from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.entity import EntityCategory
from .entity import PanelEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PanelConnection(hass.data[DOMAIN][entry.entry_id])])


class PanelConnection(PanelEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "ha_connection"

    def __init__(self, coordinator):
        super().__init__(coordinator, "ha_connection")

    @property
    def is_on(self):
        return self.coordinator.data.get("ha", {}).get("online", False)

