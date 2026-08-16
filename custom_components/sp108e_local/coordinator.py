"""Coordinator for SP108E Local."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
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
_WRITE_SETTLE_SECONDS = 0.05

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
        self._operation_lock = asyncio.Lock()
        self._power_state_uncertain = False
        self._pending_rgb: tuple[int, int, int] | None = None
        self._pending_color_task: asyncio.Task[None] | None = None
        self._retained_tasks: set[asyncio.Task[Any]] = set()
        self._shutdown_started = False
        self._shutdown_complete = False
        self._shutdown_lock = asyncio.Lock()
        self._shutdown_task: asyncio.Task[None] | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )

    async def _async_update_data(self) -> Sp108eSettings:
        return await self._run_command(self.client.get_settings)

    async def _run_command(self, func: Callable[..., _T], *args: Any) -> _T:
        command_task = self._create_retained_task(self._async_run_command_locked(func, *args))
        return await asyncio.shield(command_task)

    async def _run_write_command(self, func: Callable[..., None], *args: Any) -> None:
        command_task = self._create_retained_task(self._async_run_write_command_locked(func, *args))
        await asyncio.shield(command_task)

    async def _run_color_attempt(self, device_rgb: tuple[int, int, int]) -> Sp108eSettings:
        command_task = self._create_retained_task(self._async_run_color_attempt_locked(device_rgb))
        return await asyncio.shield(command_task)

    def _create_retained_task(self, coroutine: Coroutine[Any, Any, _T]) -> asyncio.Task[_T]:
        task = self.hass.async_create_task(coroutine)
        self._retained_tasks.add(task)
        task.add_done_callback(self._retained_tasks.discard)
        return task

    def _create_operation_task(self, coroutine: Coroutine[Any, Any, _T]) -> asyncio.Task[_T]:
        if self._shutdown_started:
            coroutine.close()
            raise UpdateFailed("coordinator is shutting down")
        return self._create_retained_task(coroutine)

    async def async_shutdown(self) -> None:
        shutdown_task = self._shutdown_task
        if shutdown_task is None:
            shutdown_task = self.hass.async_create_task(self._async_shutdown())
            self._shutdown_task = shutdown_task
        await asyncio.shield(shutdown_task)

    async def _async_shutdown(self) -> None:
        async with self._shutdown_lock:
            if self._shutdown_complete:
                return
            self._shutdown_started = True
            await super().async_shutdown()
            self.cancel_pending_color()
            while self._retained_tasks:
                tasks = tuple(self._retained_tasks)
                await asyncio.gather(*tasks, return_exceptions=True)
                self._retained_tasks.difference_update(task for task in tasks if task.done())
            self._shutdown_complete = True

    async def _async_run_command_locked(self, func: Callable[..., _T], *args: Any) -> _T:
        async with self._command_lock:
            try:
                return await self.hass.async_add_executor_job(func, *args)
            except Sp108eError as err:
                raise UpdateFailed(str(err)) from err

    async def _async_run_write_command_locked(self, func: Callable[..., None], *args: Any) -> None:
        async with self._command_lock:
            try:
                await self.hass.async_add_executor_job(func, *args)
                await asyncio.sleep(_WRITE_SETTLE_SECONDS)
            except Sp108eError as err:
                raise UpdateFailed(str(err)) from err

    async def _async_run_color_attempt_locked(self, device_rgb: tuple[int, int, int]) -> Sp108eSettings:
        async with self._command_lock:
            try:
                await self.hass.async_add_executor_job(self.client.set_color, *device_rgb)
                await asyncio.sleep(_WRITE_SETTLE_SECONDS)
                return await self.hass.async_add_executor_job(self.client.get_settings)
            except Sp108eError as err:
                raise UpdateFailed(str(err)) from err

    async def _ensure_state(self) -> Sp108eSettings:
        if self._power_state_uncertain:
            state = await self._run_command(self.client.get_settings)
            self.async_set_updated_data(state)
            self._power_state_uncertain = False
        if self.data is None or not self.last_update_success:
            await self.async_request_refresh()
        if self.data is None:
            raise UpdateFailed("state unavailable")
        return self.data

    async def _async_toggle_power(self) -> Sp108eSettings:
        self._power_state_uncertain = True
        state = await self._run_command(self.client.toggle_power)
        if state is None:
            state = await self._run_command(self.client.get_settings)
        self.async_set_updated_data(state)
        self._power_state_uncertain = False
        return state

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
        self._pending_color_task = self._create_retained_task(self._async_send_pending_color())

    async def _async_send_pending_color(self) -> None:
        try:
            if self.color_debounce > 0:
                await asyncio.sleep(self.color_debounce)
            rgb_color = self._pending_rgb
            self._pending_rgb = None
            if rgb_color is None:
                return
            device_rgb = map_rgb_to_device(rgb_color, self.rgb_order)
            await self._run_write_command(self.client.set_color, *device_rgb)
            await self.async_request_refresh()
        except asyncio.CancelledError:
            return

    async def _async_set_color_verified(self, rgb_color: tuple[int, int, int]) -> None:
        device_rgb = map_rgb_to_device(rgb_color, self.rgb_order)
        last_rgb: tuple[int, int, int] | None = None
        for _attempt in range(2):
            state = await self._run_color_attempt(device_rgb)
            self.async_set_updated_data(state)
            last_rgb = state.color_rgb
            if last_rgb == device_rgb:
                return
        raise UpdateFailed(f"color readback mismatch after retry: expected {device_rgb}, got {last_rgb}")

    async def async_turn_on(
        self,
        brightness: int | None = None,
        rgb_color: tuple[int, int, int] | None = None,
        effect: str | None = None,
    ) -> None:
        transaction = self._create_operation_task(self._async_turn_on_transaction(brightness, rgb_color, effect))
        await asyncio.shield(transaction)

    async def _async_turn_on_transaction(
        self,
        brightness: int | None,
        rgb_color: tuple[int, int, int] | None,
        effect: str | None,
    ) -> None:
        async with self._operation_lock:
            state = await self._ensure_state()
            if not state.is_on:
                state = await self._async_toggle_power()
            if effect is not None:
                await self._run_write_command(self.client.set_mode, EFFECTS[effect])
            elif rgb_color is not None and state.effect_raw != EFFECTS[SOLID_EFFECT]:
                await self._run_write_command(self.client.set_mode, EFFECTS[SOLID_EFFECT])
            if brightness is not None:
                await self._run_write_command(self.client.set_brightness, brightness)
            if rgb_color is not None:
                if self.color_debounce > 0:
                    self._schedule_color(rgb_color)
                else:
                    await self._async_set_color_verified(rgb_color)
            else:
                await self.async_request_refresh()

    async def async_turn_off(self) -> None:
        transaction = self._create_operation_task(self._async_turn_off_transaction())
        await asyncio.shield(transaction)

    async def _async_turn_off_transaction(self) -> None:
        async with self._operation_lock:
            self.cancel_pending_color()
            state = await self._ensure_state()
            if state.is_on:
                await self._async_toggle_power()
            await self.async_request_refresh()

    async def async_set_speed(self, speed: int) -> None:
        transaction = self._create_operation_task(self._async_set_speed_transaction(speed))
        await asyncio.shield(transaction)

    async def _async_set_speed_transaction(self, speed: int) -> None:
        await self._run_write_command(self.client.set_speed, speed)
        await self.async_request_refresh()
