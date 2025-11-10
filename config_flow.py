"""Config flow for ProPresenter integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import ProPresenterAPI, ProPresenterConnectionError
from .const import CONF_PORT, CONF_REQUIRES_CONFIRMATION, DEFAULT_PORT, DEFAULT_REQUIRES_CONFIRMATION, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_REQUIRES_CONFIRMATION, default=DEFAULT_REQUIRES_CONFIRMATION): bool,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    _LOGGER.debug("Validating input: host=%s, port=%s", data[CONF_HOST], data[CONF_PORT])
    api = ProPresenterAPI(data[CONF_HOST], data[CONF_PORT])
    
    try:
        # Test the connection by getting version info
        version_info = await api.get_version()
        
        if not version_info:
            _LOGGER.error("Failed to get version information from ProPresenter")
            raise CannotConnect("Failed to get version information")
            
        # Extract useful info for the title
        name = version_info.get("name", "ProPresenter")
        version = version_info.get("version", "Unknown")
        
        _LOGGER.debug("Successfully connected to %s version %s", name, version)
        
        return {
            "title": f"{name} ({data[CONF_HOST]})",
            "version": version,
        }
    except ProPresenterConnectionError as err:
        _LOGGER.error("ProPresenter connection error: %s", err, exc_info=True)
        raise CannotConnect from err
    finally:
        await api.close()


class ProPresenterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ProPresenter."""

    VERSION = 1

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Update the config entry with new data
                return self.async_update_reload_and_abort(
                    entry,
                    data=user_input,
                    reason="reconfigure_successful"
                )

        # Pre-fill form with current values
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST)): str,
                    vol.Required(CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)): int,
                    vol.Optional(
                        CONF_REQUIRES_CONFIRMATION, 
                        default=entry.data.get(CONF_REQUIRES_CONFIRMATION, DEFAULT_REQUIRES_CONFIRMATION)
                    ): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Set unique ID based on host:port combination
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
