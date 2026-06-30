"""Color-order helpers for SP108E Local."""

from __future__ import annotations

from .const import DEFAULT_RGB_ORDER, RGB_ORDERS


def _validate_order(order: str) -> str:
    if order not in RGB_ORDERS:
        return DEFAULT_RGB_ORDER
    return order


def map_rgb_to_device(rgb: tuple[int, int, int], order: str) -> tuple[int, int, int]:
    """Map Home Assistant RGB to the byte order sent to the controller."""
    order = _validate_order(order)
    values = {"R": rgb[0], "G": rgb[1], "B": rgb[2]}
    return tuple(values[channel] for channel in order)


def map_rgb_from_device(device_rgb: tuple[int, int, int], order: str) -> tuple[int, int, int]:
    """Map controller bytes back to Home Assistant RGB."""
    order = _validate_order(order)
    values = dict(zip(order, device_rgb, strict=True))
    return values["R"], values["G"], values["B"]
