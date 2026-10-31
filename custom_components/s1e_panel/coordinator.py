from __future__ import annotations
import asyncio
import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .client import PanelClient, PanelError, PanelAuthError
from .const import DOMAIN
_LOGGER = logging.getLogger(__name__)


class PanelCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, client: PanelClient, entry):
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=timedelta(seconds=30))
        self.client, self.entry = client, entry
        self._task = None
        self._bridge_task = None

    async def _async_update_data(self):
        try:
            return await self.client.status()
        except PanelAuthError as err:
            raise ConfigEntryAuthFailed from err
        except PanelError as err:
            raise UpdateFailed(str(err)) from err

    def start(self):
        self._task = self.entry.async_create_background_task(self.hass, self._listen(), "S1E push")
        self._ensure_bridge(self.data)

    def _ensure_bridge(self, data):
        if data.get("ha", {}).get("bridge_supported") and self._bridge_task is None:
            self._bridge_task = self.entry.async_create_background_task(self.hass, self._bridge(), "S1E HA bridge")

    async def _bridge(self):
        delay = 1
        while True:
            try:
                await self.client.bridge(self.hass)
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug("S1E bridge reconnect: %s", type(err).__name__)
            await asyncio.sleep(delay)
            delay = min(60, delay * 2)

    async def _listen(self):
        delay = 1
        while True:
            try:
                async for data in self.client.messages():
                    self.async_set_updated_data(data)
                    self._ensure_bridge(data)
                    delay = 1
                self.async_set_update_error(UpdateFailed("Push connection closed"))
            except asyncio.CancelledError:
                raise
            except (PanelError, OSError, ValueError, asyncio.TimeoutError) as err:
                self.async_set_update_error(UpdateFailed(type(err).__name__))
            except Exception as err:  # aiohttp websocket exceptions vary by version
                self.async_set_update_error(UpdateFailed(type(err).__name__))
            await asyncio.sleep(delay)
            delay = min(60, delay * 2)

    async def stop(self):
        tasks = [task for task in (self._task, self._bridge_task) if task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
