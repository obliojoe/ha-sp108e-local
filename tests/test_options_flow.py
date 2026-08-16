from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path


def load_config_flow_module(monkeypatch):
    """Load config_flow with a current-HA-shaped OptionsFlow base."""
    voluptuous = types.ModuleType("voluptuous")
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    const = types.ModuleType("homeassistant.const")
    core = types.ModuleType("homeassistant.core")

    class ConfigFlow:
        def __init_subclass__(cls, **_kwargs):
            return super().__init_subclass__()

    class OptionsFlow:
        @property
        def config_entry(self):
            """Current HA exposes this as a read-only, post-init property."""
            return object()

    class HomeAssistant:
        pass

    def marker(key, **_kwargs):
        return key

    voluptuous.Schema = lambda value: value
    voluptuous.Required = marker
    voluptuous.Optional = marker
    voluptuous.All = lambda *values: values
    voluptuous.Coerce = lambda value: value
    voluptuous.Range = lambda **kwargs: kwargs
    voluptuous.In = lambda values: values

    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.ConfigEntry = object
    config_entries.ConfigFlowResult = dict
    const.CONF_HOST = "host"
    const.CONF_NAME = "name"
    const.CONF_PORT = "port"
    const.CONF_SCAN_INTERVAL = "scan_interval"
    core.HomeAssistant = HomeAssistant

    monkeypatch.setitem(sys.modules, "voluptuous", voluptuous)
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)
    monkeypatch.setitem(sys.modules, "homeassistant.const", const)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)

    package_name = "sp108e_local_config_flow_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(Path(__file__).parents[1] / "custom_components" / "sp108e_local")]
    monkeypatch.setitem(sys.modules, package_name, package)
    return importlib.import_module(f"{package_name}.config_flow")


def test_options_flow_can_be_created_with_read_only_config_entry(monkeypatch):
    config_flow = load_config_flow_module(monkeypatch)

    handler = config_flow.ConfigFlow.async_get_options_flow(object())

    assert isinstance(handler, config_flow.OptionsFlowHandler)
