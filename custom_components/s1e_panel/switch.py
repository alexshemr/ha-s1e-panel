from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from .client import PanelError
from .entity import PanelEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([*(PanelRelay(coordinator, i) for i in range(1, 4)),
        PanelNightMode(coordinator), PanelNightSchedule(coordinator)])


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


class PanelSleepEntity(PanelEntity):
    """Night mode: the panel reports its schedule from firmware 0.8.5 on."""

    @property
    def schedule(self):
        return self.coordinator.data["runtime"].get("sleep_schedule")

    @property
    def available(self):
        return super().available and isinstance(self.schedule, dict)

    async def _put(self, data):
        if not self.available:
            raise HomeAssistantError("Panel night mode unavailable")
        try:
            await self.coordinator.client.request("PUT", "/sleep", data)
        except PanelError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


class PanelNightMode(PanelSleepEntity, SwitchEntity):
    """On: the screen sleeps now. Set by hand, it holds until the schedule next turns (bedtime or morning)."""
    _attr_translation_key = "night_mode"
    _attr_icon = "mdi:weather-night"

    def __init__(self, coordinator):
        super().__init__(coordinator, "night_mode")

    @property
    def is_on(self):
        return self.coordinator.data["runtime"].get("sleep_active", False)

    @property
    def extra_state_attributes(self):
        return {"manual": self.coordinator.data["runtime"].get("sleep_manual", False)}

    async def async_turn_on(self, **kwargs):
        await self._put({"active": True})

    async def async_turn_off(self, **kwargs):
        await self._put({"active": False})


class PanelNightSchedule(PanelSleepEntity, SwitchEntity):
    _attr_translation_key = "night_schedule"
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator, "night_schedule")

    @property
    def is_on(self):
        return bool((self.schedule or {}).get("enabled"))

    async def async_turn_on(self, **kwargs):
        await self._put({"enabled": True})

    async def async_turn_off(self, **kwargs):
        await self._put({"enabled": False})
