from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory
from .entity import PanelEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(PanelSensor(coordinator, kind) for kind in ("version", "wifi", "screen_mode", "ip_address"))


class PanelSensor(PanelEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, kind):
        super().__init__(coordinator, kind)
        self.kind = kind
        self._attr_translation_key = kind
        self._attr_icon = {"version": "mdi:information-outline", "wifi": "mdi:wifi",
                           "screen_mode": "mdi:monitor-dashboard", "ip_address": "mdi:ip-network"}[kind]

    @property
    def native_value(self):
        data = self.coordinator.data
        if self.kind == "version":
            return data.get("version")
        if self.kind == "screen_mode":
            return data["runtime"]["view"]
        wifi = data.get("hardware", {}).get("wifi", {})
        return wifi.get("ip" if self.kind == "ip_address" else "ssid") or None
