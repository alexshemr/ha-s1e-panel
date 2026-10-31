from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from .client import PanelError
from .entity import PanelEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(PanelRelay(hass.data[DOMAIN][entry.entry_id], i) for i in range(1, 4))


class PanelRelay(PanelEntity, SwitchEntity):
    _attr_icon = "mdi:electric-switch"
    _attr_translation_key = "relay"

    def __init__(self, coordinator, channel):
        super().__init__(coordinator, f"relay{channel}")
        self.channel = channel
        self._attr_translation_placeholders = {"channel": str(channel)}

    @property
    def available(self):
        if not super().available:
            return False
        hardware = self.coordinator.data.get("hardware", {})
        states = hardware.get("relays", [])
        return (hardware.get("relay_verified", False) and isinstance(states, list)
                and len(states) >= self.channel and isinstance(states[self.channel - 1], bool))

    @property
    def is_on(self):
        if not self.available:
            return None
        return self.coordinator.data["hardware"]["relays"][self.channel - 1]

    async def _set_state(self, on):
        if not self.available:
            raise HomeAssistantError("Panel relay unavailable")
        try:
            await self.coordinator.client.command(self.channel, on)
            await self.coordinator.async_request_refresh()
        except PanelError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_on(self, **kwargs):
        await self._set_state(True)

    async def async_turn_off(self, **kwargs):
        await self._set_state(False)
