"""Button platform for ProPresenter integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base import ProPresenterBaseEntity
from .coordinator import ProPresenterCoordinator, ProPresenterStreamingCoordinator

_LOGGER = logging.getLogger(__name__)

# Define available clear layers with icons for active/inactive states
CLEAR_LAYERS = {
    "audio": {
        "name": "Clear Audio",
        "icon_active": "mdi:volume-high",
        "icon_inactive": "mdi:volume-variant-off",
    },
    "messages": {
        "name": "Clear Messages",
        "icon_active": "mdi:send-circle",
        "icon_inactive": "mdi:send-circle-outline",
    },
    "props": {
        "name": "Clear Props",
        "icon_active": "mdi:layers-outline",
        "icon_inactive": "mdi:layers-off-outline",
    },
    "announcements": {
        "name": "Clear Announcements",
        "icon_active": "mdi:bullhorn-variant",
        "icon_inactive": "mdi:bullhorn-outline",
    },
    "slide": {
        "name": "Clear Slide",
        "icon_active": "mdi:text-box-outline",
        "icon_inactive": "mdi:text-box-remove-outline",
    },
    "media": {
        "name": "Clear Media",
        "icon_active": "mdi:play-box",
        "icon_inactive": "mdi:play-box-outline",
    },
    "video_input": {
        "name": "Clear Video Input",
        "icon_active": "mdi:video-box",
        "icon_inactive": "mdi:video-off-outline",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ProPresenter button entities."""
    coordinator: ProPresenterCoordinator = config_entry.runtime_data["coordinator"]
    streaming_coordinator: ProPresenterStreamingCoordinator = config_entry.runtime_data[
        "streaming_coordinator"
    ]

    # Create slide control button entities
    entities = [
        ProPresenterNextSlideButton(coordinator, config_entry),
        ProPresenterPreviousSlideButton(coordinator, config_entry),
        ProPresenterFindMyMouseButton(coordinator, config_entry),
    ]

    # Add clear layer buttons (using streaming coordinator for status)
    for layer_id, layer_info in CLEAR_LAYERS.items():
        entities.append(
            ProPresenterClearLayerButton(
                coordinator, streaming_coordinator, config_entry, layer_id, layer_info
            )
        )

    # Add Clear All button
    clear_groups = coordinator.data.get("clear_groups", [])
    for group in clear_groups:
        group_data = group.get("id", {})
        group_uuid = group_data.get("uuid")
        group_name = group_data.get("name")
        if group_uuid and group_name:
            entities.append(
                ProPresenterClearGroupButton(
                    coordinator, config_entry, group_uuid, group_name
                )
            )

    # Add timer reset buttons
    timers = coordinator.data.get("timers", [])
    for timer in timers:
        timer_data = timer.get("id", {})
        timer_uuid = timer_data.get("uuid")
        timer_name = timer_data.get("name")

        # Skip "Countdown to Time" timers as they're clock-based, not duration-based
        if timer.get("count_down_to_time"):
            continue

        if timer_uuid and timer_name:
            entities.append(
                ProPresenterTimerResetButton(
                    coordinator, config_entry, timer_uuid, timer_name
                )
            )

    async_add_entities(entities)


class ProPresenterButton(ProPresenterBaseEntity, ButtonEntity):
    """Base class for ProPresenter button entities."""

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, config_entry)


class ProPresenterNextSlideButton(ProPresenterButton):
    """Button to trigger the next slide in ProPresenter."""

    _attr_translation_key = "next_slide"
    _attr_icon = "mdi:arrow-right"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the next slide button."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_next_slide"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.trigger_next()


class ProPresenterPreviousSlideButton(ProPresenterButton):
    """Button to trigger the previous slide in ProPresenter."""

    _attr_translation_key = "previous_slide"
    _attr_icon = "mdi:arrow-left"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the previous slide button."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_previous_slide"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.trigger_previous()


class ProPresenterFindMyMouseButton(ProPresenterButton):
    """Button to execute Find My Mouse operation."""

    _attr_name = "Find Mouse"
    _attr_translation_key = "find_mouse"
    _attr_icon = "mdi:cursor-default-outline"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the find mouse button."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_find_mouse"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.find_my_mouse()


class ProPresenterClearGroupButton(ProPresenterButton):
    """Button to trigger a clear group (like Clear All)."""

    _attr_icon = "mdi:broom"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
        group_uuid: str,
        group_name: str,
    ) -> None:
        """Initialize the clear group button."""
        super().__init__(coordinator, config_entry)
        self._group_uuid = group_uuid
        self._attr_name = group_name
        self._attr_unique_id = f"{config_entry.entry_id}_clear_group_{group_uuid}"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.trigger_clear_group(self._group_uuid)
        await self.coordinator.async_request_refresh()


class ProPresenterAudioPlayButton(ProPresenterButton):
    """Button to play/resume audio in ProPresenter."""

    _attr_name = "Audio play"
    _attr_icon = "mdi:play"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the audio play button."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_audio_play"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.audio_play()


class ProPresenterAudioPauseButton(ProPresenterButton):
    """Button to pause audio in ProPresenter."""

    _attr_name = "Audio pause"
    _attr_icon = "mdi:pause"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the audio pause button."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_audio_pause"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.audio_pause()


class ProPresenterAudioNextButton(ProPresenterButton):
    """Button to skip to next audio track in ProPresenter."""

    _attr_name = "Audio next"
    _attr_icon = "mdi:skip-next"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the audio next button."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_audio_next"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.audio_next()


class ProPresenterAudioPreviousButton(ProPresenterButton):
    """Button to skip to previous audio track in ProPresenter."""

    _attr_name = "Audio previous"
    _attr_icon = "mdi:skip-previous"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the audio previous button."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_audio_previous"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.audio_previous()


class ProPresenterClearLayerButton(ProPresenterBaseEntity, ButtonEntity):
    """Button to clear a ProPresenter layer with status indication via icon."""

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        layer_id: str,
        layer_info: dict,
    ) -> None:
        """Initialize the clear layer button."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=coordinator
        )
        self.api = coordinator.api  # Keep reference to API for actions
        self._layer_id = layer_id
        self._layer_info = layer_info
        self._attr_name = layer_info["name"]
        self._attr_unique_id = f"{config_entry.entry_id}_clear_{layer_id}"

    @property
    def icon(self) -> str:
        """Return the icon based on layer status."""
        # Get the unified layer status from streaming coordinator (self.coordinator is the streaming coordinator)
        status_layers = self.coordinator.data.get("status_layers", {})

        # Map our layer IDs to the API's layer names
        layer_map = {
            "audio": "audio",
            "messages": "messages",
            "props": "props",
            "announcements": "announcements",
            "slide": "slide",
            "media": "media",
            "video_input": "video_input",
        }

        api_layer_name = layer_map.get(self._layer_id)
        is_active = False

        if api_layer_name and status_layers:
            is_active = status_layers.get(api_layer_name, False)

        # Return different icon when active vs inactive
        if is_active:
            return self._layer_info["icon_active"]
        else:
            return self._layer_info["icon_inactive"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes including status."""
        # Get status from streaming coordinator (self.coordinator is the streaming coordinator)
        status_layers = self.coordinator.data.get("status_layers", {})
        layer_map = {
            "audio": "audio",
            "messages": "messages",
            "props": "props",
            "announcements": "announcements",
            "slide": "slide",
            "media": "media",
            "video_input": "video_input",
        }
        api_layer_name = layer_map.get(self._layer_id)
        is_active = False

        if api_layer_name and status_layers:
            is_active = status_layers.get(api_layer_name, False)

        return {
            "layer_active": is_active,
            "layer_id": self._layer_id,
            "status": "Layer Showing" if is_active else "Clear",
        }

    async def async_press(self) -> None:
        """Handle the button press to clear the layer."""
        await self.api.trigger_clear_layer(self._layer_id)
        # No need to request refresh - streaming will update automatically


class ProPresenterTimerResetButton(ProPresenterBaseEntity, ButtonEntity):
    """Reset button for a ProPresenter timer."""

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
        timer_uuid: str,
        timer_name: str,
    ) -> None:
        """Initialize the timer reset button."""
        super().__init__(coordinator, config_entry)
        self._timer_uuid = timer_uuid
        self._timer_name = timer_name
        self._attr_unique_id = f"{config_entry.entry_id}_timer_{timer_uuid}_reset"
        self._attr_name = f"{timer_name} Reset"
        self._attr_icon = "mdi:timer-refresh-outline"

    async def async_press(self) -> None:
        """Handle the button press - reset the timer."""
        await self.coordinator.api.timer_operation(self._timer_uuid, "reset")
