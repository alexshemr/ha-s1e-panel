"""Night mode schedule: when the screen goes to sleep and when it wakes."""
from datetime import time
from homeassistant.components.time import TimeEntity
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .switch import PanelSleepEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PanelNightTime(coordinator, "start"), PanelNightTime(coordinator, "end")])


class PanelNightTime(PanelSleepEntity, TimeEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, edge):
        super().__init__(coordinator, f"night_{edge}")
        self.edge = edge
        self._attr_translation_key = f"night_{edge}"
        self._attr_icon = "mdi:bed-clock" if edge == "start" else "mdi:weather-sunset-up"

    @property
    def native_value(self):
        value = (self.schedule or {}).get(self.edge)
        try:
            hour, minute = str(value).split(":")
            return time(int(hour), int(minute))
        except (TypeError, ValueError):
            return None

    async def async_set_value(self, value: time) -> None:
        await self._put({self.edge: f"{value.hour:02d}:{value.minute:02d}"})
