"""Services for ProPresenter integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SERVICE_SHOW_MESSAGE
from .coordinator import ProPresenterCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH_CACHE = "refresh_presentation_cache"

# Service schema for show_message
SHOW_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("tokens", default={}): vol.Schema({cv.string: cv.string}),
    }
)


def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for ProPresenter integration."""

    async def async_show_message(call: ServiceCall) -> None:
        """Handle the show_message service call."""
        message_identifier = call.data.get("message")
        tokens = call.data.get("tokens", {})
        
        if not message_identifier:
            _LOGGER.error("Message UUID or name is required")
            return
        
        _LOGGER.debug("Show message service called: message=%s, tokens=%s", message_identifier, tokens)
        
        # Find all ProPresenter integrations
        found = False
        for entry_id in hass.data.get(DOMAIN, {}):
            coordinator: ProPresenterCoordinator = hass.data[DOMAIN][entry_id]
            
            # Find the message by UUID or name
            messages = coordinator.data.get("messages", [])
            for message in messages:
                message_data = message.get("id", {})
                message_uuid = message_data.get("uuid")
                message_name = message_data.get("name")
                
                # Check if identifier matches UUID or name
                if message_uuid == message_identifier or message_name == message_identifier:
                    # Build token structure matching ProPresenter's format
                    # Need to match token names with their UUIDs from the message definition
                    token_data = {}
                    if tokens:
                        message_tokens = message.get("tokens", [])
                        for token_name, token_value in tokens.items():
                            # Find the token UUID
                            for msg_token in message_tokens:
                                if msg_token.get("name") == token_name:
                                    token_data[token_name] = token_value
                                    break
                    
                    # Show the message with tokens if provided
                    await coordinator.api.show_message(message_uuid, token_data if token_data else None)
                    await coordinator.async_request_refresh()
                    
                    _LOGGER.info("Showed message: %s (UUID: %s) with tokens: %s", 
                               message_name, message_uuid, token_data)
                    found = True
                    break
            
            if found:
                break
        
        if not found:
            _LOGGER.error("Message not found: %s", message_identifier)

    # Register the service
    hass.services.async_register(
        DOMAIN,
        SERVICE_SHOW_MESSAGE,
        async_show_message,
        schema=SHOW_MESSAGE_SCHEMA,
    )

    async def async_refresh_presentation_cache(call: ServiceCall) -> None:
        """Force refresh presentation and playlist caches."""
        _LOGGER.info("Refreshing presentation and playlist caches via service call")
        
        for entry_id in hass.data.get(DOMAIN, {}):
            coordinator: ProPresenterCoordinator = hass.data[DOMAIN][entry_id]
            
            # Invalidate playlist cache in coordinator
            coordinator.invalidate_playlist_cache()
            
            # Request coordinator refresh to fetch new data
            await coordinator.async_request_refresh()
            
        _LOGGER.info("Cache refresh completed - coordinator playlist caches invalidated and refreshed")
        _LOGGER.info("Note: Sensor presentation caches will auto-refresh when presentation changes")

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_CACHE,
        async_refresh_presentation_cache,
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Unload ProPresenter services."""
    hass.services.async_remove(DOMAIN, SERVICE_SHOW_MESSAGE)
    hass.services.async_remove(DOMAIN, SERVICE_REFRESH_CACHE)
