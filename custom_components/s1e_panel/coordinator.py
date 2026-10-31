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

    async def _async_update_data(self):
        try:
            return await self.client.status()
        except PanelAuthError as err:
            raise ConfigEntryAuthFailed from err
        except PanelError as err:
            raise UpdateFailed(str(err)) from err

    def start(self):
        self._task = self.entry.async_create_background_task(self.hass, self._listen(), "S1E push")

    async def _listen(self):
        delay = 1
        while True:
            try:
                async for data in self.client.messages():
                    self.async_set_updated_data(data)
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
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
