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
        
        _LOGGER.debug("Version info response: %s", version_info)
        
        if not version_info:
            _LOGGER.error("Failed to get version information from ProPresenter")
            raise CannotConnect("Failed to get version information")
        
        # Extract version string from host_description (format: "ProPresenter 19.0.1")
        host_description = version_info.get("host_description", "")
        
        if not host_description or not host_description.startswith("ProPresenter"):
            _LOGGER.warning("ProPresenter version information not available. Response: %s", version_info)
            raise CannotConnect("Unable to determine ProPresenter version")
        
        # Parse version from host_description (e.g., "ProPresenter 19.0.1" -> "19.0.1")
        version_str = host_description.replace("ProPresenter ", "").strip()
        
        if not version_str:
            _LOGGER.warning("Could not extract version from host_description: %s", host_description)
            raise CannotConnect("Unable to determine ProPresenter version")
        
        # Parse version (format: "19.0.1" or similar)
        version_info_parsed = None
        try:
            version_parts = version_str.split(".")
            major = int(version_parts[0])
            minor = int(version_parts[1]) if len(version_parts) > 1 else 0
            patch = int(version_parts[2]) if len(version_parts) > 2 else 0
            version_info_parsed = (major, minor, patch)
        except (ValueError, IndexError) as err:
            _LOGGER.warning("Could not parse ProPresenter version: %s", version_str)
            raise CannotConnect(f"Could not validate ProPresenter version: {version_str}") from err
            
        # Extract useful info for the title
        name = version_info.get("name", "ProPresenter")
        
        _LOGGER.debug("Successfully connected to %s version %s", name, version_str)
        
        # Note: Version warnings (e.g., < v19) are handled at the next step
        return {
            "title": f"{name} ({data[CONF_HOST]})",
            "version": version_str,
            "version_tuple": version_info_parsed,  # Pass parsed version for later checks
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
                # Log warning if version is old
                version_tuple = info.get("version_tuple")
                if version_tuple and version_tuple[0] < 19:
                    _LOGGER.warning(
                        "ProPresenter version %s detected. This integration works best with v19 or higher. "
                        "Older versions may have limited functionality.",
                        info.get("version", "Unknown")
                    )
                
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

                # Log warning if version is old
                version_tuple = info.get("version_tuple")
                if version_tuple and version_tuple[0] < 19:
                    _LOGGER.warning(
                        "ProPresenter version %s detected. This integration works best with v19 or higher. "
                        "Older versions may have limited functionality.",
                        info.get("version", "Unknown")
                    )

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
