"""Persistent screensaver selection; options are advertised by the panel."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from .client import PanelError
from .const import DOMAIN
from .entity import PanelEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PanelScreensaver(hass.data[DOMAIN][entry.entry_id])])


class PanelScreensaver(PanelEntity, SelectEntity):
    _attr_translation_key = "screensaver"
    _attr_icon = "mdi:monitor-dashboard"

    def __init__(self, coordinator):
        super().__init__(coordinator, "screensaver")

    @property
    def options(self):
        return self.coordinator.data.get("screensaver", {}).get("options", [])

    @property
    def current_option(self):
        return self.coordinator.data.get("screensaver", {}).get("selected")

    @property
    def available(self):
        return super().available and bool(self.options) and self.current_option in self.options

    async def async_select_option(self, option):
        if not self.available or option not in self.options:
            raise HomeAssistantError("Screensaver is unavailable or unsupported")
        try:
            await self.coordinator.client.request("PUT", "/screensaver", {"selected": option})
        except PanelError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
