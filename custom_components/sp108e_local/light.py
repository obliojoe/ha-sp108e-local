"""Light platform for SP108E Local."""

from __future__ import annotations

from typing import Any

import homeassistant.util.color as color_util
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Sp108eDataUpdateCoordinator
from .effects import EFFECT_NAMES_BY_VALUE, EFFECTS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SP108E light entity."""
    coordinator: Sp108eDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Sp108eLight(coordinator)])


class Sp108eLight(CoordinatorEntity[Sp108eDataUpdateCoordinator], LightEntity):
    """SP108E RGB light."""

    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, coordinator: Sp108eDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_light"
        self._attr_name = coordinator.display_name

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
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.is_on

    @property
    def brightness(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.brightness_raw

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self.coordinator.rgb_color_for_ha()

    @property
    def color_mode(self) -> ColorMode | None:
        return ColorMode.RGB

    @property
    def effect_list(self) -> list[str]:
        return list(EFFECTS)

    @property
    def effect(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return EFFECT_NAMES_BY_VALUE.get(self.coordinator.data.effect_raw)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "power_raw": data.power_raw,
            "effect_raw": data.effect_raw,
            "speed_raw": data.speed_raw,
            "brightness_raw": data.brightness_raw,
            "ic_type_raw": data.ic_type_raw,
            "led_count": data.led_count,
            "segment_count": data.segment_count,
            "color_hex": data.color_hex,
            "color_order_raw": data.color_order_raw,
            "recorded_patterns_raw": data.recorded_patterns_raw,
            "white_brightness_raw": data.white_brightness_raw,
            "rgb_order_override": self.coordinator.rgb_order,
            "color_debounce": self.coordinator.color_debounce,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        rgb_color = kwargs.get(ATTR_RGB_COLOR)
        if rgb_color is None and ATTR_HS_COLOR in kwargs:
            hue, saturation = kwargs[ATTR_HS_COLOR]
            rgb_color = color_util.color_hs_to_RGB(hue, saturation)
        effect = kwargs.get(ATTR_EFFECT)
        await self.coordinator.async_turn_on(
            brightness=brightness,
            rgb_color=rgb_color,
            effect=effect,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_turn_off()
