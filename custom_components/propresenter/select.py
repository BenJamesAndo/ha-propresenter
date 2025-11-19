"""Select platform for ProPresenter integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base import ProPresenterBaseEntity
from .coordinator import ProPresenterCoordinator, ProPresenterStreamingCoordinator
from .utils import get_nested_value

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ProPresenter select entities."""
    coordinator: ProPresenterCoordinator = config_entry.runtime_data["coordinator"]
    streaming_coordinator: ProPresenterStreamingCoordinator = config_entry.runtime_data[
        "streaming_coordinator"
    ]

    # Get stage screens from streaming coordinator data
    stage_screens = streaming_coordinator.data.get("stage_screens", [])

    # Create a select entity for each stage screen
    entities = []
    for screen in stage_screens:
        # ProPresenter uses 'uuid' not 'id' for stage screens
        screen_id = screen.get("uuid") or screen.get("id")
        if screen_id:
            entities.append(
                ProPresenterStageLayoutSelect(
                    coordinator, streaming_coordinator, config_entry, screen_id
                )
            )

    # Props are now handled by media_player platform (ProPresenterPropMediaPlayer)

    # Create a select entity for looks (from streaming coordinator)
    looks = streaming_coordinator.data.get("looks", [])
    if looks:
        entities.append(
            ProPresenterLookSelect(coordinator, streaming_coordinator, config_entry)
        )

    # Create a select entity for macros
    macros = coordinator.data.get("macros", [])
    if macros:
        entities.append(ProPresenterMacroSelect(coordinator, config_entry))

    # Create a select entity for video inputs
    video_inputs = coordinator.data.get("video_inputs", [])
    if video_inputs:
        entities.append(
            ProPresenterVideoInputSelect(
                coordinator, streaming_coordinator, config_entry
            )
        )

    if entities:
        async_add_entities(entities)
    else:
        _LOGGER.warning(
            "No stage screens or props found - no select entities will be created"
        )


class ProPresenterStageLayoutSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for choosing stage layout on a specific screen."""

    _attr_translation_key = "stage_layout"
    _attr_icon = "mdi:contacts"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        screen_id: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=coordinator
        )
        self.api = coordinator.api  # Keep reference to API for actions
        self._screen_id = screen_id
        self._attr_unique_id = f"{config_entry.entry_id}_stage_screen_{screen_id}"

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        # Get screen name from streaming coordinator data (self.coordinator is the streaming coordinator)
        stage_screens = self.coordinator.data.get("stage_screens", [])
        for screen in stage_screens:
            # Check both 'uuid' and 'id' fields
            screen_id = screen.get("uuid") or screen.get("id")
            if screen_id == self._screen_id:
                screen_name = screen.get("name", f"Screen {self._screen_id}")
                return f"{screen_name} layout"
        return f"Stage screen {self._screen_id} layout"

    @property
    def options(self) -> list[str]:
        """Return list of available stage layouts."""
        # Get layouts from streaming coordinator data (self.coordinator is the streaming coordinator)
        stage_layouts = self.coordinator.data.get("stage_layouts", [])
        layout_names = []

        for layout in stage_layouts:
            # ProPresenter nests layout info under 'id' key
            layout_data = layout.get("id", {})
            layout_name = (
                layout_data.get("name")
                if isinstance(layout_data, dict)
                else layout.get("name")
            )
            if layout_name:
                layout_names.append(layout_name)

        return layout_names if layout_names else ["No layouts available"]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected layout."""
        # Get layout map and layouts from streaming coordinator data (self.coordinator is the streaming coordinator)
        layout_map = self.coordinator.data.get("layout_map", [])
        stage_layouts = self.coordinator.data.get("stage_layouts", [])

        # Find the current layout UUID for this screen
        # Layout map format: [{"screen": {"uuid": "..."}, "layout": {"uuid": "...", "name": "..."}}]
        current_layout_uuid = None
        for mapping in layout_map:
            screen_data = mapping.get("screen", {})
            screen_uuid = screen_data.get("uuid") or screen_data.get("id")

            if screen_uuid == self._screen_id:
                layout_data = mapping.get("layout", {})
                current_layout_uuid = layout_data.get("uuid")
                # Can also get the name directly from here
                current_layout_name = layout_data.get("name")
                if current_layout_name:
                    return current_layout_name
                break

        # If no layout is assigned, return None
        if not current_layout_uuid:
            return None

        # Find the layout name from the layout UUID
        for layout in stage_layouts:
            layout_uuid = get_nested_value(layout, "id", "uuid")
            layout_name = get_nested_value(layout, "id", "name")

            if layout_uuid == current_layout_uuid:
                return layout_name

        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected layout."""
        # Get layouts from streaming coordinator data (self.coordinator is the streaming coordinator)
        stage_layouts = self.coordinator.data.get("stage_layouts", [])

        # Find the layout UUID for the selected layout name
        selected_layout_uuid = None
        for layout in stage_layouts:
            layout_name = get_nested_value(layout, "id", "name")
            if layout_name == option:
                selected_layout_uuid = get_nested_value(layout, "id", "uuid")
                break

        if not selected_layout_uuid:
            _LOGGER.error("Could not find layout UUID for: %s", option)
            return

        _LOGGER.debug(
            "Setting stage screen %s to layout %s (UUID: %s)",
            self._screen_id,
            option,
            selected_layout_uuid,
        )

        # Set the layout on the screen using the API
        await self.api.set_stage_screen_layout(self._screen_id, selected_layout_uuid)

        # No need to request refresh - streaming will update automatically


class ProPresenterPropSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for choosing which prop to display."""

    _attr_name = "Active prop"
    _attr_icon = "mdi:image-frame"

    def __init__(
        self,
        static_coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=static_coordinator
        )
        self.api = static_coordinator.api  # Keep reference to API for actions
        self._attr_unique_id = f"{config_entry.entry_id}_active_prop"
        self._prop_uuid_map = {}  # Map display names to UUIDs

    @property
    def options(self) -> list[str]:
        """Return list of available props with unique display names."""
        props = self.coordinator.data.get("props", [])
        prop_names = []
        self._prop_uuid_map = {}  # Reset map

        # Add "None" option for clearing all props
        prop_names.append("None")

        # Track name occurrences to make duplicates unique
        name_counts = {}

        # Add each prop name, making duplicates unique
        for prop in props:
            prop_data = prop.get("id", {})
            if isinstance(prop_data, dict):
                prop_name = prop_data.get("name")
                prop_uuid = prop_data.get("uuid")
                if prop_name and prop_uuid:
                    # Check if we've seen this name before
                    if prop_name in name_counts:
                        name_counts[prop_name] += 1
                        # Make it unique by appending the count
                        display_name = f"{prop_name} ({name_counts[prop_name]})"
                    else:
                        name_counts[prop_name] = 1
                        display_name = prop_name

                    prop_names.append(display_name)
                    self._prop_uuid_map[display_name] = prop_uuid

        return prop_names

    @property
    def current_option(self) -> str | None:
        """Return the currently active prop."""
        props = self.coordinator.data.get("props", [])

        # Find the active prop UUID
        active_uuid = None
        for prop in props:
            if prop.get("is_active", False):
                prop_data = prop.get("id", {})
                if isinstance(prop_data, dict):
                    active_uuid = prop_data.get("uuid")
                    break

        if not active_uuid:
            return "None"

        # Find the display name for this UUID in our map
        for display_name, uuid in self._prop_uuid_map.items():
            if uuid == active_uuid:
                return display_name

        # Fallback: return the name without decoration
        for prop in props:
            if prop.get("is_active", False):
                prop_data = prop.get("id", {})
                if isinstance(prop_data, dict):
                    return prop_data.get("name")

        return "None"

    async def async_select_option(self, option: str) -> None:
        """Trigger the selected prop."""
        if option == "None":
            # Clear all props
            await self.api.trigger_clear_layer("props")
        else:
            # Look up the UUID from our map
            selected_prop_uuid = self._prop_uuid_map.get(option)

            if not selected_prop_uuid:
                _LOGGER.error("Could not find prop UUID for: %s", option)
                return

            # Trigger the prop
            await self.api.trigger_prop(selected_prop_uuid)

        # No need to request refresh - streaming will update automatically


class ProPresenterAudioTrackSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for audio tracks."""

    _attr_name = "Audio Track"
    _attr_icon = "mdi:music"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the audio track select."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_audio_track"

    @property
    def options(self) -> list[str]:
        """Return the list of available audio tracks from all playlists."""
        audio_playlist_details_list = self.coordinator.data.get(
            "audio_playlist_details_list", []
        )

        if not audio_playlist_details_list:
            return ["No Playlists"]

        track_options = []

        # Iterate through all playlists
        for playlist_details in audio_playlist_details_list:
            playlist_name = get_nested_value(
                playlist_details, "id", "name", default="Unknown Playlist"
            )
            items = playlist_details.get("items", [])

            if not items:
                continue

            # Add tracks from this playlist
            for item in items:
                if item.get("type") == "audio":
                    track_name = get_nested_value(
                        item, "id", "name", default="Unknown Track"
                    )
                    # Remove .mp3 extension if present for cleaner display
                    if track_name.endswith(".mp3"):
                        track_name = track_name[:-4]

                    # Format as "Playlist Name - Track Name" if multiple playlists
                    if len(audio_playlist_details_list) > 1:
                        display_name = f"{playlist_name} - {track_name}"
                    else:
                        display_name = track_name

                    track_options.append(display_name)

        return track_options if track_options else ["No Audio Tracks"]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected audio track."""
        # ProPresenter doesn't provide "current track" in the API
        # So we'll return None to show no selection
        return None

    async def async_select_option(self, option: str) -> None:
        """Select an audio track to play from any playlist."""
        if option in ["No Playlists", "No Tracks", "No Audio Tracks"]:
            return

        try:
            audio_playlist_details_list = self.coordinator.data.get(
                "audio_playlist_details_list", []
            )

            if not audio_playlist_details_list:
                _LOGGER.error("No audio playlist data available")
                return

            # Search through all playlists to find the track
            playlist_uuid = None
            track_uuid = None
            found = False

            for playlist_details in audio_playlist_details_list:
                current_playlist_uuid = get_nested_value(playlist_details, "id", "uuid")
                playlist_name = get_nested_value(
                    playlist_details, "id", "name", default="Unknown Playlist"
                )
                items = playlist_details.get("items", [])

                for item in items:
                    if item.get("type") == "audio":
                        track_name = get_nested_value(item, "id", "name", default="")
                        # Remove .mp3 extension for comparison
                        display_track_name = (
                            track_name[:-4]
                            if track_name.endswith(".mp3")
                            else track_name
                        )

                        # Check if this is the selected track
                        # Handle both "Playlist - Track" and "Track" formats
                        if len(audio_playlist_details_list) > 1:
                            full_display_name = (
                                f"{playlist_name} - {display_track_name}"
                            )
                            if full_display_name == option:
                                playlist_uuid = current_playlist_uuid
                                track_uuid = get_nested_value(item, "id", "uuid")
                                found = True
                                break
                        else:
                            if display_track_name == option or track_name == option:
                                playlist_uuid = current_playlist_uuid
                                track_uuid = get_nested_value(item, "id", "uuid")
                                found = True
                                break

                if found:
                    break

            if not playlist_uuid or not track_uuid:
                _LOGGER.error(f"Could not find track: {option}")
                return

            _LOGGER.debug(
                f"Triggering audio track: {option} (playlist: {playlist_uuid}, track: {track_uuid})"
            )
            await self.coordinator.api.trigger_audio_track(playlist_uuid, track_uuid)

        except Exception as e:
            _LOGGER.error(f"Error selecting audio track: {e}")
            raise


class ProPresenterLookSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for choosing ProPresenter looks."""

    _attr_translation_key = "look"
    _attr_name = "Look"
    _attr_icon = "mdi:glasses"

    def __init__(
        self,
        static_coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=static_coordinator
        )
        self.api = static_coordinator.api
        self._attr_unique_id = f"{config_entry.entry_id}_look"
        self._pending_look: str | None = None
        self._processing_lock = asyncio.Lock()

    @property
    def options(self) -> list[str]:
        """Return list of available looks."""
        looks = self.coordinator.data.get("looks", [])
        look_names = []

        for look in looks:
            look_id = look.get("id", {})
            if look_id:
                look_name = look_id.get("name", "Unknown")
                look_names.append(look_name)

        return look_names

    @property
    def current_option(self) -> str | None:
        """Return the currently active look."""
        current_look = self.coordinator.data.get("current_look")

        if not current_look:
            return None

        look_id = current_look.get("id", {})
        if look_id:
            return look_id.get("name")

        return None

    async def async_select_option(self, option: str) -> None:
        """Trigger the selected look."""
        # Use lock to prevent concurrent look changes
        async with self._processing_lock:
            # Store the pending look
            self._pending_look = option

            looks = self.coordinator.data.get("looks", [])

            # Find the look UUID by name
            look_uuid = None
            for look in looks:
                if get_nested_value(look, "id", "name") == option:
                    look_uuid = get_nested_value(look, "id", "uuid")
                    break

            if not look_uuid:
                _LOGGER.error("Could not find look: %s", option)
                self._pending_look = None
                return

            try:
                # Trigger the look
                await self.api.trigger_look(look_uuid)

                # No need to poll - streaming will update automatically
                self._pending_look = None

            except Exception as e:
                _LOGGER.error("Error setting look %s: %s", option, e)
                self._pending_look = None
            except Exception as e:
                _LOGGER.error("Error triggering look: %s", e, exc_info=True)
                self._pending_look = None


class ProPresenterMacroSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for triggering macros."""

    _attr_icon = "mdi:alpha-m-box-outline"
    _attr_name = "Trigger Macro"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the macro select entity."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_macro_trigger"
        self.api = coordinator.api
        self._current_selection = "Select Macro"
        self._macro_uuid_map = {}  # Map display names to UUIDs

    @property
    def options(self) -> list[str]:
        """Return the list of available macro names with unique display names."""
        # Always include "Select Macro" as the first/default option
        macro_names = ["Select Macro"]
        self._macro_uuid_map = {}  # Reset map

        # Track name occurrences to make duplicates unique
        name_counts = {}

        macros = self.coordinator.data.get("macros", [])
        for macro in macros:
            macro_id = macro.get("id", {})
            if isinstance(macro_id, dict):
                macro_name = macro_id.get("name")
                macro_uuid = macro_id.get("uuid")
                if macro_name and macro_uuid:
                    # Check if we've seen this name before
                    if macro_name in name_counts:
                        name_counts[macro_name] += 1
                        # Make it unique by appending the count
                        display_name = f"{macro_name} ({name_counts[macro_name]})"
                    else:
                        name_counts[macro_name] = 1
                        display_name = macro_name

                    macro_names.append(display_name)
                    self._macro_uuid_map[display_name] = macro_uuid

        return macro_names

    @property
    def current_option(self) -> str:
        """Return the current selection."""
        return self._current_selection

    async def async_select_option(self, option: str) -> None:
        """Trigger the selected macro and reset to Select Macro."""
        if option == "Select Macro":
            # Just update the state
            self._current_selection = "Select Macro"
            self.async_write_ha_state()
            return

        try:
            _LOGGER.debug("Triggering macro: %s", option)

            # Temporarily set to the selected option so frontend sees the change
            self._current_selection = option
            self.async_write_ha_state()

            # Look up the UUID from our map
            macro_uuid = self._macro_uuid_map.get(option)

            if macro_uuid:
                # Trigger the macro
                await self.api.trigger_macro(macro_uuid)
            else:
                _LOGGER.error("Could not find UUID for macro: %s", option)

            # Reset to "Select Macro" after triggering
            import asyncio

            await asyncio.sleep(0.5)  # Brief delay so user sees selection
            self._current_selection = "Select Macro"
            self.async_write_ha_state()

        except Exception as e:
            _LOGGER.error("Error triggering macro: %s", e, exc_info=True)
            # Reset to Select Macro even on error
            self._current_selection = "Select Macro"
            self.async_write_ha_state()


class ProPresenterVideoInputSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for triggering video inputs.

    Note: ProPresenter API does not provide feedback on which video input
    is currently active, so this entity cannot display the current selection.
    """

    _attr_icon = "mdi:message-video"
    _attr_name = "Trigger Video Input"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            streaming_coordinator, config_entry, static_coordinator=coordinator
        )
        self.api = coordinator.api  # Keep reference to API for actions
        self._attr_unique_id = f"{config_entry.entry_id}_video_input"
        self._current_selection = "Select Video Input"

    @property
    def options(self) -> list[str]:
        """Return list of available video inputs."""
        # Always include "Select Video Input" as the first/default option
        input_names = ["Select Video Input"]

        # Get video inputs from static coordinator data
        video_inputs = self.static_coordinator.data.get("video_inputs", [])

        for video_input in video_inputs:
            input_name = video_input.get("name")
            if input_name:
                input_names.append(input_name)

        return input_names if len(input_names) > 1 else ["No video inputs available"]

    @property
    def current_option(self) -> str:
        """Return the current selection.

        Note: ProPresenter does not provide feedback on active video input,
        so this always returns to the default after triggering.
        """
        return self._current_selection

    async def async_select_option(self, option: str) -> None:
        """Trigger the selected video input and reset to default."""
        if option == "Select Video Input":
            # Just update the state
            self._current_selection = "Select Video Input"
            self.async_write_ha_state()
            return

        try:
            _LOGGER.debug("Triggering video input: %s", option)

            # Temporarily set to the selected option so frontend sees the change
            self._current_selection = option
            self.async_write_ha_state()

            # Get video inputs from static coordinator data
            video_inputs = self.static_coordinator.data.get("video_inputs", [])

            # Find the UUID for the selected video input name
            selected_uuid = None
            for video_input in video_inputs:
                if video_input.get("name") == option:
                    selected_uuid = video_input.get("uuid")
                    break

            if selected_uuid:
                # Trigger the video input
                await self.api.trigger_video_input(selected_uuid)

                # Reset to "Select Video Input" after triggering
                await asyncio.sleep(0.5)  # Brief delay so user sees selection
                self._current_selection = "Select Video Input"
                self.async_write_ha_state()
            else:
                _LOGGER.error("Could not find UUID for video input: %s", option)
                raise HomeAssistantError(f"Could not find video input: {option}")

            # Reset to "Select Video Input" after triggering
            await asyncio.sleep(0.5)  # Brief delay so user sees selection
            self._current_selection = "Select Video Input"
            self.async_write_ha_state()

        except HomeAssistantError:
            # Re-raise HomeAssistantError to show to user
            self._current_selection = "Select Video Input"
            self.async_write_ha_state()
            raise
        except Exception as err:
            _LOGGER.error("Error triggering video input '%s': %s", option, err)

            # Reset and show error to user
            self._current_selection = "Select Video Input"
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Failed to trigger video input '{option}'. "
                "Note: ProPresenter does not provide feedback on which video input is currently active."
            ) from err
