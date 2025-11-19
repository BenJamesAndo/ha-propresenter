"""Switch platform for ProPresenter integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base import ProPresenterBaseEntity
from .coordinator import ProPresenterCoordinator, ProPresenterStreamingCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ProPresenter switch entities."""
    # Get coordinators
    static_coordinator: ProPresenterCoordinator = config_entry.runtime_data[
        "coordinator"
    ]
    streaming_coordinator: ProPresenterStreamingCoordinator = config_entry.runtime_data[
        "streaming_coordinator"
    ]

    entities = []

    # Add audience and stage screen control switches
    entities.append(
        ProPresenterAudienceScreenSwitch(
            static_coordinator, streaming_coordinator, config_entry
        )
    )
    entities.append(
        ProPresenterStageScreenSwitch(
            static_coordinator, streaming_coordinator, config_entry
        )
    )

    # Add stage message switch
    entities.append(
        ProPresenterStageMessageSwitch(
            static_coordinator, streaming_coordinator, config_entry
        )
    )

    # Add capture switch
    entities.append(
        ProPresenterCaptureSwitch(
            static_coordinator, streaming_coordinator, config_entry
        )
    )

    # Add timer switches
    timers = static_coordinator.data.get("timers", [])
    for timer in timers:
        timer_data = timer.get("id", {})
        timer_uuid = timer_data.get("uuid")
        timer_name = timer_data.get("name")

        # Skip "Countdown to Time" timers as they're clock-based, not duration-based
        if timer.get("count_down_to_time"):
            continue

        if timer_uuid and timer_name:
            entities.append(
                ProPresenterTimerSwitch(
                    static_coordinator,
                    streaming_coordinator,
                    config_entry,
                    timer_uuid,
                    timer_name,
                    timer,
                )
            )

    # Create a switch for each message
    messages = streaming_coordinator.data.get("messages", [])
    for message in messages:
        message_data = message.get("id", {})
        message_uuid = message_data.get("uuid")
        message_name = message_data.get("name")
        if message_uuid and message_name:
            entities.append(
                ProPresenterMessageSwitch(
                    static_coordinator,
                    streaming_coordinator,
                    config_entry,
                    message_uuid,
                    message_name,
                )
            )

    async_add_entities(entities)


class ProPresenterMessageSwitch(ProPresenterBaseEntity, SwitchEntity):
    """Switch entity for ProPresenter message."""

    _attr_icon = "mdi:send"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        message_uuid: str,
        message_name: str,
    ) -> None:
        """Initialize the message switch."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=coordinator
        )
        self._message_uuid = message_uuid
        self._message_name = message_name
        self._attr_name = message_name
        self._attr_unique_id = f"{config_entry.entry_id}_message_{message_uuid}"
        self.api = coordinator.api  # Store API reference for actions

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "submit_button_text": "Hide" if self.is_on else "Show",
        }

    @property
    def is_on(self) -> bool:
        """Return True if the message is active."""
        messages = self.coordinator.data.get("messages", [])
        for message in messages:
            message_data = message.get("id", {})
            if message_data.get("uuid") == self._message_uuid:
                return message.get("is_active", False)
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch (show the message)."""
        try:
            # Gather token values from Home Assistant text entities
            tokens = {}

            # Get all text entities from the entity registry for this integration
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(self.hass)

            # Get message UUID short form for matching
            short_uuid = self._message_uuid.split("-")[0]

            # Find text entities that belong to this message
            for entity_id, entry in registry.entities.items():
                if entry.platform == "propresenter" and entity_id.startswith("text."):
                    # Check if this text entity belongs to this message (format: msg_{short_uuid}_{token_name}_{index})
                    if f"_msg_{short_uuid}_" in entry.unique_id:
                        # Get the current state value
                        state = self.hass.states.get(entity_id)
                        if state and state.attributes:
                            # Get token info from entity attributes
                            token_name = state.attributes.get("token_name")
                            if token_name:
                                # Store by name (duplicate names will overwrite - API limitation)
                                tokens[token_name] = state.state

            # Show message with token values from HA text entities
            await self.api.show_message(
                self._message_uuid,
                tokens if tokens else None,
            )
            # No need to refresh - streaming will update automatically
        except Exception as err:
            _LOGGER.error(
                "Error showing message %s: %s", self._message_name, err, exc_info=True
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch (hide the message)."""
        try:
            await self.api.hide_message(self._message_uuid)
            # No need to refresh - streaming will update automatically
        except Exception as err:
            _LOGGER.error(
                "Error hiding message %s: %s", self._message_name, err, exc_info=True
            )


class ProPresenterAudienceScreenSwitch(ProPresenterBaseEntity, SwitchEntity):
    """Switch entity for ProPresenter audience screens."""

    _attr_name = "Audience Screens"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the audience screen switch."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=coordinator
        )
        self._attr_unique_id = f"{config_entry.entry_id}_audience_screens"
        self.api = coordinator.api  # Store API reference for actions

    @property
    def icon(self) -> str:
        """Return the icon based on state."""
        return (
            "mdi:checkbox-blank-circle"
            if self.is_on
            else "mdi:checkbox-blank-circle-outline"
        )

    @property
    def is_on(self) -> bool:
        """Return True if audience screens are enabled."""
        return self.coordinator.data.get("audience_screens_status", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch (enable audience screens)."""
        try:
            await self.api.set_audience_screens_status(True)
            # No need to refresh - streaming will update automatically
        except Exception as err:
            _LOGGER.error("Error enabling audience screens: %s", err, exc_info=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch (disable audience screens)."""
        try:
            await self.api.set_audience_screens_status(False)
            # No need to refresh - streaming will update automatically
        except Exception as err:
            _LOGGER.error("Error disabling audience screens: %s", err, exc_info=True)


class ProPresenterStageScreenSwitch(ProPresenterBaseEntity, SwitchEntity):
    """Switch entity for ProPresenter stage screens."""

    _attr_name = "Stage Screens"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the stage screen switch."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=coordinator
        )
        self._attr_unique_id = f"{config_entry.entry_id}_stage_screens"
        self.api = coordinator.api  # Store API reference for actions

    @property
    def icon(self) -> str:
        """Return the icon based on state."""
        return (
            "mdi:checkbox-blank-circle"
            if self.is_on
            else "mdi:checkbox-blank-circle-outline"
        )

    @property
    def is_on(self) -> bool:
        """Return True if stage screens are enabled."""
        return self.coordinator.data.get("stage_screens_status", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch (enable stage screens)."""
        try:
            await self.api.set_stage_screens_status(True)
            # No need to refresh - streaming will update automatically
        except Exception as err:
            _LOGGER.error("Error enabling stage screens: %s", err, exc_info=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch (disable stage screens)."""
        try:
            await self.api.set_stage_screens_status(False)
            # No need to refresh - streaming will update automatically
        except Exception as err:
            _LOGGER.error("Error disabling stage screens: %s", err, exc_info=True)


class ProPresenterStageMessageSwitch(ProPresenterBaseEntity, SwitchEntity):
    """Switch entity for ProPresenter stage message visibility."""

    _attr_icon = "mdi:send-circle"
    _attr_name = "Stage Message"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the stage message switch."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=coordinator
        )
        self._attr_unique_id = f"{config_entry.entry_id}_stage_message_switch"
        self.api = coordinator.api  # Store API reference for actions

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "submit_button_text": "Hide" if self.is_on else "Show",
        }

    @property
    def is_on(self) -> bool:
        """Return True if stage message is shown (has text)."""
        stage_message = self.coordinator.data.get("stage_message", "")
        return bool(stage_message)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch (show the stage message with current text)."""
        try:
            # Get the current message text from the text entity
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(self.hass)

            # Find the stage message text entity
            stage_message_text = ""
            for entity_id, entry in registry.entities.items():
                if (
                    entry.platform == "propresenter"
                    and "stage_message" in entry.unique_id
                    and "switch" not in entry.unique_id
                    and entity_id.startswith("text.")
                ):
                    state = self.hass.states.get(entity_id)
                    if state and state.state and state.state != "unknown":
                        stage_message_text = state.state
                    break

            # Show the message (even if empty - ProPresenter will handle it)
            await self.api.set_stage_message(stage_message_text)
            # No need to refresh - streaming will update automatically
        except Exception as err:
            _LOGGER.error("Error showing stage message: %s", err, exc_info=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch (hide the stage message)."""
        try:
            await self.api.clear_stage_message()
            # No need to refresh - streaming will update automatically
        except Exception as err:
            _LOGGER.error("Error hiding stage message: %s", err, exc_info=True)


class ProPresenterCaptureSwitch(ProPresenterBaseEntity, SwitchEntity):
    """Switch entity for ProPresenter capture control."""

    _attr_name = "Capture"
    _attr_icon = "mdi:access-point"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the capture switch."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=coordinator
        )
        self._attr_unique_id = f"{config_entry.entry_id}_capture"
        self.api = coordinator.api
        self._capture_settings: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        # Fetch initial capture settings (settings don't stream, only status does)
        try:
            self._capture_settings = await self.api.get_capture_settings() or {}
        except Exception:
            pass  # Settings will be fetched on demand if needed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        capture_status = self.coordinator.data.get("capture_status", {})

        attrs = {}

        # Only show capture time when actively capturing, otherwise explicitly set to None
        if capture_status.get("status") == "active":
            attrs["capture_time"] = capture_status.get("capture_time", "0:00")
        else:
            attrs["capture_time"] = "0:00"

        # Add capture settings as attributes
        if self._capture_settings:
            disk_settings = self._capture_settings.get("disk", {})
            if disk_settings:
                attrs["file_location"] = disk_settings.get("file_location", "")
                attrs["codec"] = disk_settings.get("codec", "")
                resolution = disk_settings.get("resolution", {})
                if resolution:
                    attrs["resolution"] = (
                        f"{resolution.get('width', 0)}x{resolution.get('height', 0)}"
                    )
                attrs["frame_rate"] = disk_settings.get("frame_rate", 0)

        return attrs

    @property
    def is_on(self) -> bool:
        """Return True if capture is active."""
        capture_status = self.coordinator.data.get("capture_status", {})
        return capture_status.get("status") == "active"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch (start capture)."""
        try:
            await self.api.capture_operation("start")
            # State will update via streaming coordinator
        except Exception as err:
            _LOGGER.error("Error starting capture: %s", err, exc_info=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch (stop capture)."""
        try:
            await self.api.capture_operation("stop")
            # State will update via streaming coordinator
        except Exception as err:
            _LOGGER.error("Error stopping capture: %s", err, exc_info=True)


class ProPresenterTimerSwitch(ProPresenterBaseEntity, SwitchEntity):
    """Switch entity for ProPresenter timer control."""

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        timer_uuid: str,
        timer_name: str,
        timer_config: dict,
    ) -> None:
        """Initialize the timer switch."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=coordinator
        )
        self._timer_uuid = timer_uuid
        self._timer_name = timer_name
        self._attr_unique_id = f"{config_entry.entry_id}_timer_{timer_uuid}"
        self._attr_name = timer_name
        self.api = coordinator.api

        # Determine timer type from initial config
        if timer_config.get("countdown"):
            self._timer_type = "countdown"
        elif timer_config.get("elapsed"):
            self._timer_type = "elapsed"
        else:
            self._timer_type = "unknown"

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Force write state to HA when coordinator updates
        # This ensures attributes like current_time update in the UI immediately
        self.async_write_ha_state()

    def _format_time(self, total_seconds: int) -> str:
        """Format seconds as HH:MM:SS (always, like ProPresenter)."""
        # Handle negative values
        is_negative = total_seconds < 0
        total_seconds = abs(total_seconds)

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        # Always show HH:MM:SS format (like ProPresenter)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return f"-{time_str}" if is_negative else time_str

    def _get_timer_config(self) -> dict:
        """Get current timer configuration from streaming coordinator."""
        # First try streaming coordinator (has real-time updates)
        timers = self.coordinator.data.get("timers", [])
        if timers:
            for timer in timers:
                timer_id = timer.get("id", {})
                if timer_id.get("uuid") == self._timer_uuid:
                    return timer

        # Fallback to static coordinator if streaming doesn't have it yet
        if hasattr(self, "static_coordinator"):
            timers = self.static_coordinator.data.get("timers", [])
            for timer in timers:
                timer_id = timer.get("id", {})
                if timer_id.get("uuid") == self._timer_uuid:
                    return timer
        return {}

    def _parse_time_to_seconds(self, time_str: str) -> int:
        """Parse time string (HH:MM:SS or -HH:MM:SS) to seconds."""
        if not time_str:
            return 0

        # Handle negative time (overrun)
        is_negative = time_str.startswith("-")
        time_str = time_str.lstrip("-")

        parts = time_str.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            total_seconds = hours * 3600 + minutes * 60 + seconds
            return -total_seconds if is_negative else total_seconds
        return 0

    def _get_current_timer_state(self) -> dict | None:
        """Get current timer state from streaming coordinator."""
        timers_current = self.coordinator.data.get("timers_current", [])
        for timer in timers_current:
            timer_id = timer.get("id", {})
            if isinstance(timer_id, dict) and timer_id.get("uuid") == self._timer_uuid:
                return timer
        return None

    @property
    def icon(self) -> str:
        """Return dynamic icon based on timer state."""
        if self._timer_type == "countdown":
            timer_state = self._get_current_timer_state()
            timer_config = self._get_timer_config()

            if not timer_state:
                return "mdi:timer-stop-outline"

            pp_state = timer_state.get("state", "stopped")

            # Overrunning state
            if pp_state == "overrunning":
                return "mdi:timer-alert-outline"

            # Running state
            if pp_state == "running":
                return "mdi:timer-play-outline"

            # Stopped state - check if reset or paused
            if pp_state == "stopped":
                time_str = timer_state.get("time", "00:00:00")
                current_seconds = self._parse_time_to_seconds(time_str)
                configured_duration = timer_config.get("countdown", {}).get(
                    "duration", 0
                )

                # If current time equals configured duration, it's reset
                if current_seconds == configured_duration:
                    return "mdi:timer-stop-outline"
                else:
                    # Paused mid-timer
                    return "mdi:timer-pause-outline"

            return "mdi:timer-outline"
        elif self._timer_type == "elapsed":
            # For elapsed timers, use simple running/stopped icons
            timer_state = self._get_current_timer_state()
            if timer_state and timer_state.get("state") == "running":
                return "mdi:timer"
            return "mdi:timer-outline"

        return "mdi:timer"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        timer_state = self._get_current_timer_state()
        timer_config = self._get_timer_config()

        attrs = {
            "timer_type": self._timer_type,
            "allows_overrun": timer_config.get("allows_overrun", False),
        }

        if timer_state:
            # Format current time using our formatter (MM:SS or HH:MM:SS)
            time_str = timer_state.get("time", "00:00:00")
            seconds = self._parse_time_to_seconds(time_str)
            attrs["current_time"] = self._format_time(seconds)

            # Display a more user-friendly state
            pp_state = timer_state.get("state", "stopped")

            # For countdown timers, distinguish between truly stopped vs paused
            if self._timer_type == "countdown" and pp_state == "stopped":
                configured_duration = timer_config.get("countdown", {}).get(
                    "duration", 0
                )
                if seconds == configured_duration:
                    # Timer is at full duration - truly stopped/reset
                    attrs["timer_state"] = "Stopped"
                else:
                    # Timer is stopped mid-countdown - paused
                    attrs["timer_state"] = "Paused"
            else:
                # Running, overrunning, or elapsed timer
                attrs["timer_state"] = pp_state.capitalize()

            # Add remaining/elapsed seconds
            if self._timer_type == "countdown":
                attrs["remaining_seconds"] = seconds
            elif self._timer_type == "elapsed":
                attrs["elapsed_seconds"] = abs(seconds)
        else:
            attrs["timer_state"] = "Stopped"

        # Add configured duration/start time formatted as HH:MM:SS or MM:SS
        if self._timer_type == "countdown":
            duration_seconds = timer_config.get("countdown", {}).get("duration", 0)
            attrs["configured_duration"] = self._format_time(duration_seconds)
        elif self._timer_type == "elapsed":
            start_seconds = timer_config.get("elapsed", {}).get("start_time", 0)
            attrs["start_time"] = self._format_time(start_seconds)

        return attrs

    @property
    def is_on(self) -> bool:
        """Return True if timer is running."""
        timer_state = self._get_current_timer_state()
        if not timer_state:
            return False

        pp_state = timer_state.get("state", "stopped")
        return pp_state in ["running", "overrunning"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch (start timer)."""
        try:
            await self.api.timer_operation(self._timer_uuid, "start")
            # State will update via streaming coordinator
        except Exception as err:
            _LOGGER.error("Error starting timer: %s", err, exc_info=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch (stop timer)."""
        try:
            await self.api.timer_operation(self._timer_uuid, "stop")
            # State will update via streaming coordinator
        except Exception as err:
            _LOGGER.error("Error stopping timer: %s", err, exc_info=True)
