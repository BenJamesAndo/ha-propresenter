"""The ProPresenter integration.

This integration allows control of ProPresenter presentation software via its REST API.
It provides button entities for controlling slide navigation (next/previous) and
select entities for choosing stage screen layouts.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import ProPresenterCoordinator, ProPresenterStreamingCoordinator
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

# List of platforms to set up
PLATFORMS: list[Platform] = [
     Platform.BUTTON,
     Platform.IMAGE,
     Platform.MEDIA_PLAYER,
     Platform.SELECT,
     Platform.SWITCH,
     Platform.TEXT,
]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up ProPresenter from a config entry."""
    
    # Initialize the main coordinator that manages data updates from the API
    coordinator = ProPresenterCoordinator(hass, config_entry)
    
    # Perform an initial data load from API
    await coordinator.async_config_entry_first_refresh()
    
    # Test to see if API initialized correctly
    if not coordinator.data:
        raise ConfigEntryNotReady("Failed to connect to ProPresenter")
    
    # Initialize the streaming coordinator for dynamic presentation data
    streaming_coordinator = ProPresenterStreamingCoordinator(hass, coordinator.api, coordinator)
    await streaming_coordinator.async_config_entry_first_refresh()
    
    # Store all coordinators in config entry runtime data
    config_entry.runtime_data = {
        "coordinator": coordinator,
        "streaming_coordinator": streaming_coordinator,
    }
    
    # Store main coordinator in hass.data for service access
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = coordinator
    
    # Set up services (only once)
    if not hass.services.has_service(DOMAIN, "show_message"):
        async_setup_services(hass)
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    
    # Start streaming in background (uses asyncio.create_task so HA doesn't wait for it)
    await streaming_coordinator.start_streaming()
    
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    
    if unload_ok:
        # Remove from hass.data
        hass.data[DOMAIN].pop(config_entry.entry_id, None)
        
        # Unload services if this is the last entry
        if not hass.data[DOMAIN]:
            async_unload_services(hass)
        
        # Close coordinators and streaming connections
        coordinators = config_entry.runtime_data
        coordinator: ProPresenterCoordinator = coordinators["coordinator"]
        streaming_coordinator: ProPresenterStreamingCoordinator = coordinators["streaming_coordinator"]
        
        await streaming_coordinator.async_shutdown()
        await coordinator.async_shutdown()
    
    return unload_ok
