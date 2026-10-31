"""HTTPS and push client. No credentials are placed in URLs or log messages."""
from __future__ import annotations
import asyncio
import re
from typing import Any
import aiohttp


class PanelError(Exception):
    """Panel request failed."""


class PanelAuthError(PanelError):
    """Pairing key was rejected."""


class PanelClient:
    def __init__(self, session: aiohttp.ClientSession, url: str, token: str, fingerprint: str) -> None:
        self.session = session
        self.url = url.rstrip("/")
        if not self.url.startswith("https://") or "@" in self.url:
            raise ValueError("HTTPS URL required")
        clean = re.sub(r"[:\s]", "", fingerprint)
        if len(clean) != 64 or not re.fullmatch(r"[a-fA-F0-9]{64}", clean):
            raise ValueError("SHA-256 certificate fingerprint required")
        self.ssl = aiohttp.Fingerprint(bytes.fromhex(clean))
        if not re.fullmatch(r"[a-fA-F0-9]{64}", token):
            raise ValueError("Invalid pairing key")
        self.headers = {"Authorization": f"Bearer {token}"}

    async def request(self, method: str, path: str, data: dict | None = None) -> Any:
        try:
            async with self.session.request(method, f"{self.url}/api/v1{path}", json=data,
                    headers=self.headers, ssl=self.ssl, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 401:
                    raise PanelAuthError("Pairing key rejected")
                result = await response.json()
                if response.status >= 400:
                    raise PanelError(result.get("error", f"HTTP {response.status}"))
                return result
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise PanelError("Panel unavailable or certificate mismatch") from err

    async def status(self) -> dict:
        return await self.request("GET", "/status")

    async def command(self, relay: int, on: bool) -> None:
        await self.request("POST", "/commands", {"entity_id": f"local.relay{relay}", "action": "turn_on" if on else "turn_off"})

    async def screen(self, on: bool, brightness: int | None = None) -> None:
        data: dict[str, Any] = {"on": on}
        if brightness is not None:
            data["brightness"] = brightness
        await self.request("PUT", "/screen", data)

    async def messages(self):
        async with self.session.ws_connect(f"{self.url}/api/v1/events", headers=self.headers,
                ssl=self.ssl, protocols=("panel",), heartbeat=30, max_msg_size=2 * 1024 * 1024) as websocket:
            async for message in websocket:
                if message.type == aiohttp.WSMsgType.TEXT:
                    yield message.json()
                elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
