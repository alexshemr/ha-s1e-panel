"""HTTPS and push client. No credentials are placed in URLs or log messages."""
from __future__ import annotations
import asyncio
import re
from urllib.parse import urlsplit
from typing import Any
import aiohttp


class PanelError(Exception):
    """Panel request failed."""


class PanelAuthError(PanelError):
    """Pairing key was rejected."""


class PanelClient:
    def __init__(self, session: aiohttp.ClientSession, url: str, token: str | None, fingerprint: str) -> None:
        self.session = session
        self.url = url.rstrip("/")
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("HTTPS URL required")
        clean = re.sub(r"[:\s]", "", fingerprint)
        if len(clean) != 64 or not re.fullmatch(r"[a-fA-F0-9]{64}", clean):
            raise ValueError("SHA-256 certificate fingerprint required")
        self.ssl = aiohttp.Fingerprint(bytes.fromhex(clean))
        if token is not None and not re.fullmatch(r"[a-fA-F0-9]{64}", token):
            raise ValueError("Invalid pairing key")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def request(self, method: str, path: str, data: dict | None = None) -> Any:
        try:
            async with self.session.request(method, f"{self.url}/api/v1{path}", json=data,
                    headers=self.headers, ssl=self.ssl, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 401:
                    raise PanelAuthError("Pairing key rejected")
                result = await response.json()
                if response.status >= 300:
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

    async def bridge(self, hass):
        from homeassistant.helpers.json import json_dumps
        from .bridge import PanelBridge
        async with self.session.ws_connect(f"{self.url}/api/v1/bridge", headers=self.headers,
                ssl=self.ssl, protocols=("panel",), heartbeat=30, max_msg_size=16384) as websocket:
            lock = asyncio.Lock()
            async def send(value):
                async with lock:
                    await websocket.send_str(json_dumps(value))
            bridge = PanelBridge(hass, send)
            async def clock():
                import time
                while True:
                    await asyncio.sleep(60)
                    if bridge.closed:
                        await websocket.close()
                        return
                    await send({"type": "s1e_time", "server_time": time.time()})
            timer = asyncio.create_task(clock())
            try:
                async for message in websocket:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await bridge.handle(message.json())
                    elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
            finally:
                bridge.close()
                timer.cancel()
                await asyncio.gather(timer, *bridge.tasks, return_exceptions=True)
