"""Number platform for SP108E Local."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Sp108eDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SP108E number entities."""
    coordinator: Sp108eDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Sp108eSpeedNumber(coordinator)])


class Sp108eSpeedNumber(CoordinatorEntity[Sp108eDataUpdateCoordinator], NumberEntity):
    """Effect speed number entity."""

    _attr_native_min_value = 0
    _attr_native_max_value = 255
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: Sp108eDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_effect_speed"
        self._attr_name = f"{coordinator.entry.title} Effect Speed"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.unique_id)},
            manufacturer="SP108E",
            model="SP108E LED Controller",
            name=self.coordinator.display_name,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.speed_raw

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_speed(int(value))
