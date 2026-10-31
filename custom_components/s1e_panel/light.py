from homeassistant.components.light import LightEntity, ColorMode, ATTR_BRIGHTNESS
from .entity import PanelEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PanelScreen(hass.data[DOMAIN][entry.entry_id])])


class PanelScreen(PanelEntity, LightEntity):
    _attr_translation_key = "screen"
    _attr_icon = "mdi:monitor"
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator):
        super().__init__(coordinator, "screen")

    @property
    def is_on(self):
        return self.coordinator.data["runtime"]["brightness"] > 0

    @property
    def extra_state_attributes(self):
        runtime = self.coordinator.data["runtime"]
        reasons = []
        if runtime.get("sleep_active"): reasons.append("night")
        if runtime.get("external_off"): reasons.append("home_assistant")
        if not reasons and not self.is_on: reasons.append("timeout")
        return {"off_reasons": reasons, "temporary_wake": runtime.get("temporary_wake", False)}

    @property
    def brightness(self):
        return round(self.coordinator.data["runtime"]["brightness"] * 255 / 100)

    async def async_turn_on(self, **kwargs):
        brightness = max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)) if ATTR_BRIGHTNESS in kwargs else None
        await self.coordinator.client.screen(True, brightness)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.coordinator.client.screen(False)
        await self.coordinator.async_request_refresh()
