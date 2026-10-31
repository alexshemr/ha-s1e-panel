from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


class PanelEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, suffix):
        super().__init__(coordinator)
        uid = coordinator.data["device_id"]
        self._attr_unique_id = f"{uid}_{suffix}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, uid)}, name=f"S1E {uid[-6:]}",
            manufacturer="Aqara / S1E Panel", model="S1E NPD1121WSK01", sw_version=coordinator.data.get("version"),
            configuration_url=coordinator.client.url)
