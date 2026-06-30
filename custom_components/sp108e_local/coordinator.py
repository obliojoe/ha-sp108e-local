"""Coordinator for SP108E Local."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .color_order import map_rgb_from_device, map_rgb_to_device
from .const import (
    CONF_COLOR_DEBOUNCE,
    CONF_DEVICE_NAME,
    CONF_RGB_ORDER,
    CONF_TIMEOUT,
    DEFAULT_COLOR_DEBOUNCE,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_RGB_ORDER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .effects import EFFECTS, SOLID_EFFECT
from .protocol import Sp108eClient, Sp108eError, Sp108eSettings

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T")


class Sp108eDataUpdateCoordinator(DataUpdateCoordinator[Sp108eSettings]):
    """Fetch and write SP108E state."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        values = {**entry.data, **entry.options}
        self.host = values[CONF_HOST]
        self.port = values.get(CONF_PORT, DEFAULT_PORT)
        self.timeout = values.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        self.display_name = values.get(CONF_NAME, entry.title or DEFAULT_NAME)
        self.rgb_order = values.get(CONF_RGB_ORDER, DEFAULT_RGB_ORDER)
        self.color_debounce = values.get(CONF_COLOR_DEBOUNCE, DEFAULT_COLOR_DEBOUNCE)
        self.unique_id = entry.unique_id or values.get(CONF_DEVICE_NAME) or f"{self.host}:{self.port}"
        self.client = Sp108eClient(self.host, self.port, self.timeout)
        self._command_lock = asyncio.Lock()
        self._pending_rgb: tuple[int, int, int] | None = None
        self._pending_color_task: asyncio.Task[None] | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )

    async def _async_update_data(self) -> Sp108eSettings:
        try:
            return await self.hass.async_add_executor_job(self.client.get_settings)
        except Sp108eError as err:
            raise UpdateFailed(str(err)) from err

    async def _run_command(self, func: Callable[..., _T], *args: Any) -> _T:
        async with self._command_lock:
            try:
                return await self.hass.async_add_executor_job(func, *args)
            except Sp108eError as err:
                raise UpdateFailed(str(err)) from err

    async def _ensure_state(self) -> Sp108eSettings:
        if self.data is None or not self.last_update_success:
            await self.async_request_refresh()
        if self.data is None:
            raise UpdateFailed("state unavailable")
        return self.data

    def rgb_color_for_ha(self) -> tuple[int, int, int] | None:
        if self.data is None:
            return None
        return map_rgb_from_device(self.data.color_rgb, self.rgb_order)

    def cancel_pending_color(self) -> None:
        self._pending_rgb = None
        if self._pending_color_task is not None and not self._pending_color_task.done():
            self._pending_color_task.cancel()
        self._pending_color_task = None

    def _schedule_color(self, rgb_color: tuple[int, int, int]) -> None:
        self._pending_rgb = rgb_color
        if self._pending_color_task is not None and not self._pending_color_task.done():
            self._pending_color_task.cancel()
        self._pending_color_task = self.hass.async_create_task(self._async_send_pending_color())

    async def _async_send_pending_color(self) -> None:
        try:
            if self.color_debounce > 0:
                await asyncio.sleep(self.color_debounce)
            rgb_color = self._pending_rgb
            self._pending_rgb = None
            if rgb_color is None:
                return
            device_rgb = map_rgb_to_device(rgb_color, self.rgb_order)
            await self._run_command(self.client.set_color, *device_rgb)
            await self.async_request_refresh()
        except asyncio.CancelledError:
            return

    async def async_turn_on(
        self,
        brightness: int | None = None,
        rgb_color: tuple[int, int, int] | None = None,
        effect: str | None = None,
    ) -> None:
        state = await self._ensure_state()
        if not state.is_on:
            await self._run_command(self.client.toggle_power)
        if effect is not None:
            await self._run_command(self.client.set_mode, EFFECTS[effect])
        elif rgb_color is not None and state.effect_raw != EFFECTS[SOLID_EFFECT]:
            await self._run_command(self.client.set_mode, EFFECTS[SOLID_EFFECT])
        if brightness is not None:
            await self._run_command(self.client.set_brightness, brightness)
        if rgb_color is not None:
            self._schedule_color(rgb_color)
        else:
            await self.async_request_refresh()

    async def async_turn_off(self) -> None:
        self.cancel_pending_color()
        state = await self._ensure_state()
        if state.is_on:
            await self._run_command(self.client.toggle_power)
        await self.async_request_refresh()

    async def async_set_speed(self, speed: int) -> None:
        await self._run_command(self.client.set_speed, speed)
        await self.async_request_refresh()
