"""Base entity for ProPresenter integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProPresenterCoordinator


def get_device_info(
    coordinator: ProPresenterCoordinator, config_entry: ConfigEntry
) -> DeviceInfo:
    """Get device info for ProPresenter entities.

    Args:
        coordinator: The static coordinator with version info
        config_entry: The config entry with connection details

    Returns:
        DeviceInfo object with ProPresenter device information
    """
    version_data = coordinator.data.get("version", {})
    host = version_data.get("host", config_entry.data["host"])
    name = version_data.get("name", "ProPresenter")
    port = config_entry.data.get("port", 51482)

    # Extract version from host_description (e.g., "ProPresenter 21.0" -> "21.0")
    host_description = version_data.get("host_description", "")
    version = "Unknown"
    if host_description.startswith("ProPresenter "):
        version = host_description.replace("ProPresenter ", "")

    # Add warning message if version is below recommended (v19)
    if version != "Unknown":
        try:
            version_clean = version.strip()
            version_parts = version_clean.split(".")
            major = int(version_parts[0])
            if major < 19:
                version = (
                    f"{version_clean} (limited functionality, upgrade to v19 or above)"
                )
        except (ValueError, IndexError):
            pass

    # Extract hardware platform (Windows/Mac)
    platform = version_data.get("platform", "Unknown")
    # Improve platform names
    platform_map = {
        "win": "Windows",
        "mac": "Mac",
    }
    platform = platform_map.get(platform, platform)

    return DeviceInfo(
        identifiers={(DOMAIN, config_entry.entry_id)},
        name=name,
        manufacturer="Renewed Vision",
        model="ProPresenter",
        sw_version=version,
        hw_version=platform,
        configuration_url=f"http://{host}:{port}/v1/control/",
    )


class ProPresenterBaseEntity(CoordinatorEntity):
    """Base entity for ProPresenter with common device info."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CoordinatorEntity,
        config_entry: ConfigEntry,
        static_coordinator: ProPresenterCoordinator | None = None,
    ) -> None:
        """Initialize the base entity.

        Args:
            coordinator: The coordinator this entity uses for updates
            config_entry: The config entry
            static_coordinator: Optional static coordinator for version info (if different from coordinator)
        """
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.static_coordinator = static_coordinator

        # Use static coordinator for device info if provided, otherwise use main coordinator
        device_info_coordinator = (
            static_coordinator if static_coordinator else coordinator
        )
        self._attr_device_info = get_device_info(device_info_coordinator, config_entry)
