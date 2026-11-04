"""HA-side bridge over the panel's pinned, paired WebSocket.

Only the small protocol used by the renderer is supported. No HA access token
is created or sent to the panel. Subscriptions belong to this connection.
"""
from __future__ import annotations
import asyncio
import time
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from .media import allowed_media, fetch_jpeg

SERVICES = {
    "light": {"turn_on", "turn_off", "toggle"},
    "switch": {"turn_on", "turn_off", "toggle"},
    "input_boolean": {"turn_on", "turn_off", "toggle"},
    "humidifier": {"turn_on", "turn_off", "set_humidity", "set_mode"},
    "fan": {"turn_on", "turn_off", "toggle", "set_percentage", "set_preset_mode", "oscillate", "set_direction"},
    "cover": {"open_cover", "close_cover", "stop_cover", "set_cover_position"},
    "climate": {"set_temperature", "set_hvac_mode", "set_preset_mode", "set_fan_mode", "set_swing_mode", "turn_on", "turn_off"},
    "media_player": {"media_play_pause", "media_play", "media_pause", "media_stop", "media_next_track", "media_previous_track", "volume_set", "volume_mute",
                     "volume_up", "volume_down", "select_source", "turn_on", "turn_off"},
    "remote": {"send_command"},
    "scene": {"turn_on"}, "script": {"turn_on", "turn_off"},
    "button": {"press"}, "input_button": {"press"},
    "number": {"set_value"}, "input_number": {"set_value"},
    "select": {"select_option"}, "input_select": {"select_option"},
    "text": {"set_value"}, "input_text": {"set_value"}, "input_datetime": {"set_datetime"},
}


class PanelBridge:
    def __init__(self, hass, send):
        self.hass, self.send = hass, send
        self.subscriptions = {}
        self.selected = {}
        self.tasks = set()
        self.last_id = 0
        self.closed = False

    @callback
    def emit(self, value):
        if self.closed:
            return
        if len(self.tasks) >= 128:
            self.close()
            return
        task = self.hass.async_create_task(self.send(value), "S1E bridge event")
        self.tasks.add(task)
        task.add_done_callback(self.sent)

    @callback
    def sent(self, task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            self.close()

    def close(self):
        self.closed = True
        for unsub in self.subscriptions.values():
            unsub()
        self.subscriptions.clear()
        self.selected.clear()
        for task in self.tasks:
            task.cancel()

    def state(self, entity_id):
        state = self.hass.states.get(entity_id)
        if state is None:
            return {"r": [entity_id]}
        return {"a": {entity_id: {"s": state.state, "a": dict(state.attributes),
                                 "lc": state.last_changed.timestamp()}}}

    async def handle(self, msg):
        request_id = msg.get("id")
        if type(request_id) is not int or request_id <= self.last_id:
            return  # Never replay commands, including after an error.
        self.last_id = request_id
        try:
            result = await self.dispatch(request_id, msg)
        except (ValueError, KeyError, TypeError):
            await self.send({"id": request_id, "type": "result", "success": False,
                             "error": {"code": "invalid_request"}})
        except Exception:
            # Service exceptions may contain private data; do not forward or log them.
            await self.send({"id": request_id, "type": "result", "success": False,
                             "error": {"code": "ha_request_failed"}})
        else:
            await self.send({"id": request_id, "type": "result", "success": True, "result": result})

    async def dispatch(self, request_id, msg):
        kind = msg["type"]
        if kind == "ping":
            await self.send({"id": request_id, "type": "pong"})
            return None
        if kind == "get_config":
            return {"time_zone": self.hass.config.time_zone, "server_time": time.time()}
        if kind == "get_states":
            return [state.as_dict() for state in self.hass.states.async_all()]
        if kind == "config/area_registry/list":
            return [{"area_id": a.id, "name": a.name} for a in ar.async_get(self.hass).areas.values()]
        if kind == "config/device_registry/list":
            keys = ("id", "name", "name_by_user", "area_id", "model", "manufacturer")
            return [{k: getattr(d, k) for k in keys} for d in dr.async_get(self.hass).devices.values()]
        if kind == "config/entity_registry/list":
            keys = ("entity_id", "name", "original_name", "device_id", "area_id", "icon", "disabled_by", "hidden_by")
            return [{**{k: getattr(e, k) for k in keys}, "aliases": list(e.aliases)}
                    for e in er.async_get(self.hass).entities.values()]
        if kind == "unsubscribe_events":
            unsub = self.subscriptions.pop(msg["subscription"], None)
            self.selected.pop(msg["subscription"], None)
            if unsub:
                unsub()
            return None
        if kind in ("subscribe_events", "subscribe_entities", "weather/subscribe_forecast"):
            if len(self.subscriptions) >= 80:
                raise ValueError
            return await self.subscribe(request_id, msg)
        if kind == "s1e/media":
            # A picture for the screen: only cameras and images the panel shows (subscribed) or that
            # a service call put on it (a doorbell photo kept live).
            entity_id = msg["entity_id"]
            shown = set().union(*self.selected.values()) if self.selected else set()
            if entity_id not in shown and entity_id not in allowed_media(self.hass):
                raise ValueError
            async with asyncio.timeout(20):
                return await fetch_jpeg(self.hass, entity_id, msg["width"], msg["height"], msg.get("fit", "contain"))
        if kind == "call_service":
            entity_id = msg["target"]["entity_id"]
            domain, service, data = msg["domain"], msg["service"], msg.get("service_data", {})
            allowed = set().union(*self.selected.values()) if self.selected else set()
            if (not isinstance(entity_id, str) or entity_id not in allowed
                    or not entity_id.startswith(domain + ".")
                    or service not in SERVICES.get(domain, ()) or not self.hass.states.get(entity_id)
                    or not isinstance(data, dict)
                    or any(k in data for k in ("entity_id", "area_id", "device_id", "floor_id", "label_id"))):
                raise ValueError
            async with asyncio.timeout(30):
                await self.hass.services.async_call(domain, service, {**data, "entity_id": entity_id}, blocking=True)
            return None
        raise ValueError

    async def subscribe(self, request_id, msg):
        if msg["type"] == "subscribe_events":
            event_type = msg["event_type"]
            if event_type not in ("area_registry_updated", "device_registry_updated", "entity_registry_updated"):
                raise ValueError
            @callback
            def registry(event):
                self.emit({"id": request_id, "type": "event", "event": {"event_type": event_type, "data": dict(event.data)}})
            self.subscriptions[request_id] = self.hass.bus.async_listen(event_type, registry)
        elif msg["type"] == "subscribe_entities":
            ids = msg["entity_ids"]
            if not isinstance(ids, list) or len(ids) > 512 or any(not isinstance(i, str) or len(i) > 255 for i in ids):
                raise ValueError
            self.selected[request_id] = set(ids)
            @callback
            def changed(event):
                entity_id = event.data["entity_id"]
                if entity_id in self.selected.get(request_id, ()):
                    self.emit({"id": request_id, "type": "event", "event": self.state(entity_id)})
            self.subscriptions[request_id] = self.hass.bus.async_listen("state_changed", changed)
            for entity_id in self.selected[request_id]:
                await self.send({"id": request_id, "type": "event", "event": self.state(entity_id)})
        else:
            from homeassistant.components.weather.const import DATA_COMPONENT
            from homeassistant.components.weather.websocket_api import FORECAST_TYPE_TO_FLAG
            forecast_type = msg["forecast_type"]
            component = self.hass.data.get(DATA_COMPONENT)
            entity = component.get_entity(msg["entity_id"]) if component else None
            if (entity is None or forecast_type not in FORECAST_TYPE_TO_FLAG
                    or not (entity.supported_features or 0) & FORECAST_TYPE_TO_FLAG[forecast_type]):
                raise ValueError
            @callback
            def forecast(entries):
                self.emit({"id": request_id, "type": "event", "event": {"forecast": entries}})
            self.subscriptions[request_id] = entity.async_subscribe_forecast(forecast_type, forecast)
            await entity.async_update_listeners({forecast_type})
        return None
