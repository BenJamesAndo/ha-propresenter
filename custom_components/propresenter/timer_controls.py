"""Timer controls (button entities) for ProPresenter integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
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
    """Set up ProPresenter timer control button entities."""
    static_coordinator: ProPresenterCoordinator = config_entry.runtime_data[
        "coordinator"
    ]
    streaming_coordinator: ProPresenterStreamingCoordinator = config_entry.runtime_data[
        "streaming_coordinator"
    ]

    entities = []

    # Get all timers from static coordinator
    timers = static_coordinator.data.get("timers", [])
    _LOGGER.debug(f"Found {len(timers)} timers for controls")

    for timer in timers:
        timer_data = timer.get("id", {})
        timer_uuid = timer_data.get("uuid")
        timer_name = timer_data.get("name")

        # Skip "Countdown to Time" timers as they're clock-based, not duration-based
        if timer.get("count_down_to_time"):
            _LOGGER.debug(f"Skipping 'Countdown to Time' timer controls: {timer_name}")
            continue

        if timer_uuid and timer_name:
            # Create start, stop, and reset buttons for each timer
            entities.extend(
                [
                    ProPresenterTimerStartButton(
                        static_coordinator,
                        streaming_coordinator,
                        config_entry,
                        timer_uuid,
                        timer_name,
                    ),
                    ProPresenterTimerStopButton(
                        static_coordinator,
                        streaming_coordinator,
                        config_entry,
                        timer_uuid,
                        timer_name,
                    ),
                    ProPresenterTimerResetButton(
                        static_coordinator,
                        streaming_coordinator,
                        config_entry,
                        timer_uuid,
                        timer_name,
                    ),
                ]
            )

    async_add_entities(entities)


class ProPresenterTimerStartButton(ProPresenterBaseEntity, ButtonEntity):
    """Start button for a ProPresenter timer."""

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        timer_uuid: str,
        timer_name: str,
    ) -> None:
        """Initialize the timer start button."""
        super().__init__(coordinator, config_entry)
        self.streaming_coordinator = streaming_coordinator
        self._timer_uuid = timer_uuid
        self._timer_name = timer_name
        self._attr_unique_id = f"{config_entry.entry_id}_timer_{timer_uuid}_start"
        self._attr_name = f"{timer_name} Start"
        self._attr_icon = "mdi:play"

    async def async_press(self) -> None:
        """Handle the button press - start the timer."""
        await self.coordinator.api.timer_operation(self._timer_uuid, "start")


class ProPresenterTimerStopButton(ProPresenterBaseEntity, ButtonEntity):
    """Stop button for a ProPresenter timer."""

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        timer_uuid: str,
        timer_name: str,
    ) -> None:
        """Initialize the timer stop button."""
        super().__init__(coordinator, config_entry)
        self.streaming_coordinator = streaming_coordinator
        self._timer_uuid = timer_uuid
        self._timer_name = timer_name
        self._attr_unique_id = f"{config_entry.entry_id}_timer_{timer_uuid}_stop"
        self._attr_name = f"{timer_name} Stop"
        self._attr_icon = "mdi:stop"

    async def async_press(self) -> None:
        """Handle the button press - stop the timer."""
        await self.coordinator.api.timer_operation(self._timer_uuid, "stop")


class ProPresenterTimerResetButton(ProPresenterBaseEntity, ButtonEntity):
    """Reset button for a ProPresenter timer."""

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        timer_uuid: str,
        timer_name: str,
    ) -> None:
        """Initialize the timer reset button."""
        super().__init__(coordinator, config_entry)
        self.streaming_coordinator = streaming_coordinator
        self._timer_uuid = timer_uuid
        self._timer_name = timer_name
        self._attr_unique_id = f"{config_entry.entry_id}_timer_{timer_uuid}_reset"
        self._attr_name = f"{timer_name} Reset"
        self._attr_icon = "mdi:restart"

    async def async_press(self) -> None:
        """Handle the button press - reset the timer."""
        await self.coordinator.api.timer_operation(self._timer_uuid, "reset")
