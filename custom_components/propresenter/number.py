"""Number platform for ProPresenter integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Set up ProPresenter number entities."""
    coordinator: ProPresenterCoordinator = config_entry.runtime_data["coordinator"]
    streaming_coordinator: ProPresenterStreamingCoordinator = config_entry.runtime_data[
        "streaming_coordinator"
    ]

    entities = []

    # Add timer duration number entities
    timers = coordinator.data.get("timers", [])
    for timer in timers:
        timer_data = timer.get("id", {})
        timer_uuid = timer_data.get("uuid")
        timer_name = timer_data.get("name")

        # Only create duration entities for countdown timers
        if timer.get("countdown"):
            if timer_uuid and timer_name:
                entities.append(
                    ProPresenterTimerDurationNumber(
                        coordinator,
                        streaming_coordinator,
                        config_entry,
                        timer_uuid,
                        timer_name,
                        timer,
                    )
                )

    async_add_entities(entities)


class ProPresenterTimerDurationNumber(ProPresenterBaseEntity, NumberEntity):
    """Number entity for setting timer duration."""

    _attr_native_min_value = 1  # 1 minute minimum
    _attr_native_max_value = 1440  # 24 hours maximum (in minutes)
    _attr_native_step = 1  # 1 minute increments
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "min"
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        timer_uuid: str,
        timer_name: str,
        timer_config: dict,
    ) -> None:
        """Initialize the timer duration number."""
        # Use streaming coordinator as primary, static as fallback for device info
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=coordinator
        )
        self._timer_uuid = timer_uuid
        self._timer_name = timer_name
        self._timer_config = timer_config
        self._attr_unique_id = f"{config_entry.entry_id}_timer_{timer_uuid}_duration"
        self._attr_name = f"{timer_name} Duration"

    @property
    def native_value(self) -> float:
        """Return the current timer duration in minutes."""
        # Read from streaming coordinator (self.coordinator is now streaming)
        timers = self.coordinator.data.get("timers", [])
        for timer in timers:
            timer_data = timer.get("id", {})
            if timer_data.get("uuid") == self._timer_uuid:
                seconds = timer.get("countdown", {}).get("duration", 0)
                minutes = seconds / 60.0
                # Return int if it's a whole number, otherwise float
                return int(minutes) if minutes == int(minutes) else minutes

        # Fallback to static coordinator
        if self.static_coordinator:
            static_timers = self.static_coordinator.data.get("timers", [])
            for timer in static_timers:
                timer_data = timer.get("id", {})
                if timer_data.get("uuid") == self._timer_uuid:
                    seconds = timer.get("countdown", {}).get("duration", 0)
                    minutes = seconds / 60.0
                    return int(minutes) if minutes == int(minutes) else minutes

        # Final fallback to initial config
        seconds = self._timer_config.get("countdown", {}).get("duration", 0)
        minutes = seconds / 60.0
        return int(minutes) if minutes == int(minutes) else minutes

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        # Get current value in seconds
        minutes = self.native_value
        total_seconds = int(minutes * 60)

        # Convert to HH:MM:SS format (like ProPresenter displays)
        hours = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        return {
            "formatted_time": f"{hours:02d}:{mins:02d}:{secs:02d}",
            "total_seconds": total_seconds,
        }

    async def async_set_native_value(self, value: float) -> None:
        """Set new timer duration."""
        # Convert minutes to seconds
        duration_seconds = int(value * 60)

        # Get the current timer configuration
        timers = self.coordinator.data.get("timers", [])
        current_timer = None
        for timer in timers:
            timer_data = timer.get("id", {})
            if timer_data.get("uuid") == self._timer_uuid:
                current_timer = timer
                break

        if not current_timer:
            _LOGGER.error(f"Could not find timer {self._timer_uuid} to update duration")
            return

        # Build the PUT request body with the complete timer object
        timer_body = {
            "id": current_timer.get("id"),
            "allows_overrun": current_timer.get("allows_overrun", False),
            "countdown": {"duration": duration_seconds},
        }

        _LOGGER.debug(
            f"Setting timer {self._timer_name} duration to {duration_seconds}s ({value} min)"
        )

        # Use the API to update the timer
        success = await self.coordinator.api.update_timer(self._timer_uuid, timer_body)

        if success:
            # Only reset if timer is fully stopped (reset), not paused mid-countdown
            # Check if current time equals configured duration (stopped) or not (paused)
            timers_current = self.coordinator.data.get("timers_current", [])
            current_timer_state = None
            for timer in timers_current:
                if timer.get("id", {}).get("uuid") == self._timer_uuid:
                    current_timer_state = timer
                    break

            should_reset = False
            if current_timer_state:
                pp_state = current_timer_state.get("state", "stopped")
                time_str = current_timer_state.get("time", "00:00:00")

                # Parse current time to seconds
                is_negative = time_str.startswith("-")
                time_str_clean = time_str.lstrip("-")
                parts = time_str_clean.split(":")
                if len(parts) == 3:
                    hours, minutes, seconds = map(int, parts)
                    current_seconds = hours * 3600 + minutes * 60 + seconds
                    if is_negative:
                        current_seconds = -current_seconds

                    # Get OLD configured duration before we changed it
                    old_duration = current_timer.get("countdown", {}).get("duration", 0)

                    # Reset if state is stopped AND current time equals old duration (timer was reset/never started)
                    if pp_state == "stopped" and current_seconds == old_duration:
                        should_reset = True
                        _LOGGER.debug(
                            f"Timer is stopped and at reset position ({current_seconds}s == {old_duration}s), will reset to apply new duration"
                        )
                    else:
                        _LOGGER.debug(
                            f"Timer is paused or running (state={pp_state}, time={current_seconds}s != {old_duration}s), not resetting"
                        )

            if should_reset:
                await self.coordinator.api.timer_operation(self._timer_uuid, "reset")
