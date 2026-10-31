"""Set up S1E Panel through the UI."""
from __future__ import annotations
import asyncio
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .client import PanelClient, PanelError, PanelAuthError
from .const import DOMAIN

SCHEMA = vol.Schema({vol.Required("url", default="https://192.168.1.100:8443"): str,
    vol.Required("token"): str, vol.Required("fingerprint"): str})
ADDRESS = vol.Schema({vol.Required("url", default="https://s1e-panel.local:8443"): str})


class S1EConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._connection = None
        self._pair_task = None
        self._paired = None

    async def async_step_zeroconf(self, discovery_info):
        props = discovery_info.properties
        try:
            url = f"https://{discovery_info.host}:{discovery_info.port}"
            fingerprint = props["fingerprint"]
            PanelClient(async_get_clientsession(self.hass), url, None, fingerprint)
            device_id = props["id"]
        except (ValueError, KeyError):
            return self.async_abort(reason="invalid_discovery")
        await self.async_set_unique_id(device_id)
        for entry in self._async_current_entries():
            if entry.unique_id == device_id and entry.data["fingerprint"] != fingerprint:
                return self.async_abort(reason="certificate_changed")
        self._abort_if_unique_id_configured(updates={"url": url})
        self._connection = {"url": url, "fingerprint": fingerprint}
        self.context["title_placeholders"] = {"name": f"S1E {device_id[-6:]}"}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        if user_input is not None:
            return await self.async_step_pair()
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}))

    async def _pair(self):
        client = PanelClient(async_get_clientsession(self.hass), token=None, **self._connection)
        info = await client.request("GET", "/info")
        if self.unique_id and info["device_id"] != self.unique_id:
            raise PanelError("Wrong device")
        await self.async_set_unique_id(info["device_id"])
        pending = await client.request("POST", "/pair", {"kind": "ha", "name": "Home Assistant"})
        async with asyncio.timeout(120):
            while True:
                result = await client.request("GET", "/pair/" + pending["id"])
                if result.get("status") == "approved":
                    self._paired = {**self._connection, "token": result["token"]}
                    status = await PanelClient(async_get_clientsession(self.hass), **self._paired).status()
                    if status["device_id"] != self.unique_id:
                        raise PanelError("Wrong device")
                    return
                await asyncio.sleep(1)

    async def async_step_pair(self, user_input=None):
        if self._pair_task is None:
            self._pair_task = self.hass.async_create_task(self._pair(), "S1E physical pairing")
        if not self._pair_task.done():
            return self.async_show_progress(step_id="pair", progress_action="physical_confirmation", progress_task=self._pair_task)
        try:
            self._pair_task.result()
        except (PanelError, ValueError, KeyError, asyncio.TimeoutError):
            return self.async_abort(reason="pairing_failed")
        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_finish(self, user_input=None):
        if self.source == config_entries.SOURCE_REAUTH:
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=self._paired)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=f"S1E {self.unique_id[-6:]}", data=self._paired)

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                if "token" not in user_input:
                    # Initial trust on the local network; no credential is sent
                    # until the advertised certificate is pinned and confirmed.
                    url = user_input["url"].rstrip("/")
                    PanelClient(async_get_clientsession(self.hass), url, None, "0" * 64)
                    async with async_get_clientsession(self.hass).get(url + "/api/v1/info", ssl=False,
                            allow_redirects=False, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status != 200:
                            raise PanelError("Panel unavailable")
                        info = await response.json()
                    self._connection = {"url": url, "fingerprint": info["certificate_sha256"]}
                    PanelClient(async_get_clientsession(self.hass), token=None, **self._connection)
                    await self.async_set_unique_id(info["device_id"])
                    self._abort_if_unique_id_configured()
                    return await self.async_step_confirm()
                client = PanelClient(async_get_clientsession(self.hass), **user_input)
                status = await client.status()
                await self.async_set_unique_id(status["device_id"])
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(title=f"S1E {status['device_id'][-6:]}", data=user_input)
            except PanelAuthError:
                errors["base"] = "invalid_auth"
            except (PanelError, ValueError, KeyError, aiohttp.ClientError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="user", data_schema=ADDRESS, errors=errors)

    async def async_step_reauth(self, entry_data):
        self._connection = {k: entry_data[k] for k in ("url", "fingerprint")}
        await self.async_set_unique_id(self._get_reauth_entry().unique_id)
        return await self.async_step_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                status = await PanelClient(async_get_clientsession(self.hass), **user_input).status()
                entry = self._get_reauth_entry()
                if status["device_id"] != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
            except (PanelError, ValueError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="reauth_confirm", data_schema=SCHEMA, errors=errors)
