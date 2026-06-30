"""Constants for the SP108E Local integration."""

from __future__ import annotations

DOMAIN = "sp108e_local"

CONF_TIMEOUT = "timeout"
CONF_DEVICE_NAME = "device_name"
CONF_COLOR_DEBOUNCE = "color_debounce"
CONF_RGB_ORDER = "rgb_order"

DEFAULT_NAME = "SP108E Controller"
DEFAULT_HOST = "192.0.2.10"
DEFAULT_PORT = 8189
DEFAULT_TIMEOUT = 2.0
DEFAULT_SCAN_INTERVAL = 10
DEFAULT_COLOR_DEBOUNCE = 0.25
DEFAULT_RGB_ORDER = "RGB"
RGB_ORDERS = ("RGB", "RBG", "GRB", "GBR", "BRG", "BGR")
