"""Timer platform for ProPresenter integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.timer import TimerEntity
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
    """Set up ProPresenter timer entities."""
    static_coordinator: ProPresenterCoordinator = config_entry.runtime_data["coordinator"]
    streaming_coordinator: ProPresenterStreamingCoordinator = config_entry.runtime_data["streaming_coordinator"]
    
    entities = []
    
    # Get all timers from static coordinator
    timers = static_coordinator.data.get("timers", [])
    _LOGGER.debug(f"Found {len(timers)} timers")
    
    for timer in timers:
        timer_data = timer.get("id", {})
        timer_uuid = timer_data.get("uuid")
        timer_name = timer_data.get("name")
        
        # Skip "Countdown to Time" timers as they're clock-based, not duration-based
        if timer.get("count_down_to_time"):
            _LOGGER.debug(f"Skipping 'Countdown to Time' timer: {timer_name}")
            continue
        
        if timer_uuid and timer_name:
            entities.append(
                ProPresenterTimer(static_coordinator, streaming_coordinator, config_entry, timer_uuid, timer_name, timer)
            )
    
    async_add_entities(entities)


class ProPresenterTimer(ProPresenterBaseEntity, TimerEntity):
    """Timer entity for ProPresenter."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        timer_uuid: str,
        timer_name: str,
        timer_config: dict[str, Any],
    ) -> None:
        """Initialize the timer."""
        super().__init__(streaming_coordinator, config_entry, static_coordinator=coordinator)
        self._timer_uuid = timer_uuid
        self._timer_name = timer_name
        self._timer_config = timer_config
        self._attr_name = timer_name
        self._attr_unique_id = f"{config_entry.entry_id}_timer_{timer_uuid}"
        self.api = coordinator.api

    def _parse_time_to_seconds(self, time_str: str) -> int:
        """Parse time string (HH:MM:SS or -HH:MM:SS) to seconds."""
        if not time_str:
            return 0
        
        is_negative = time_str.startswith("-")
        time_str = time_str.lstrip("-")
        
        parts = time_str.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            total_seconds = hours * 3600 + minutes * 60 + seconds
            return -total_seconds if is_negative else total_seconds
        return 0

    def _get_timer_current_state(self) -> dict[str, Any]:
        """Get current timer state from streaming coordinator."""
        timers_current = self.coordinator.data.get("timers_current", [])
        for timer in timers_current:
            timer_id = timer.get("id", {})
            if timer_id.get("uuid") == self._timer_uuid:
                return timer
        return {}

    @property
    def icon(self) -> str:
        """Return icon based on timer type."""
        if self._timer_config.get("countdown"):
            return "mdi:timer-outline"
        elif self._timer_config.get("elapsed"):
            return "mdi:timer"
        return "mdi:timer-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}
        
        # Add timer type
        if self._timer_config.get("countdown"):
            attrs["timer_type"] = "countdown"
            attrs["configured_duration"] = self._timer_config["countdown"].get("duration", 0)
        elif self._timer_config.get("elapsed"):
            attrs["timer_type"] = "elapsed"
            attrs["start_time"] = self._timer_config["elapsed"].get("start_time", 0)
        
        attrs["allows_overrun"] = self._timer_config.get("allows_overrun", False)
        
        # Add current state from streaming data
        current_state = self._get_timer_current_state()
        if current_state:
            attrs["current_time_display"] = current_state.get("time", "00:00:00")
            attrs["pp_state"] = current_state.get("state", "stopped")
        
        return attrs

    @property
    def duration(self) -> timedelta | None:
        """Return the configured duration."""
        if self._timer_config.get("countdown"):
            duration_seconds = self._timer_config["countdown"].get("duration", 0)
            return timedelta(seconds=duration_seconds)
        elif self._timer_config.get("elapsed"):
            # Elapsed timers don't have a fixed duration, but we can use start_time
            start_seconds = self._timer_config["elapsed"].get("start_time", 0)
            return timedelta(seconds=start_seconds)
        return None

    @property
    def remaining(self) -> timedelta | None:
        """Return the remaining time."""
        current_state = self._get_timer_current_state()
        if not current_state:
            return None
        
        time_str = current_state.get("time", "00:00:00")
        seconds = self._parse_time_to_seconds(time_str)
        
        # For countdown timers, the time is the remaining time
        # For elapsed timers, we need to calculate remaining from start_time
        if self._timer_config.get("countdown"):
            # Handle negative time (overrun)
            if seconds < 0:
                return timedelta(seconds=0)
            return timedelta(seconds=seconds)
        elif self._timer_config.get("elapsed"):
            # Elapsed timers count up, so remaining is start_time - current
            start_seconds = self._timer_config["elapsed"].get("start_time", 0)
            remaining = start_seconds - seconds
            return timedelta(seconds=max(0, remaining))
        
        return None

    @property
    def finishes_at(self) -> Any:
        """Return when the timer will finish."""
        # We don't have a reliable way to calculate this without knowing when it started
        return None

    async def async_start(self) -> None:
        """Start the timer."""
        try:
            _LOGGER.debug(f"Starting timer: {self._timer_name}")
            await self.api.timer_operation(self._timer_uuid, "start")
        except Exception as err:
            _LOGGER.error(f"Error starting timer {self._timer_name}: {err}", exc_info=True)

    async def async_pause(self) -> None:
        """Pause the timer."""
        try:
            _LOGGER.debug(f"Pausing timer: {self._timer_name}")
            await self.api.timer_operation(self._timer_uuid, "stop")
        except Exception as err:
            _LOGGER.error(f"Error pausing timer {self._timer_name}: {err}", exc_info=True)

    async def async_cancel(self) -> None:
        """Cancel/reset the timer."""
        try:
            _LOGGER.debug(f"Resetting timer: {self._timer_name}")
            await self.api.timer_operation(self._timer_uuid, "reset")
        except Exception as err:
            _LOGGER.error(f"Error resetting timer {self._timer_name}: {err}", exc_info=True)

    async def async_finish(self) -> None:
        """Finish the timer (set to 0)."""
        try:
            _LOGGER.debug(f"Finishing timer: {self._timer_name}")
            # Reset first, then stop
            await self.api.timer_operation(self._timer_uuid, "reset")
            await self.api.timer_operation(self._timer_uuid, "stop")
        except Exception as err:
            _LOGGER.error(f"Error finishing timer {self._timer_name}: {err}", exc_info=True)
