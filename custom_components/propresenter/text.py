"""Text platform for ProPresenter integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base import ProPresenterBaseEntity
from .const import DOMAIN
from .coordinator import ProPresenterCoordinator, ProPresenterStreamingCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ProPresenter text entities."""
    coordinator: ProPresenterCoordinator = config_entry.runtime_data["coordinator"]
    streaming_coordinator: ProPresenterStreamingCoordinator = config_entry.runtime_data["streaming_coordinator"]
    
    # Add stage message text entity
    entities = [ProPresenterStageMessageText(coordinator, streaming_coordinator, config_entry)]
    
    # Get messages from streaming coordinator data
    messages = streaming_coordinator.data.get("messages", [])
    
    # Create a text entity for each message token
    for message in messages:
        message_id = message.get("id", {})
        message_uuid = message_id.get("uuid") if isinstance(message_id, dict) else None
        message_name = message_id.get("name", "Unknown") if isinstance(message_id, dict) else "Unknown"
        
        # Get the tokens for this message
        tokens = message.get("tokens", [])
        
        for token in tokens:
            token_name = token.get("name")
            token_uuid = token.get("uuid")
            
            if message_uuid and token_name and token_uuid:
                entities.append(
                    ProPresenterMessageTokenText(
                        coordinator,
                        streaming_coordinator,
                        config_entry,
                        message_uuid,
                        message_name,
                        token_name,
                        token_uuid,
                    )
                )
    
    async_add_entities(entities)


class ProPresenterMessageTokenText(ProPresenterBaseEntity, TextEntity):
    """Text entity for a message token (dynamic text field)."""

    _attr_native_max = 255  # Max length for text input
    _attr_mode = "text"  # Single-line text input
    _attr_icon = "mdi:message-text"
    def __init__(
        self,
        static_coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        message_uuid: str,
        message_name: str,
        token_name: str,
        token_uuid: str,
    ) -> None:
        """Initialize the text entity."""
        super().__init__(streaming_coordinator, config_entry, static_coordinator=static_coordinator)
        self.api = static_coordinator.api  # Keep reference to API for actions
        self._message_uuid = message_uuid
        self._message_name = message_name
        self._token_name = token_name
        self._token_uuid = token_uuid
        self._attr_unique_id = f"{config_entry.entry_id}_message_{message_uuid}_token_{token_uuid}"
        self._attr_translation_key = "message_token"
        
        # Store the user-entered value locally (overrides ProPresenter value)
        self._local_value = None

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"{self._message_name} {self._token_name}"

    @property
    def native_value(self) -> str | None:
        """Return the current value of the token."""
        # If user has set a local value, use that (takes priority)
        if self._local_value is not None:
            return self._local_value
        
        # Otherwise, read from ProPresenter (for two-way sync)
        messages = self.coordinator.data.get("messages", [])
        for message in messages:
            message_id = message.get("id", {})
            message_uuid = message_id.get("uuid") if isinstance(message_id, dict) else None
            
            if message_uuid == self._message_uuid:
                tokens = message.get("tokens", [])
                for token in tokens:
                    if token.get("name") == self._token_name:
                        text_data = token.get("text", {})
                        if isinstance(text_data, dict):
                            return text_data.get("text", "")
                        return ""
        
        return ""

    async def async_set_value(self, value: str) -> None:
        """Update the token value."""
        # Store the value locally - it will be used when triggering the message
        # This takes priority over ProPresenter's stored value
        self._local_value = value
        self.async_write_ha_state()


class ProPresenterStageMessageText(ProPresenterBaseEntity, TextEntity):
    """Text entity for the stage message."""

    _attr_native_max = 255  # Standard text input max
    _attr_mode = "text"  # Single-line text input
    _attr_icon = "mdi:message-text-outline"
    _attr_name = "Stage Message"

    def __init__(
        self,
        static_coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the stage message text entity."""
        super().__init__(streaming_coordinator, config_entry, static_coordinator=static_coordinator)
        self.api = static_coordinator.api
        self._attr_unique_id = f"{config_entry.entry_id}_stage_message"
        self._local_text = ""  # Store user-entered text locally

    @property
    def native_value(self) -> str | None:
        """Return the current stage message, truncated if needed."""
        message = self.coordinator.data.get("stage_message", "")
        
        # If message is shown in ProPresenter, display it and update local storage
        if message:
            # Update local storage to match ProPresenter (for when it gets hidden)
            truncated_message = message
            if len(message) > self._attr_native_max:
                _LOGGER.warning(
                    "Stage message from ProPresenter is %d chars, truncating to %d",
                    len(message),
                    self._attr_native_max
                )
                truncated_message = message[:self._attr_native_max]
            
            # Keep local storage in sync with ProPresenter
            self._local_text = truncated_message
            return truncated_message
        
        # If message is hidden, show the locally stored text
        return self._local_text

    async def async_set_value(self, value: str) -> None:
        """Set the stage message text."""
        try:
            # Always store the value locally
            self._local_text = value
            
            # Check if the message is currently shown (visible)
            current_message = self.coordinator.data.get("stage_message", "")
            is_currently_shown = bool(current_message)
            
            # Only send to ProPresenter if the message is currently visible
            # This matches ProPresenter behavior: you type text, then click Show
            if is_currently_shown:
                # Message is visible, update it in real-time
                await self.api.set_stage_message(value)
            else:
                # Message is hidden, just update local storage
                # It will be sent when the switch is turned on
                self.async_write_ha_state()  # Update the UI
            
            # No need to refresh coordinator - streaming will update automatically
        except Exception as err:
            _LOGGER.error("Error setting stage message: %s", err, exc_info=True)
