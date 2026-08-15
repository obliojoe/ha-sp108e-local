from __future__ import annotations

import asyncio
import importlib
import sys
import threading
import types
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
