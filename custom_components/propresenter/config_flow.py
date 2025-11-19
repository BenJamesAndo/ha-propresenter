"""Config flow for ProPresenter integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import ProPresenterAPI, ProPresenterConnectionError
from .const import CONF_PORT, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    _LOGGER.debug(
        "Validating input: host=%s, port=%s", data[CONF_HOST], data[CONF_PORT]
    )
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
            _LOGGER.warning(
                "ProPresenter version information not available. Response: %s",
                version_info,
            )
            raise CannotConnect("Unable to determine ProPresenter version")

        # Parse version from host_description (e.g., "ProPresenter 19.0.1" -> "19.0.1")
        version_str = host_description.replace("ProPresenter ", "").strip()

        if not version_str:
            _LOGGER.warning(
                "Could not extract version from host_description: %s", host_description
            )
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
            raise CannotConnect(
                f"Could not validate ProPresenter version: {version_str}"
            ) from err

        # Extract useful info for the title
        name = version_info.get("name", "ProPresenter")

        _LOGGER.debug("Successfully connected to %s version %s", name, version_str)

        return {
            "title": f"{name} ({data[CONF_HOST]})",
            "name": name,
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
                        info.get("version", "Unknown"),
                    )

                # Update the config entry with new data
                return self.async_update_reload_and_abort(
                    entry, data=user_input, reason="reconfigure_successful"
                )

        # Pre-fill form with current values
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST)): str,
                    vol.Required(
                        CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)
                    ): int,
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
                # Use device name as unique_id (matches zeroconf pattern for consistency)
                device_name = info.get("name", "ProPresenter")
                await self.async_set_unique_id(device_name)

                # Auto-update IP if device already configured
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_HOST: user_input[CONF_HOST],
                    }
                )

                # Log warning if version is old
                version_tuple = info.get("version_tuple")
                if version_tuple and version_tuple[0] < 19:
                    _LOGGER.warning(
                        "ProPresenter version %s detected. This integration works best with v19 or higher. "
                        "Older versions may have limited functionality.",
                        info.get("version", "Unknown"),
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

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        import asyncio
        import ipaddress

        port = discovery_info.port or DEFAULT_PORT

        # Get all IP addresses from discovery info
        # discovery_info.addresses contains all IPs as bytes
        ip_candidates = []
        if hasattr(discovery_info, "addresses") and discovery_info.addresses:
            for addr_bytes in discovery_info.addresses:
                try:
                    ip_obj = ipaddress.ip_address(addr_bytes)
                    ip = str(ip_obj)
                    # Filter out IPv6 and link-local
                    if ip_obj.version == 6:
                        _LOGGER.debug(
                            "ProPresenter discovery: Skipping IPv6 address: %s", ip
                        )
                        continue
                    ip_candidates.append(ip)
                except (ValueError, OSError):
                    continue

        # Fallback to single host if addresses not available
        if not ip_candidates and discovery_info.host:
            ip_candidates = [discovery_info.host]

        if not ip_candidates:
            return self.async_abort(reason="no_host")

        # Race all IPs - whichever connects first wins (usually Ethernet due to lower latency)
        _LOGGER.debug(
            "ProPresenter discovery: Racing connection to %d IPs: %s",
            len(ip_candidates),
            ip_candidates,
        )

        async def try_connection(ip: str):
            """Try connecting to a specific IP."""
            try:
                info = await validate_input(
                    self.hass,
                    {
                        CONF_HOST: ip,
                        CONF_PORT: port,
                    },
                )
                return (ip, info)
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.debug("ProPresenter discovery: %s failed: %s", ip, err)
                return None

        # Create tasks for all IPs and race them
        tasks = [asyncio.create_task(try_connection(ip)) for ip in ip_candidates]

        # Use asyncio.as_completed to get first successful connection
        ip_address = None
        info = None

        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result is not None:
                ip_address, info = result
                _LOGGER.info(
                    "ProPresenter discovery: Connected to %s (won race against %s)",
                    ip_address,
                    [ip for ip in ip_candidates if ip != ip_address],
                )
                # Cancel remaining tasks
                for task in tasks:
                    if not task.done():
                        task.cancel()
                break

        if not ip_address or not info:
            return self.async_abort(reason="cannot_connect")

        device_name = info.get("name", "ProPresenter")
        await self.async_set_unique_id(device_name)

        existing_entries = self._async_current_entries(include_ignore=False)
        for entry in existing_entries:
            if entry.unique_id == device_name:
                new_data = entry.data.copy()
                if new_data.get(CONF_HOST) != ip_address:
                    new_data[CONF_HOST] = ip_address
                    self.hass.config_entries.async_update_entry(entry, data=new_data)

                return self.async_abort(reason="already_configured")

        self.context.update(
            {
                "title_placeholders": {"name": device_name},
                "_discovered_host": ip_address,
                "_discovered_port": port,
                "_discovered_name": device_name,
            }
        )

        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm zeroconf discovery."""
        name = self.context.get("_discovered_name", "ProPresenter")
        host = self.context.get("_discovered_host")
        port = self.context.get("_discovered_port")

        if user_input is not None:
            return self.async_create_entry(
                title=name,
                data={
                    CONF_HOST: host,
                    CONF_PORT: port,
                },
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": name},
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
