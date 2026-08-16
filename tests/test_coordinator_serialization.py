from __future__ import annotations

import asyncio
import importlib
import sys
import threading
import time
import types
from contextlib import suppress
from dataclasses import replace
from pathlib import Path


def load_coordinator_module(monkeypatch):
    """Load the coordinator with the smallest Home Assistant test doubles."""
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    const = types.ModuleType("homeassistant.const")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class ConfigEntry:
        pass

    class HomeAssistant:
        pass

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        @classmethod
        def __class_getitem__(cls, _item):
            return cls

        def __init__(self, hass, _logger, *, name, update_interval):
            self.hass = hass
            self.name = name
            self.update_interval = update_interval
            self.data = None
            self.last_update_success = True
            self.base_shutdown_called = False

        def async_set_updated_data(self, data):
            self.data = data

        async def async_shutdown(self):
            self.base_shutdown_called = True

    config_entries.ConfigEntry = ConfigEntry
    const.CONF_HOST = "host"
    const.CONF_NAME = "name"
    const.CONF_PORT = "port"
    const.CONF_SCAN_INTERVAL = "scan_interval"
    core.HomeAssistant = HomeAssistant
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed

    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)
    monkeypatch.setitem(sys.modules, "homeassistant.const", const)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.update_coordinator", update_coordinator)

    package_name = "sp108e_local_coordinator_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(Path(__file__).parents[1] / "custom_components" / "sp108e_local")]
    monkeypatch.setitem(sys.modules, package_name, package)
    return importlib.import_module(f"{package_name}.coordinator")


class FakeEntry:
    data = {"host": "192.0.2.10", "scan_interval": 10}
    options = {}
    title = "Test SP108E"
    unique_id = "test-sp108e"


class FakeHass:
    async def async_add_executor_job(self, func, *args):
        return await asyncio.get_running_loop().run_in_executor(None, func, *args)

    def async_create_task(self, coroutine):
        return asyncio.create_task(coroutine)


class OverlapDetectingClient:
    def __init__(self):
        self.read_started = threading.Event()
        self.write_started = threading.Event()
        self.release_read = threading.Event()
        self._state_lock = threading.Lock()
        self.active_calls = 0
        self.max_active_calls = 0

    def _enter(self):
        with self._state_lock:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)

    def _exit(self):
        with self._state_lock:
            self.active_calls -= 1

    def get_settings(self):
        self._enter()
        self.read_started.set()
        self.release_read.wait(timeout=2)
        self._exit()
        return object()

    def set_color(self, _red, _green, _blue):
        self._enter()
        self.write_started.set()
        self._exit()


class SettleGapClient:
    def __init__(self, initial_state):
        self.state = initial_state
        self.color_started = threading.Event()
        self.write_time = None
        self.read_times = []

    def set_color(self, red, green, blue):
        self.state = replace(self.state, color_rgb=(red, green, blue))
        self.write_time = time.monotonic()
        self.color_started.set()

    def get_settings(self):
        self.read_times.append(time.monotonic())
        return self.state


class ConsecutiveWriteClient:
    def __init__(self, initial_state):
        self.state = initial_state
        self.events = []

    def set_mode(self, effect):
        self.events.append(("mode", time.monotonic()))
        self.state = replace(self.state, effect_raw=effect)

    def set_brightness(self, brightness):
        self.events.append(("brightness", time.monotonic()))
        self.state = replace(self.state, brightness_raw=brightness)

    def set_color(self, red, green, blue):
        self.events.append(("color", time.monotonic()))
        self.state = replace(self.state, color_rgb=(red, green, blue))

    def get_settings(self):
        return self.state


class BlockingColorClient:
    def __init__(self, initial_state):
        self.state = initial_state
        self.color_started = threading.Event()
        self.release_color = threading.Event()

    def set_color(self, red, green, blue):
        self.color_started.set()
        self.release_color.wait(timeout=2)
        self.state = replace(self.state, color_rgb=(red, green, blue))

    def get_settings(self):
        return self.state


class DroppedFirstColorClient:
    def __init__(self, initial_state):
        self.state = initial_state
        self.set_color_calls = 0
        self.settings_calls = 0
        self.write_times = []
        self.read_times = []

    def set_color(self, red, green, blue):
        self.set_color_calls += 1
        self.write_times.append(time.monotonic())
        if self.set_color_calls > 1:
            self.state = replace(self.state, color_rgb=(red, green, blue))

    def get_settings(self):
        self.settings_calls += 1
        self.read_times.append(time.monotonic())
        return self.state


class ReplacementColorClient:
    def __init__(self):
        self._state_lock = threading.Lock()
        self.active_calls = 0
        self.max_active_calls = 0
        self.set_color_calls = 0
        self.physical_color = None
        self.first_color_started = threading.Event()
        self.second_color_started = threading.Event()
        self.release_first_color = threading.Event()

    def set_color(self, red, green, blue):
        color = (red, green, blue)
        with self._state_lock:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
            self.set_color_calls += 1
            call_number = self.set_color_calls
        if call_number == 1:
            self.first_color_started.set()
            self.release_first_color.wait(timeout=2)
        else:
            self.second_color_started.set()
        self.physical_color = color
        with self._state_lock:
            self.active_calls -= 1


class BlockingSpeedClient:
    def __init__(self):
        self.speed_started = threading.Event()
        self.release_speed = threading.Event()

    def set_speed(self, _speed):
        self.speed_started.set()
        self.release_speed.wait(timeout=2)


class ToggleStateClient:
    def __init__(self, off_state, on_state):
        self.off_state = off_state
        self.on_state = on_state
        self.current_state = off_state
        self.toggle_count = 0

    def toggle_power(self):
        self.toggle_count += 1
        self.current_state = self.on_state if self.toggle_count % 2 else self.off_state
        return self.current_state

    def set_mode(self, _effect):
        return None

    def set_color(self, red, green, blue):
        color = (red, green, blue)
        self.off_state = replace(self.off_state, color_rgb=color)
        self.on_state = replace(self.on_state, color_rgb=color)
        self.current_state = replace(self.current_state, color_rgb=color)

    def get_settings(self):
        return self.current_state


class BlockingToggleStateClient(ToggleStateClient):
    def __init__(self, off_state, on_state):
        super().__init__(off_state, on_state)
        self.first_toggle_started = threading.Event()
        self.second_toggle_started = threading.Event()
        self.release_first_toggle = threading.Event()

    def toggle_power(self):
        self.toggle_count += 1
        if self.toggle_count == 1:
            self.first_toggle_started.set()
            self.release_first_toggle.wait(timeout=2)
            self.current_state = self.on_state
            return self.current_state
        self.second_toggle_started.set()
        self.current_state = self.off_state
        return self.current_state

    def get_settings(self):
        return self.current_state


class NoneResponseToggleClient(ToggleStateClient):
    def __init__(self, off_state, on_state):
        super().__init__(off_state, on_state)
        self.physical_on = False

    def toggle_power(self):
        self.toggle_count += 1
        self.physical_on = not self.physical_on
        return None

    def get_settings(self):
        return self.on_state if self.physical_on else self.off_state


class RecoveringNoneResponseToggleClient(NoneResponseToggleClient):
    def __init__(self, off_state, on_state, error_type):
        super().__init__(off_state, on_state)
        self.error_type = error_type
        self.settings_calls = 0

    def get_settings(self):
        self.settings_calls += 1
        if self.settings_calls == 1:
            raise self.error_type("settings timeout")
        return super().get_settings()


class AttemptRecordingLock:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.attempts = 0
        self.second_attempt = asyncio.Event()

    async def __aenter__(self):
        self.attempts += 1
        if self.attempts == 2:
            self.second_attempt.set()
        await self._lock.acquire()

    async def __aexit__(self, _exc_type, _exc, _traceback):
        self._lock.release()


def test_periodic_read_and_color_write_share_one_io_lock(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    async def exercise_overlap():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        command_lock = AttemptRecordingLock()
        coordinator._command_lock = command_lock
        client = OverlapDetectingClient()
        coordinator.client = client

        read_task = asyncio.create_task(coordinator._async_update_data())
        while not client.read_started.is_set():
            await asyncio.sleep(0.001)

        write_task = asyncio.create_task(coordinator._run_command(client.set_color, 1, 2, 3))
        await asyncio.wait_for(command_lock.second_attempt.wait(), timeout=1)
        write_started_while_read_active = client.write_started.is_set()

        client.release_read.set()
        await asyncio.gather(read_task, write_task)
        return write_started_while_read_active, client.max_active_calls

    write_overlapped_read, max_active_calls = asyncio.run(exercise_overlap())

    assert not write_overlapped_read
    assert max_active_calls == 1


def test_periodic_read_cannot_enter_color_settle_gap(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    async def exercise_settle_gap():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0
        coordinator.data = coordinator_module.Sp108eSettings(
            power_raw=1,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )
        client = SettleGapClient(coordinator.data)
        coordinator.client = client

        turn_on = asyncio.create_task(coordinator.async_turn_on(rgb_color=(255, 247, 5)))
        async with asyncio.timeout(1):
            while not client.color_started.is_set():
                await asyncio.sleep(0.001)

        periodic_read = asyncio.create_task(coordinator._async_update_data())
        await asyncio.sleep(0.01)
        periodic_completed_during_settle = periodic_read.done()
        await asyncio.gather(turn_on, periodic_read)
        return periodic_completed_during_settle, client

    periodic_completed_early, client = asyncio.run(exercise_settle_gap())
    assert not periodic_completed_early
    assert client.write_time is not None
    assert client.read_times[0] - client.write_time >= 0.045


def test_consecutive_fire_and_forget_writes_are_paced(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    async def exercise_consecutive_writes():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0
        coordinator.data = coordinator_module.Sp108eSettings(
            power_raw=1,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )
        client = ConsecutiveWriteClient(coordinator.data)
        coordinator.client = client
        await coordinator.async_turn_on(
            effect=coordinator_module.SOLID_EFFECT,
            brightness=242,
            rgb_color=(255, 29, 0),
        )
        return client

    client = asyncio.run(exercise_consecutive_writes())
    assert [name for name, _timestamp in client.events] == ["mode", "brightness", "color"]
    gaps = [later[1] - earlier[1] for earlier, later in zip(client.events, client.events[1:])]
    assert all(gap >= 0.045 for gap in gaps)
    assert client.state.brightness_raw == 242
    assert client.state.color_rgb == (255, 29, 0)


def test_zero_debounce_turn_on_waits_for_color_write(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    async def exercise_turn_on():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0
        coordinator.data = coordinator_module.Sp108eSettings(
            power_raw=1,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )
        client = BlockingColorClient(coordinator.data)
        coordinator.client = client

        async def refresh():
            return None

        coordinator.async_request_refresh = refresh
        turn_on_task = asyncio.create_task(coordinator.async_turn_on(rgb_color=(255, 180, 0)))
        async with asyncio.timeout(1):
            while not client.color_started.is_set():
                await asyncio.sleep(0.001)

        returned_before_write_finished = turn_on_task.done()
        client.release_color.set()
        await turn_on_task
        if coordinator._pending_color_task is not None:
            await coordinator._pending_color_task
        return returned_before_write_finished

    assert not asyncio.run(exercise_turn_on())


def test_zero_debounce_waits_before_readback_and_retries_once_on_mismatch(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    async def exercise_dropped_color():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0
        initial_state = coordinator_module.Sp108eSettings(
            power_raw=1,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )
        coordinator.data = initial_state
        client = DroppedFirstColorClient(initial_state)
        coordinator.client = client

        async def refresh():
            coordinator.async_set_updated_data(client.get_settings())

        coordinator.async_request_refresh = refresh
        await coordinator.async_turn_on(rgb_color=(255, 247, 5))
        return client, coordinator.data

    client, final_state = asyncio.run(exercise_dropped_color())
    assert client.set_color_calls == 2
    assert client.settings_calls == 2
    assert client.state.color_rgb == (255, 247, 5)
    assert final_state.color_rgb == (255, 247, 5)
    assert all(read - write >= 0.045 for write, read in zip(client.write_times, client.read_times, strict=True))


def test_replacing_inflight_debounced_color_keeps_io_serialized(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    async def exercise_replacement():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0.001
        client = ReplacementColorClient()
        coordinator.client = client

        async def refresh():
            return None

        coordinator.async_request_refresh = refresh
        coordinator._schedule_color((10, 20, 30))
        first_task = coordinator._pending_color_task
        async with asyncio.timeout(1):
            while not client.first_color_started.is_set():
                await asyncio.sleep(0.001)

        coordinator._schedule_color((40, 50, 60))
        second_task = coordinator._pending_color_task
        try:
            async with asyncio.timeout(0.05):
                while not client.second_color_started.is_set():
                    await asyncio.sleep(0.001)
        except TimeoutError:
            pass

        second_started_before_first_finished = client.second_color_started.is_set()
        client.release_first_color.set()
        if first_task is not None:
            with suppress(asyncio.CancelledError):
                await first_task
        if second_task is not None:
            await second_task
        return (
            second_started_before_first_finished,
            client.max_active_calls,
            client.physical_color,
        )

    second_started_early, max_active_calls, physical_color = asyncio.run(exercise_replacement())
    assert not second_started_early
    assert max_active_calls == 1
    assert physical_color == (40, 50, 60)


def test_turn_on_uses_toggle_response_as_current_power_state(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    def settings(power_raw):
        return coordinator_module.Sp108eSettings(
            power_raw=power_raw,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )

    async def exercise_two_colors():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0
        off_state = settings(0)
        on_state = settings(1)
        coordinator.data = off_state
        client = ToggleStateClient(off_state, on_state)
        coordinator.client = client

        async def refresh():
            return None

        coordinator.async_request_refresh = refresh
        await coordinator.async_turn_on(rgb_color=(0, 0, 255))
        await coordinator.async_turn_on(rgb_color=(255, 180, 0))
        return coordinator.data.is_on, client.toggle_count

    is_on, toggle_count = asyncio.run(exercise_two_colors())
    assert is_on
    assert toggle_count == 1


def test_concurrent_turn_on_calls_toggle_power_once(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    def settings(power_raw):
        return coordinator_module.Sp108eSettings(
            power_raw=power_raw,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )

    async def exercise_concurrent_turn_on():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0
        off_state = settings(0)
        on_state = settings(1)
        coordinator.data = off_state
        client = BlockingToggleStateClient(off_state, on_state)
        coordinator.client = client
        command_lock = AttemptRecordingLock()
        coordinator._command_lock = command_lock

        async def refresh():
            return None

        coordinator.async_request_refresh = refresh
        first = asyncio.create_task(coordinator.async_turn_on(rgb_color=(0, 0, 255)))
        while not client.first_toggle_started.is_set():
            await asyncio.sleep(0.001)
        second = asyncio.create_task(coordinator.async_turn_on(rgb_color=(255, 180, 0)))
        try:
            await asyncio.wait_for(command_lock.second_attempt.wait(), timeout=0.05)
        except TimeoutError:
            pass
        client.release_first_toggle.set()
        await asyncio.gather(first, second)
        return coordinator.data.is_on, client.toggle_count

    is_on, toggle_count = asyncio.run(exercise_concurrent_turn_on())
    assert is_on
    assert toggle_count == 1


def test_turn_off_uses_toggle_response_as_current_power_state(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    def settings(power_raw):
        return coordinator_module.Sp108eSettings(
            power_raw=power_raw,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )

    async def exercise_turn_off():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        off_state = settings(0)
        on_state = settings(1)
        coordinator.data = on_state
        client = ToggleStateClient(off_state, on_state)
        client.toggle_count = 1
        initial_toggle_count = client.toggle_count
        coordinator.client = client

        async def refresh():
            return None

        coordinator.async_request_refresh = refresh
        await coordinator.async_turn_off()
        return coordinator.data.is_on, client.toggle_count - initial_toggle_count

    is_on, toggle_calls = asyncio.run(exercise_turn_off())
    assert not is_on
    assert toggle_calls == 1


def test_none_toggle_response_is_refreshed_before_next_turn_on(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    def settings(power_raw):
        return coordinator_module.Sp108eSettings(
            power_raw=power_raw,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )

    async def exercise_none_response():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0.25
        off_state = settings(0)
        on_state = settings(1)
        coordinator.data = off_state
        client = NoneResponseToggleClient(off_state, on_state)
        coordinator.client = client

        async def refresh():
            return None

        coordinator.async_request_refresh = refresh
        await coordinator.async_turn_on(rgb_color=(0, 0, 255))
        await coordinator.async_turn_on(rgb_color=(255, 180, 0))
        coordinator.cancel_pending_color()
        return coordinator.data.is_on, client.physical_on, client.toggle_count

    coordinator_on, physical_on, toggle_count = asyncio.run(exercise_none_response())
    assert coordinator_on
    assert physical_on
    assert toggle_count == 1


def test_cancelled_turn_on_does_not_release_power_transaction(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    def settings(power_raw):
        return coordinator_module.Sp108eSettings(
            power_raw=power_raw,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )

    async def exercise_cancellation():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0
        off_state = settings(0)
        on_state = settings(1)
        coordinator.data = off_state
        client = BlockingToggleStateClient(off_state, on_state)
        coordinator.client = client

        async def refresh():
            return None

        coordinator.async_request_refresh = refresh
        first = asyncio.create_task(coordinator.async_turn_on(rgb_color=(0, 0, 255)))
        while not client.first_toggle_started.is_set():
            await asyncio.sleep(0.001)
        first.cancel()
        with suppress(asyncio.CancelledError):
            await first
        second = asyncio.create_task(coordinator.async_turn_on(rgb_color=(255, 180, 0)))
        try:
            async with asyncio.timeout(0.05):
                while not client.second_toggle_started.is_set():
                    await asyncio.sleep(0.001)
        except TimeoutError:
            pass
        client.release_first_toggle.set()
        await second
        return coordinator.data.is_on, client.toggle_count

    is_on, toggle_count = asyncio.run(exercise_cancellation())
    assert is_on
    assert toggle_count == 1


def test_failed_toggle_readback_is_reconciled_before_retry(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    def settings(power_raw):
        return coordinator_module.Sp108eSettings(
            power_raw=power_raw,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )

    async def exercise_failed_readback():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0
        off_state = settings(0)
        on_state = settings(1)
        coordinator.data = off_state
        client = RecoveringNoneResponseToggleClient(off_state, on_state, coordinator_module.Sp108eError)
        coordinator.client = client

        async def refresh():
            return None

        coordinator.async_request_refresh = refresh
        with suppress(coordinator_module.UpdateFailed):
            await coordinator.async_turn_on(rgb_color=(0, 0, 255))
        await coordinator.async_turn_on(rgb_color=(255, 180, 0))
        return (
            coordinator.data.is_on,
            client.physical_on,
            client.toggle_count,
            client.settings_calls,
        )

    coordinator_on, physical_on, toggle_count, settings_calls = asyncio.run(exercise_failed_readback())
    assert coordinator_on
    assert physical_on
    assert toggle_count == 1
    assert settings_calls == 3  # Failed toggle readback, power reconciliation, verified color readback.


def test_shutdown_drains_inflight_color_before_replacement_coordinator(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    async def exercise_reload():
        old = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        old.color_debounce = 0.001
        client = ReplacementColorClient()
        old.client = client

        async def refresh():
            return None

        old.async_request_refresh = refresh
        old._schedule_color((10, 20, 30))
        async with asyncio.timeout(1):
            while not client.first_color_started.is_set():
                await asyncio.sleep(0.001)

        try:
            shutdown_task = asyncio.create_task(old.async_shutdown())
        except AttributeError:
            client.release_first_color.set()
            raise
        async with asyncio.timeout(1):
            while not old._shutdown_started:
                await asyncio.sleep(0.001)
        late_operation_rejected = False
        try:
            await old.async_turn_on(rgb_color=(70, 80, 90))
        except coordinator_module.UpdateFailed:
            late_operation_rejected = True
        await asyncio.sleep(0.01)
        shutdown_waited_for_color = not shutdown_task.done()
        client.release_first_color.set()
        await shutdown_task

        replacement = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        replacement.client = client
        await replacement._run_command(client.set_color, 40, 50, 60)
        return (
            shutdown_waited_for_color,
            old.base_shutdown_called,
            late_operation_rejected,
            client.max_active_calls,
            client.physical_color,
        )

    shutdown_waited, base_shutdown_called, late_rejected, max_active_calls, physical_color = asyncio.run(exercise_reload())
    assert shutdown_waited
    assert base_shutdown_called
    assert late_rejected
    assert max_active_calls == 1
    assert physical_color == (40, 50, 60)


def test_shutdown_drains_cancelled_toggle_before_replacement_coordinator(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    def settings(power_raw):
        return coordinator_module.Sp108eSettings(
            power_raw=power_raw,
            effect_raw=coordinator_module.EFFECTS[coordinator_module.SOLID_EFFECT],
            speed_raw=1,
            brightness_raw=255,
            ic_type_raw=1,
            led_count=1,
            segment_count=1,
            color_rgb=(0, 0, 255),
            color_order_raw=1,
            recorded_patterns_raw=0,
            white_brightness_raw=0,
        )

    async def exercise_reload():
        old = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        old.color_debounce = 0
        off_state = settings(0)
        on_state = settings(1)
        old.data = off_state
        client = BlockingToggleStateClient(off_state, on_state)
        old.client = client

        async def refresh():
            return None

        old.async_request_refresh = refresh
        caller = asyncio.create_task(old.async_turn_on(rgb_color=(0, 0, 255)))
        async with asyncio.timeout(1):
            while not client.first_toggle_started.is_set():
                await asyncio.sleep(0.001)
        caller.cancel()
        with suppress(asyncio.CancelledError):
            await caller

        try:
            shutdown_task = asyncio.create_task(old.async_shutdown())
        except AttributeError:
            client.release_first_toggle.set()
            raise
        await asyncio.sleep(0.01)
        shutdown_waited_for_toggle = not shutdown_task.done()
        client.release_first_toggle.set()
        await shutdown_task

        replacement = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        replacement.color_debounce = 0
        replacement.client = client
        replacement.async_request_refresh = refresh
        replacement.data = await replacement._run_command(client.get_settings)
        await replacement.async_turn_on(rgb_color=(255, 180, 0))
        return shutdown_waited_for_toggle, replacement.data.is_on, client.toggle_count

    shutdown_waited, is_on, toggle_count = asyncio.run(exercise_reload())
    assert shutdown_waited
    assert is_on
    assert toggle_count == 1


def test_shutdown_drains_complete_speed_operation(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    async def exercise_shutdown():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        client = BlockingSpeedClient()
        coordinator.client = client
        refresh_started = asyncio.Event()
        release_refresh = asyncio.Event()

        async def refresh():
            refresh_started.set()
            await release_refresh.wait()

        coordinator.async_request_refresh = refresh
        speed_task = asyncio.create_task(coordinator.async_set_speed(120))
        async with asyncio.timeout(1):
            while not client.speed_started.is_set():
                await asyncio.sleep(0.001)
        shutdown_task = asyncio.create_task(coordinator.async_shutdown())
        client.release_speed.set()
        await asyncio.wait_for(refresh_started.wait(), timeout=1)
        shutdown_waited_for_parent = not shutdown_task.done()
        release_refresh.set()
        await asyncio.gather(speed_task, shutdown_task)
        return shutdown_waited_for_parent

    assert asyncio.run(exercise_shutdown())


def test_cancelled_shutdown_waiter_cannot_abandon_inflight_io(monkeypatch):
    coordinator_module = load_coordinator_module(monkeypatch)

    async def exercise_shutdown_cancellation():
        coordinator = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        coordinator.color_debounce = 0.001
        client = ReplacementColorClient()
        coordinator.client = client

        async def refresh():
            return None

        coordinator.async_request_refresh = refresh
        coordinator._schedule_color((10, 20, 30))
        async with asyncio.timeout(1):
            while not client.first_color_started.is_set():
                await asyncio.sleep(0.001)

        first_waiter = asyncio.create_task(coordinator.async_shutdown())
        async with asyncio.timeout(1):
            while not coordinator._shutdown_started:
                await asyncio.sleep(0.001)
        first_waiter.cancel()
        with suppress(asyncio.CancelledError):
            await first_waiter

        second_waiter = asyncio.create_task(coordinator.async_shutdown())
        await asyncio.sleep(0.01)
        second_waiter_returned_before_io = second_waiter.done()
        client.release_first_color.set()
        await second_waiter

        replacement = coordinator_module.Sp108eDataUpdateCoordinator(FakeHass(), FakeEntry())
        replacement.client = client
        await replacement._run_command(client.set_color, 40, 50, 60)
        return (
            second_waiter_returned_before_io,
            coordinator._shutdown_complete,
            client.max_active_calls,
            client.physical_color,
        )

    returned_early, shutdown_complete, max_active_calls, physical_color = asyncio.run(exercise_shutdown_cancellation())
    assert not returned_early
    assert shutdown_complete
    assert max_active_calls == 1
    assert physical_color == (40, 50, 60)
