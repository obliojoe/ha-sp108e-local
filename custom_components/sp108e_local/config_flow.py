"""Config flow for SP108E Local."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from .const import (
    CONF_COLOR_DEBOUNCE,
    CONF_DEVICE_NAME,
    CONF_RGB_ORDER,
    CONF_TIMEOUT,
    DEFAULT_COLOR_DEBOUNCE,
    DEFAULT_HOST,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_RGB_ORDER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    RGB_ORDERS,
)
from .protocol import Sp108eClient, Sp108eError


class CannotConnect(Exception):
    """Raised when the controller cannot be reached during setup."""


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10)),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
        vol.Optional(CONF_COLOR_DEBOUNCE, default=DEFAULT_COLOR_DEBOUNCE): vol.All(vol.Coerce(float), vol.Range(min=0, max=2)),
        vol.Optional(CONF_RGB_ORDER, default=DEFAULT_RGB_ORDER): vol.In(RGB_ORDERS),
    }
)


def _validate_input(data: dict[str, Any]) -> dict[str, str]:
    client = Sp108eClient(
        data[CONF_HOST],
        data.get(CONF_PORT, DEFAULT_PORT),
        data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
    )
    try:
        device_name = client.get_name()
        client.get_settings()
    except Sp108eError as err:
        raise CannotConnect(str(err)) from err

    return {
        CONF_DEVICE_NAME: device_name or "",
        "title": data.get(CONF_NAME) or device_name or DEFAULT_NAME,
    }


def _schema_from_values(values: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=values.get(CONF_HOST, DEFAULT_HOST)): str,
            vol.Optional(CONF_PORT, default=values.get(CONF_PORT, DEFAULT_PORT)): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Optional(CONF_NAME, default=values.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Optional(
                CONF_TIMEOUT,
                default=values.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10)),
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            vol.Optional(
                CONF_COLOR_DEBOUNCE,
                default=values.get(CONF_COLOR_DEBOUNCE, DEFAULT_COLOR_DEBOUNCE),
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=2)),
            vol.Optional(
                CONF_RGB_ORDER,
                default=values.get(CONF_RGB_ORDER, DEFAULT_RGB_ORDER),
            ): vol.In(RGB_ORDERS),
        }
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SP108E Local."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await self.hass.async_add_executor_job(_validate_input, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                user_input[CONF_DEVICE_NAME] = info[CONF_DEVICE_NAME]
                unique_id = info[CONF_DEVICE_NAME] or (f"{user_input[CONF_HOST]}:{user_input.get(CONF_PORT, DEFAULT_PORT)}")
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle SP108E Local options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        values = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(_validate_input, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_schema_from_values(values),
            errors=errors,
        )


async def async_validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate input from tests or future options flows."""
    return await hass.async_add_executor_job(_validate_input, data)
