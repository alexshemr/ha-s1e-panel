"""Local integration for the open S1E panel."""
from __future__ import annotations
import logging
from urllib.parse import quote
import voluptuous as vol
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .client import PanelClient, PanelError
from .const import DOMAIN, PLATFORMS
from .coordinator import PanelCoordinator
from .media import allowed_media, fetch_jpeg

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry):
    coordinator = PanelCoordinator(hass, PanelClient(async_get_clientsession(hass), **entry.data), entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start()

    async def show_message(call: ServiceCall):
        device = dr.async_get(hass).async_get(call.data["device_id"])
        matches = [c for eid, c in hass.data[DOMAIN].items() if device and eid == device.config_entry_id]
        if not matches:
            raise HomeAssistantError("S1E panel not found")
        body = {key: value for key, value in call.data.items() if key != "device_id"}
        if isinstance(body.get("weather"), dict):
            weather = dict(body["weather"])
            entity_id = weather.get("entity_id")
            entity = hass.states.get(entity_id) if isinstance(entity_id, str) and entity_id else None
            for unit in ("temperature_unit", "wind_speed_unit", "precipitation_unit"):
                if unit not in weather and entity and unit in entity.attributes:
                    weather[unit] = entity.attributes[unit]
            weather.setdefault("temperature_unit", hass.config.units.temperature_unit)
            weather.setdefault("wind_speed_unit", hass.config.units.wind_speed_unit)
            weather.setdefault("precipitation_unit", hass.config.units.accumulated_precipitation_unit)
            body["weather"] = weather
        # A photo with the message: taken now (the moment the doorbell rang), fitted to the screen.
        # live: the panel keeps asking the camera for frames while the message is shown.
        image = body.pop("image", None)
        live = body.pop("live", False)
        if image and call.service == "show_message":
            try:
                body["image"] = await fetch_jpeg(hass, image, 480, 360)
            except Exception as err:  # the message still goes out, without the photo
                _LOGGER.warning("S1E panel: no photo from %s (%s)", image, type(err).__name__)
            else:
                if live and image.startswith("camera."):
                    allowed_media(hass).add(image)
                    body["live"] = image
        path = "/notifications"
        if call.service == "dismiss_notification":
            path += "/" + quote(body["id"], safe="")
        try:
            for target in matches:
                await target.client.request("POST" if call.service == "show_message" else "DELETE", path, body if call.service == "show_message" else None)
        except PanelError as err:
            raise HomeAssistantError(str(err)) from err

    if not hass.services.has_service(DOMAIN, "show_message"):
        hass.services.async_register(DOMAIN, "show_message", show_message, schema=vol.Schema({
            vol.Required("device_id"): str, vol.Required("text"): vol.All(str, vol.Length(min=1, max=2048)),
            vol.Optional("id"): vol.All(str, vol.Match(r"^[A-Za-z0-9_.:-]{1,128}$")),
            vol.Optional("title"): vol.All(str, vol.Length(max=120)),
            vol.Optional("weather"): dict,
            vol.Optional("background", default="auto"): vol.In(["auto", "weather", "plain"]),
            vol.Optional("icon", default="information"): str,
            vol.Optional("duration", default=10): vol.All(vol.Coerce(float), vol.Range(min=1, max=3600)),
            vol.Optional("ttl", default=300): vol.All(vol.Coerce(float), vol.Range(min=1, max=86400)),
            vol.Optional("priority", default="normal"): vol.In(["normal", "high"]),
            vol.Optional("type", default="info"): vol.In(["info", "success", "warning", "error"]),
            vol.Optional("image"): vol.All(str, vol.Match(r"^(camera|image)\.[a-z0-9_]{1,240}$")),
            vol.Optional("live", default=False): bool,
        }))
    for name in ("dismiss_notification", "clear_notifications"):
        if not hass.services.has_service(DOMAIN, name):
            schema = {vol.Required("device_id"): str}
            if name == "dismiss_notification":
                schema[vol.Required("id")] = vol.All(str, vol.Match(r"^[A-Za-z0-9_.:-]{1,128}$"))
            hass.services.async_register(DOMAIN, name, show_message, schema=vol.Schema(schema))
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.stop()
        if not hass.data[DOMAIN]:
            for name in ("show_message", "dismiss_notification", "clear_notifications"):
                hass.services.async_remove(DOMAIN, name)
        return True
    return False
