"""Set up S1E Panel through the UI."""
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .client import PanelClient, PanelError, PanelAuthError
from .const import DOMAIN

SCHEMA = vol.Schema({vol.Required("url", default="https://192.168.1.100:8443"): str,
    vol.Required("token"): str, vol.Required("fingerprint"): str})


class S1EConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                client = PanelClient(async_get_clientsession(self.hass), **user_input)
                status = await client.status()
                await self.async_set_unique_id(status["device_id"])
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(title=f"S1E {status['device_id'][-6:]}", data=user_input)
            except PanelAuthError:
                errors["base"] = "invalid_auth"
            except (PanelError, ValueError, KeyError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

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
