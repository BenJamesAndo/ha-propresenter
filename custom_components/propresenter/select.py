"""Select platform for ProPresenter integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .base import ProPresenterBaseEntity
from .const import DOMAIN
from .coordinator import ProPresenterCoordinator, ProPresenterStreamingCoordinator
from .utils import generate_slide_label, get_nested_value, make_unique_display_name

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ProPresenter select entities."""
    coordinator: ProPresenterCoordinator = config_entry.runtime_data["coordinator"]
    streaming_coordinator: ProPresenterStreamingCoordinator = config_entry.runtime_data["streaming_coordinator"]
    
    _LOGGER.debug("Setting up ProPresenter select entities")
    _LOGGER.debug("Streaming coordinator data keys: %s", streaming_coordinator.data.keys() if streaming_coordinator.data else "No data")
    
    # Get stage screens from streaming coordinator data
    stage_screens = streaming_coordinator.data.get("stage_screens", [])
    stage_layouts = streaming_coordinator.data.get("stage_layouts", [])
    
    _LOGGER.debug("Found %d stage screens", len(stage_screens))
    _LOGGER.debug("Stage screens data: %s", stage_screens)
    _LOGGER.debug("Found %d stage layouts", len(stage_layouts))
    
    # Create a select entity for each stage screen
    entities = []
    for screen in stage_screens:
        # ProPresenter uses 'uuid' not 'id' for stage screens
        screen_id = screen.get("uuid") or screen.get("id")
        screen_name = screen.get("name", "Unknown")
        _LOGGER.debug("Processing screen: %s (ID: %s)", screen_name, screen_id)
        if screen_id:
            entities.append(
                ProPresenterStageLayoutSelect(coordinator, streaming_coordinator, config_entry, screen_id)
            )
    
    # Props are now handled by media_player platform (ProPresenterPropMediaPlayer)
    
    # Create a select entity for playlists
    entities.append(ProPresenterPlaylistSelect(coordinator, streaming_coordinator, config_entry))
    
    # Create a select entity for presentation slides (uses streaming coordinator for real-time updates)
    entities.append(ProPresenterSlideSelect(coordinator, streaming_coordinator, config_entry))
    
    # Create a select entity for announcement slides (uses streaming coordinator for real-time updates)
    entities.append(ProPresenterAnnouncementSlideSelect(coordinator, streaming_coordinator, config_entry))
    
    # Create a select entity for looks (from streaming coordinator)
    looks = streaming_coordinator.data.get("looks", [])
    if looks:
        _LOGGER.debug("Found %d looks", len(looks))
        entities.append(ProPresenterLookSelect(coordinator, streaming_coordinator, config_entry))
    
    # Create a select entity for macros
    macros = coordinator.data.get("macros", [])
    if macros:
        _LOGGER.debug("Found %d macros", len(macros))
        entities.append(ProPresenterMacroSelect(coordinator, config_entry))
    
    # Create a select entity for video inputs
    video_inputs = coordinator.data.get("video_inputs", [])
    if video_inputs:
        _LOGGER.debug("Found %d video inputs", len(video_inputs))
        entities.append(ProPresenterVideoInputSelect(coordinator, streaming_coordinator, config_entry))
    
    _LOGGER.info("Creating %d select entities", len(entities))
    if entities:
        async_add_entities(entities)
    else:
        _LOGGER.warning("No stage screens or props found - no select entities will be created")

class ProPresenterStageLayoutSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for choosing stage layout on a specific screen."""

    _attr_translation_key = "stage_layout"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        screen_id: str,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(streaming_coordinator, config_entry, static_coordinator=coordinator)
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
            layout_name = layout_data.get("name") if isinstance(layout_data, dict) else layout.get("name")
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
        await self.api.set_stage_screen_layout(
            self._screen_id, selected_layout_uuid
        )
        
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
        super().__init__(streaming_coordinator, config_entry, static_coordinator=static_coordinator)
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
            _LOGGER.debug("Clearing all props")
            await self.api.trigger_clear_layer("props")
        else:
            # Look up the UUID from our map
            selected_prop_uuid = self._prop_uuid_map.get(option)
            
            if not selected_prop_uuid:
                _LOGGER.error("Could not find prop UUID for: %s", option)
                return
            
            _LOGGER.debug("Triggering prop %s (UUID: %s)", option, selected_prop_uuid)
            
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
        audio_playlist_details_list = self.coordinator.data.get("audio_playlist_details_list", [])
        
        if not audio_playlist_details_list:
            return ["No Playlists"]
        
        track_options = []
        
        # Iterate through all playlists
        for playlist_details in audio_playlist_details_list:
            playlist_name = get_nested_value(playlist_details, "id", "name", default="Unknown Playlist")
            items = playlist_details.get("items", [])
            
            if not items:
                continue
            
            # Add tracks from this playlist
            for item in items:
                if item.get("type") == "audio":
                    track_name = get_nested_value(item, "id", "name", default="Unknown Track")
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
            audio_playlist_details_list = self.coordinator.data.get("audio_playlist_details_list", [])
            
            if not audio_playlist_details_list:
                _LOGGER.error("No audio playlist data available")
                return
            
            # Search through all playlists to find the track
            playlist_uuid = None
            track_uuid = None
            found = False
            
            for playlist_details in audio_playlist_details_list:
                current_playlist_uuid = get_nested_value(playlist_details, "id", "uuid")
                playlist_name = get_nested_value(playlist_details, "id", "name", default="Unknown Playlist")
                items = playlist_details.get("items", [])
                
                for item in items:
                    if item.get("type") == "audio":
                        track_name = get_nested_value(item, "id", "name", default="")
                        # Remove .mp3 extension for comparison
                        display_track_name = track_name[:-4] if track_name.endswith(".mp3") else track_name
                        
                        # Check if this is the selected track
                        # Handle both "Playlist - Track" and "Track" formats
                        if len(audio_playlist_details_list) > 1:
                            full_display_name = f"{playlist_name} - {display_track_name}"
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
            
            _LOGGER.debug(f"Triggering audio track: {option} (playlist: {playlist_uuid}, track: {track_uuid})")
            await self.coordinator.api.trigger_audio_track(playlist_uuid, track_uuid)
            
        except Exception as e:
            _LOGGER.error(f"Error selecting audio track: {e}")
            raise


class ProPresenterPlaylistSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for presentation playlists."""

    _attr_name = "Playlist"
    _attr_icon = "mdi:playlist-music"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the playlist select entity."""
        # Use streaming coordinator for frequent updates, static coordinator for playlist list
        super().__init__(streaming_coordinator, config_entry, static_coordinator=coordinator)
        self.api = coordinator.api
        self._attr_unique_id = f"{config_entry.entry_id}_playlist"
        self._playlists_cache = {}  # Cache: {display_name: playlist_uuid}
        self._playlists_order = []  # Maintain order
        self._focused_playlist_uuid = None  # Currently focused playlist UUID
        _LOGGER.debug("ProPresenterPlaylistSelect initialized")

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass, populate the playlists cache."""
        await super().async_added_to_hass()
        _LOGGER.debug("ProPresenterPlaylistSelect added to hass - populating playlists cache")
        _LOGGER.debug("Static coordinator data keys: %s", self.static_coordinator.data.keys() if self.static_coordinator.data else "No data")
        self._update_playlists_cache()
        # Get initial focused playlist
        await self._update_focused_playlist()

    def _update_playlists_cache(self) -> None:
        """Build a cache of playlists from the static coordinator."""
        self._playlists_cache = {}
        self._playlists_order = []
        
        try:
            # Get presentation playlists from static coordinator
            playlists = self.static_coordinator.data.get("presentation_playlists", [])
            
            if not playlists:
                _LOGGER.warning("No presentation playlists found in coordinator data!")
                _LOGGER.debug("Coordinator data keys: %s", list(self.static_coordinator.data.keys()) if self.static_coordinator.data else "No data")
                return
            
            _LOGGER.debug("Found %d presentation playlists", len(playlists))
            _LOGGER.debug("First playlist structure: %s", playlists[0] if playlists else "None")
            
            # Build cache of playlist names to UUIDs
            def process_playlist(playlist, level=0):
                """Recursively process playlists and nested folders."""
                playlist_type = playlist.get("field_type", "")  # ProPresenter uses "field_type" not "type"
                playlist_id = playlist.get("id", {})
                playlist_name = playlist_id.get("name", "Unknown")
                playlist_uuid = playlist_id.get("uuid")
                
                _LOGGER.debug("Processing playlist at level %d: name=%s, type=%s, uuid=%s", 
                            level, playlist_name, playlist_type, playlist_uuid)
                
                # Only add actual playlists, not folders/groups
                if playlist_type == "playlist" and playlist_uuid:
                    # Make display name unique if necessary
                    display_name = playlist_name
                    counter = 1
                    while display_name in self._playlists_cache:
                        display_name = f"{playlist_name} ({counter})"
                        counter += 1
                    
                    self._playlists_cache[display_name] = playlist_uuid
                    self._playlists_order.append(display_name)
                    _LOGGER.debug("Added playlist '%s' (UUID: %s)", display_name, playlist_uuid)
                elif playlist_type == "group":
                    _LOGGER.debug("Skipping group/folder: %s", playlist_name)
                else:
                    _LOGGER.debug("Unknown playlist type '%s' for: %s", playlist_type, playlist_name)
                
                # Process children (nested playlists)
                children = playlist.get("children", [])
                for child in children:
                    process_playlist(child, level + 1)
            
            for playlist in playlists:
                process_playlist(playlist)
            
            _LOGGER.info("Cached %d playlists", len(self._playlists_cache))
            if self._playlists_cache:
                _LOGGER.debug("Cached playlist names: %s", list(self._playlists_cache.keys())[:5])  # Show first 5
            else:
                _LOGGER.warning("Playlists were found but none were added to cache! Check playlist structure.")
            
        except Exception as e:
            _LOGGER.error("Error updating playlists cache: %s", e, exc_info=True)

    async def _update_focused_playlist(self) -> None:
        """Update the currently focused playlist."""
        try:
            focused = await self.api.get_focused_playlist()
            if focused:
                # The focused endpoint returns {playlist: {uuid, name, index}, item: ..., playlist_item: ...}
                playlist_info = focused.get("playlist")
                if playlist_info:
                    self._focused_playlist_uuid = playlist_info.get("uuid")
                else:
                    self._focused_playlist_uuid = None
                # Trigger state update
                self.async_write_ha_state()
            else:
                self._focused_playlist_uuid = None
                self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Error getting focused playlist: %s", e, exc_info=True)
            self._focused_playlist_uuid = None

    @property
    def options(self) -> list[str]:
        """Return list of available playlists in order."""
        if not self._playlists_order:
            _LOGGER.debug("No playlists in cache!")
            return ["No Playlists Available"]
        return self._playlists_order

    @property
    def current_option(self) -> str | None:
        """Return the currently focused playlist."""
        if not self._focused_playlist_uuid:
            return None
        
        # Find the display name for this UUID
        for display_name, uuid in self._playlists_cache.items():
            if uuid == self._focused_playlist_uuid:
                return display_name
        
        return None

    async def async_select_option(self, option: str) -> None:
        """Focus the selected playlist."""
        # Ignore placeholder options
        if option in ["No Playlists Available"]:
            _LOGGER.warning("Cannot select placeholder option: %s", option)
            return
        
        if option not in self._playlists_cache:
            _LOGGER.error("Could not find playlist: %s", option)
            _LOGGER.debug("Available playlists: %s", list(self._playlists_cache.keys()))
            return
            _LOGGER.error("Could not find playlist: %s", option)
            return
        
        playlist_uuid = self._playlists_cache[option]
        _LOGGER.info("Focusing playlist %s (UUID: %s)", option, playlist_uuid)
        
        try:
            await self.api.focus_playlist(playlist_uuid)
            # Update our cached focused playlist immediately
            self._focused_playlist_uuid = playlist_uuid
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Error focusing playlist: %s", e, exc_info=True)

    async def async_update(self) -> None:
        """Update the list of playlists and focused playlist."""
        _LOGGER.debug("ProPresenterPlaylistSelect.async_update() called")
        await super().async_update()
        # Refresh cache when manual refresh is triggered
        self._update_playlists_cache()
        # Update focused playlist
        await self._update_focused_playlist()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Poll for focused playlist on each coordinator update (every 30 seconds)
        # This is more efficient than polling on every streaming update
        self.hass.async_create_task(self._update_focused_playlist())
        super()._handle_coordinator_update()


class ProPresenterSlideSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for presentation slides - shows all slides from all presentations in focused playlist."""

    _attr_name = "Presentation slide"
    _attr_icon = "mdi:presentation"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the slide select entity."""
        # Use streaming coordinator for real-time updates, coordinator for API access
        super().__init__(streaming_coordinator, config_entry, static_coordinator=coordinator)
        self.api = coordinator.api
        self._attr_unique_id = f"{config_entry.entry_id}_presentation_slide"
        self._slides_cache = {}  # Cache: {display_name: (presentation_uuid, slide_index)}
        self._reverse_cache = {}  # Cache: {(presentation_uuid, slide_index): display_name}
        self._slides_order = []  # Ordered list of display names to maintain slide order
        self._focused_playlist_uuid = None  # Currently focused playlist UUID
        self._presentation_uuids_in_cache = set()  # Track which presentations are in our cache
        self._skip_next_presentation_check = False  # Skip presentation check after playlist change
        _LOGGER.debug("ProPresenterSlideSelect initialized")

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass, populate the slides cache."""
        await super().async_added_to_hass()
        _LOGGER.debug("ProPresenterSlideSelect added to hass - populating slides cache")
        # Populate cache in background to avoid blocking startup
        self.hass.async_create_task(self._update_slides_cache())

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Check if the focused playlist might have changed - refresh cache periodically
        self.hass.async_create_task(self._check_and_update_cache())
        super()._handle_coordinator_update()

    async def _check_and_update_cache(self) -> None:
        """Check if we need to update cache (playlist changed or active presentation changed)."""
        try:
            focused = await self.api.get_focused_playlist()
            
            # Get active presentation UUID
            active_presentation = self.coordinator.data.get("active_presentation", {})
            presentation = active_presentation.get("presentation")
            active_pres_uuid = None
            if presentation:
                active_pres_uuid = get_nested_value(presentation, "id", "uuid")
            
            # Track what changed
            focused_uuid = None
            if focused and "playlist" in focused:
                playlist_info = focused.get("playlist", {})
                focused_uuid = playlist_info.get("uuid")
            
            # Check if playlist changed
            playlist_changed = focused_uuid != self._focused_playlist_uuid
            
            # Check if active presentation changed
            presentation_changed = False
            if self._presentation_uuids_in_cache and not self._skip_next_presentation_check:
                # We have a cache - check if active presentation is different
                presentation_changed = active_pres_uuid not in self._presentation_uuids_in_cache
            
            if playlist_changed:
                _LOGGER.info("Focused playlist changed - reloading (this clears any Library presentations)")
                # Pass flag to indicate playlist changed - don't add active presentation
                await self._update_slides_cache(playlist_just_changed=True)
                self._skip_next_presentation_check = True  # Skip next check to avoid re-adding old presentation
                self.async_write_ha_state()  # Force UI update
            elif presentation_changed and active_pres_uuid:
                _LOGGER.info("Active presentation changed to one not in cache - updating slides cache")
                await self._update_slides_cache(playlist_just_changed=False)
                self.async_write_ha_state()  # Force UI update after adding new presentation
            else:
                # Reset skip flag if nothing changed
                self._skip_next_presentation_check = False
                
        except Exception as e:
            _LOGGER.debug("Error checking focused playlist: %s", e)

    async def async_update(self) -> None:
        """Update the list of slides from focused playlist."""
        _LOGGER.debug("ProPresenterSlideSelect.async_update() called")
        await super().async_update()
        # Manual refresh - always update cache
        await self._update_slides_cache(playlist_just_changed=False)

    async def _update_slides_cache(self, playlist_just_changed: bool = False) -> None:
        """Build a cache of slides.
        
        Strategy (Option C):
        1. Always load all slides from the focused playlist
        2. If active presentation is NOT in the playlist, also add its slides
        3. Result: Combined view of playlist + any active Library presentations
        
        This gives maximum flexibility - you always see your playlist slides,
        but can also control Library presentations that the PP operator triggers.
        """
        self._slides_cache = {}
        self._reverse_cache = {}
        self._slides_order = []
        self._presentation_uuids_in_cache = set()
        
        try:
            # Get the currently focused playlist
            focused = await self.api.get_focused_playlist()
            
            if not focused:
                # Truly no focused playlist - fall back to active presentation
                _LOGGER.info("No focused playlist available - showing active presentation only")
                await self._load_slides_from_active_presentation()
                return
            
            playlist_info = focused.get("playlist")
            if not playlist_info:
                # Playlist key is None or missing - fall back to active presentation
                _LOGGER.info("No focused playlist available - showing active presentation only")
                await self._load_slides_from_active_presentation()
                return
                
            focused_playlist_uuid = playlist_info.get("uuid")
            playlist_name = playlist_info.get("name", "Unknown Playlist")
            
            if not focused_playlist_uuid:
                _LOGGER.warning("Focused playlist has no UUID - showing active presentation only")
                await self._load_slides_from_active_presentation()
                return
            
            # Always load the focused playlist slides first
            _LOGGER.info("Loading slides from focused playlist: %s", playlist_name)
            self._focused_playlist_uuid = focused_playlist_uuid
            await self._load_slides_from_playlist(focused_playlist_uuid, playlist_name)
            
            # Only add active presentation if playlist didn't just change
            if playlist_just_changed:
                _LOGGER.info("Playlist just changed - not adding active presentation yet")
            else:
                # Now check if active presentation is in the playlist
                active_presentation = self.coordinator.data.get("active_presentation", {})
                presentation = active_presentation.get("presentation")
                active_pres_uuid = None
                if presentation:
                    active_pres_uuid = get_nested_value(presentation, "id", "uuid")
                
                # If there's an active presentation that's NOT already in our cache, add it
                if active_pres_uuid and active_pres_uuid not in self._presentation_uuids_in_cache:
                    _LOGGER.info("Active presentation is NOT in playlist - adding its slides as well")
                    await self._load_additional_presentation(active_pres_uuid)
            
            # Update HA state
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error("Error updating slides cache: %s", e, exc_info=True)

    async def _load_slides_from_playlist(self, playlist_uuid: str, playlist_name: str) -> None:
        """Load all slides from all presentations in the specified playlist."""
        # Note: _focused_playlist_uuid is set by caller
        # Reset presentation tracking (caller already reset main caches)
        
        _LOGGER.info("Fetching slides from focused playlist: %s (UUID: %s)", 
                    playlist_name, playlist_uuid)
        
        # Fetch the full playlist details to get items
        playlist_details = await self.api.get_presentation_playlist_details(playlist_uuid)
        if not playlist_details:
            _LOGGER.warning("Could not fetch details for focused playlist")
            return
        
        # Get all items in the focused playlist
        items = playlist_details.get("items", [])
        
        if not items:
            _LOGGER.info("No items in focused playlist")
            return
        
        _LOGGER.debug("Found %d items in focused playlist", len(items))
        
        # Process each presentation in the playlist
        for item in items:
            item_type = item.get("type", "")
            
            # Only process presentation items (not headers, etc.)
            if item_type != "presentation":
                continue
            
            # Check the item's destination field (not the presentation's)
            # This is what determines how it behaves in the playlist
            item_destination = item.get("destination", "")
            if item_destination != "presentation":
                _LOGGER.debug("Skipping playlist item - destination is %s (not 'presentation')", item_destination)
                continue
            
            pres_uuid = get_nested_value(item, "presentation_info", "presentation_uuid")
            pres_name = get_nested_value(item, "id", "name", default="Unknown")
            
            if not pres_uuid:
                continue
            
            try:
                # Fetch presentation details to get slides
                pres_details = await self.api.get_presentation_details(pres_uuid)
                if not pres_details:
                    _LOGGER.warning("Could not fetch details for presentation %s", pres_uuid)
                    continue
                
                # Navigate to presentation.groups[].slides[]
                presentation_data = pres_details.get("presentation", {})
                
                # Track this presentation UUID (after all checks pass)
                self._presentation_uuids_in_cache.add(pres_uuid)
                
                groups = presentation_data.get("groups", [])
                
                slide_index = 0  # Global slide index across all groups
                for group in groups:
                    group_slides = group.get("slides", [])
                    
                    for slide in group_slides:
                        slide_label = generate_slide_label(slide, slide_index)
                        display_name = f"{pres_name} > {slide_label}"
                        display_name = make_unique_display_name(display_name, self._slides_cache, slide_index)
                        
                        self._slides_cache[display_name] = (pres_uuid, slide_index)
                        self._reverse_cache[(pres_uuid, slide_index)] = display_name
                        self._slides_order.append(display_name)
                        slide_index += 1
                
                _LOGGER.debug("Cached %d slides from presentation '%s'", slide_index, pres_name)
                
            except Exception as e:
                _LOGGER.warning("Error fetching slides for presentation %s: %s", pres_uuid, e)
                continue
        
        _LOGGER.info("Cached %d total slides from focused playlist '%s'", 
                    len(self._slides_cache), playlist_name)

    async def _load_slides_from_active_presentation(self) -> None:
        """Load slides from the currently active presentation (fallback when no playlist is focused)."""
        self._focused_playlist_uuid = None
        self._presentation_uuids_in_cache = set()  # Reset
        
        # Get the currently active presentation from streaming coordinator
        active_presentation = self.coordinator.data.get("active_presentation", {})
        if not active_presentation:
            _LOGGER.info("No active presentation")
            return
        
        presentation = active_presentation.get("presentation")
        if not presentation:
            _LOGGER.info("No presentation in active_presentation data")
            return
        
        pres_uuid = get_nested_value(presentation, "id", "uuid")
        pres_name = get_nested_value(presentation, "id", "name", default="Unknown")
        
        if not pres_uuid:
            _LOGGER.info("No UUID in active presentation")
            return
        
        _LOGGER.info("Fetching slides from active presentation: %s (UUID: %s)", pres_name, pres_uuid)
        
        try:
            # Fetch full presentation details to get slides
            pres_details = await self.api.get_presentation_details(pres_uuid)
            if not pres_details:
                _LOGGER.warning("Could not fetch details for presentation %s", pres_uuid)
                return
            
            # Navigate to presentation.groups[].slides[]
            presentation_data = pres_details.get("presentation", {})
            
            # Filter by destination - only include "presentation" types (not announcements)
            destination = presentation_data.get("destination", "")
            if destination != "presentation":
                _LOGGER.debug("Skipping active presentation %s - destination is %s (not 'presentation')", pres_name, destination)
                return
            
            # Track this presentation UUID (only after destination check passes)
            self._presentation_uuids_in_cache.add(pres_uuid)
            
            groups = presentation_data.get("groups", [])
            
            slide_index = 0  # Global slide index across all groups
            for group in groups:
                group_slides = group.get("slides", [])
                
                for slide in group_slides:
                    slide_label = generate_slide_label(slide, slide_index)
                    display_name = f"{pres_name} > {slide_label}"
                    display_name = make_unique_display_name(display_name, self._slides_cache, slide_index)
                    
                    self._slides_cache[display_name] = (pres_uuid, slide_index)
                    self._reverse_cache[(pres_uuid, slide_index)] = display_name
                    self._slides_order.append(display_name)
                    slide_index += 1
            
            _LOGGER.info("Cached %d slides from active presentation '%s'", 
                        len(self._slides_cache), pres_name)
            
        except Exception as e:
            _LOGGER.error("Error fetching slides from active presentation: %s", e, exc_info=True)

    async def _load_additional_presentation(self, pres_uuid: str) -> None:
        """Load slides from a specific presentation and add them to the existing cache.
        
        This is used to add slides from the active presentation when it's not in the playlist.
        """
        _LOGGER.info("Loading additional presentation: UUID %s", pres_uuid)
        
        try:
            # Fetch full presentation details to get slides and name
            pres_details = await self.api.get_presentation_details(pres_uuid)
            if not pres_details:
                _LOGGER.warning("Could not fetch details for presentation %s", pres_uuid)
                return
            
            # Navigate to presentation data
            presentation_data = pres_details.get("presentation", {})
            pres_id = presentation_data.get("id", {})
            pres_name = pres_id.get("name", "Unknown")
            
            # Filter by destination - only include "presentation" types
            destination = presentation_data.get("destination", "")
            if destination != "presentation":
                _LOGGER.debug("Skipping presentation %s - destination is %s", pres_name, destination)
                return
            
            groups = presentation_data.get("groups", [])
            
            # Track this presentation
            self._presentation_uuids_in_cache.add(pres_uuid)
            
            slide_index = 0  # Global slide index across all groups
            added_count = 0
            for group in groups:
                group_slides = group.get("slides", [])
                
                for slide in group_slides:
                    slide_label = generate_slide_label(slide, slide_index)
                    # Prefix with "★ " to indicate this is from outside the playlist
                    display_name = f"★ {pres_name} > {slide_label}"
                    display_name = make_unique_display_name(display_name, self._slides_cache, slide_index)
                    
                    self._slides_cache[display_name] = (pres_uuid, slide_index)
                    self._reverse_cache[(pres_uuid, slide_index)] = display_name
                    self._slides_order.append(display_name)
                    slide_index += 1
                    added_count += 1
            
            _LOGGER.info("Added %d slides from additional presentation '%s'", added_count, pres_name)
            
        except Exception as e:
            _LOGGER.error("Error fetching slides from additional presentation: %s", e, exc_info=True)

    @property
    def options(self) -> list[str]:
        """Return list of available slides from focused playlist."""
        if not self._slides_order:
            if self._focused_playlist_uuid:
                return ["No Slides in Focused Playlist"]
            else:
                return ["No Focused Playlist"]
        return self._slides_order

    @property
    def current_option(self) -> str | None:
        """Return the currently active slide."""
        try:
            # Get the slide index data from coordinator (which is the streaming coordinator)
            slide_index_data = self.coordinator.data.get("slide_index")
            if not slide_index_data:
                return None
            
            # Extract presentation UUID and slide index
            # Structure: {"presentation_index": {"index": 1, "presentation_id": {"uuid": "...", "name": "..."}}}
            presentation_index_info = slide_index_data.get("presentation_index", {})
            if not presentation_index_info:
                return None
                
            pres_info = presentation_index_info.get("presentation_id", {})
            pres_uuid = pres_info.get("uuid")
            slide_index = presentation_index_info.get("index")
            
            if pres_uuid is None or slide_index is None:
                return None
            
            # Look up the display name from our reverse cache
            lookup_key = (pres_uuid, slide_index)
            display_name = self._reverse_cache.get(lookup_key)
            
            # If slide not in cache (presentation not in focused playlist), return None
            if display_name is None:
                _LOGGER.debug("Current slide (uuid=%s, index=%s) not in focused playlist cache", 
                           pres_uuid, slide_index)
                return None
            
            return display_name
            
        except Exception as e:
            _LOGGER.error("Error getting current option: %s", e, exc_info=True)
            return None

    async def async_select_option(self, option: str) -> None:
        """Trigger the selected slide."""
        if option not in self._slides_cache:
            _LOGGER.error("Could not find slide: %s", option)
            return
        
        presentation_uuid, slide_index = self._slides_cache[option]
        _LOGGER.info("Triggering slide %s (presentation: %s, slide: %d)", 
                     option, presentation_uuid, slide_index)
        
        try:
            await self.api.trigger_slide(presentation_uuid, slide_index)
        except Exception as e:
            _LOGGER.error("Error triggering slide: %s", e, exc_info=True)


class ProPresenterAnnouncementSlideSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for triggering announcement slides."""

    _attr_name = "Announcement slide"
    _attr_icon = "mdi:bullhorn"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the announcement slide select entity."""
        # Use streaming coordinator for real-time updates, coordinator for API access
        super().__init__(streaming_coordinator, config_entry, static_coordinator=coordinator)
        self.api = coordinator.api
        self._attr_unique_id = f"{config_entry.entry_id}_announcement_slide"
        self._slides_cache = {}  # Cache: {display_name: (presentation_uuid, slide_index)}
        self._reverse_cache = {}  # Cache: {(presentation_uuid, slide_index): display_name}
        self._slides_order = []  # Ordered list of display names to maintain slide order
        self._focused_playlist_uuid = None  # Currently focused playlist UUID
        _LOGGER.debug("ProPresenterAnnouncementSlideSelect initialized")

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass, populate the slides cache."""
        await super().async_added_to_hass()
        _LOGGER.debug("ProPresenterAnnouncementSlideSelect added to hass - populating slides cache")
        # Populate cache in background to avoid blocking startup
        self.hass.async_create_task(self._update_slides_cache())

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Check if the focused playlist might have changed - refresh cache periodically
        self.hass.async_create_task(self._check_and_update_cache())
        super()._handle_coordinator_update()

    async def _check_and_update_cache(self) -> None:
        """Check if focused playlist changed and update cache if needed."""
        try:
            focused = await self.api.get_focused_playlist()
            
            if focused:
                # There's a focused playlist
                playlist_info = focused.get("playlist", {})
                focused_uuid = playlist_info.get("uuid")
                
                # Only update if the focused playlist actually changed
                if focused_uuid != self._focused_playlist_uuid:
                    _LOGGER.info("Focused playlist changed - updating announcement slides cache")
                    await self._update_slides_cache()
            else:
                # No focused playlist available
                if self._focused_playlist_uuid is not None:
                    # We were showing playlist slides, now clear
                    _LOGGER.info("Focused playlist removed - clearing announcement slides")
                    self._focused_playlist_uuid = None
                    await self._update_slides_cache()
        except Exception as e:
            _LOGGER.debug("Error checking focused playlist: %s", e)

    async def async_update(self) -> None:
        """Update the list of slides from all announcements."""
        _LOGGER.debug("ProPresenterAnnouncementSlideSelect.async_update() called")
        await super().async_update()
        # Manual refresh - always update cache
        await self._update_slides_cache()
        _LOGGER.debug("async_update complete - cache has %d announcement slides", len(self._slides_cache))

    async def _update_slides_cache(self) -> None:
        """Build a cache of slides from announcements in the focused playlist."""
        self._slides_cache = {}
        self._reverse_cache = {}
        self._slides_order = []
        
        try:
            # Get the currently focused playlist
            focused = await self.api.get_focused_playlist()
            
            if not focused:
                _LOGGER.info("No focused playlist available for announcements")
                return
            
            playlist_info = focused.get("playlist")
            if not playlist_info:
                _LOGGER.info("No focused playlist available for announcements")
                return
                
            focused_playlist_uuid = playlist_info.get("uuid")
            playlist_name = playlist_info.get("name", "Unknown Playlist")
            
            if not focused_playlist_uuid:
                _LOGGER.warning("Focused playlist has no UUID")
                return
            
            _LOGGER.info("Loading announcement slides from focused playlist: %s", playlist_name)
            self._focused_playlist_uuid = focused_playlist_uuid
            
            # Fetch the full playlist details to get items
            playlist_details = await self.api.get_presentation_playlist_details(focused_playlist_uuid)
            if not playlist_details:
                _LOGGER.warning("Could not fetch details for focused playlist")
                return
            
            # Get all items in the focused playlist
            items = playlist_details.get("items", [])
            
            if not items:
                _LOGGER.info("No items in focused playlist")
                return
            
            _LOGGER.debug("Found %d items in focused playlist", len(items))
            
            # Process each item in the playlist
            announcement_count = 0
            for item in items:
                item_type = item.get("type", "")
                
                # Only process presentation items (not headers, etc.)
                if item_type != "presentation":
                    continue
                
                # Check the item's destination field - only load announcements
                item_destination = item.get("destination", "")
                if item_destination != "announcements":
                    continue
                
                pres_uuid = get_nested_value(item, "presentation_info", "presentation_uuid")
                pres_name = get_nested_value(item, "id", "name", default="Unknown")
                
                if not pres_uuid:
                    continue
                
                try:
                    # Fetch presentation details to get slides
                    pres_details = await self.api.get_presentation_details(pres_uuid)
                    if not pres_details:
                        _LOGGER.warning("Could not fetch details for announcement %s", pres_uuid)
                        continue
                    
                    # Navigate to presentation.groups[].slides[]
                    presentation_data = pres_details.get("presentation", {})
                    announcement_count += 1
                    groups = presentation_data.get("groups", [])
                    
                    slide_index = 0  # Global slide index across all groups
                    for group in groups:
                        group_slides = group.get("slides", [])
                        
                        for slide in group_slides:
                            slide_label = generate_slide_label(slide, slide_index)
                            display_name = f"{pres_name} > {slide_label}"
                            display_name = make_unique_display_name(display_name, self._slides_cache, slide_index)
                            
                            self._slides_cache[display_name] = (pres_uuid, slide_index)
                            self._reverse_cache[(pres_uuid, slide_index)] = display_name
                            self._slides_order.append(display_name)
                            slide_index += 1
                    
                    _LOGGER.debug("Cached %d slides from announcement '%s'", slide_index, pres_name)
                
                except Exception as e:
                    _LOGGER.warning("Error fetching slides for announcement %s: %s", pres_uuid, e)
                    continue
                        
            _LOGGER.info("Cached %d announcement slides from %d announcements in focused playlist '%s'", 
                        len(self._slides_cache), announcement_count, playlist_name)
            
        except Exception as e:
            _LOGGER.error("Error updating announcement slides cache: %s", e, exc_info=True)

    @property
    def options(self) -> list[str]:
        """Return list of available announcement slides in the order they were added."""
        if not self._slides_order:
            return ["No Announcement Slides Available"]
        return self._slides_order

    @property
    def current_option(self) -> str | None:
        """Return the currently focused announcement slide."""
        try:
            # Get the announcement slide index data from coordinator (which is the streaming coordinator)
            slide_index_data = self.coordinator.data.get("announcement_slide_index")
            if not slide_index_data:
                return None
            
            # Extract presentation UUID and slide index
            # Structure: {"announcement_index": {"index": 1, "presentation_id": {"uuid": "...", "name": "..."}}}
            announcement_index_info = slide_index_data.get("announcement_index", {})
            pres_info = announcement_index_info.get("presentation_id", {})
            pres_uuid = pres_info.get("uuid")
            slide_index = announcement_index_info.get("index")
            
            if pres_uuid is None or slide_index is None:
                return None
            
            # Look up the display name from our reverse cache
            lookup_key = (pres_uuid, slide_index)
            display_name = self._reverse_cache.get(lookup_key)
            
            # If slide not in cache (user added slides mid-presentation), refresh cache
            if display_name is None:
                _LOGGER.info("Announcement slide (uuid=%s, index=%s) not found in cache - triggering cache refresh", 
                           pres_uuid, slide_index)
                # Schedule cache update in background
                self.hass.async_create_task(self._update_slides_cache())
                return None
            
            return display_name
            
        except Exception as e:
            _LOGGER.debug("Error getting current announcement option: %s", e)
            return None

    async def async_select_option(self, option: str) -> None:
        """Trigger the selected announcement slide."""
        if option not in self._slides_cache:
            _LOGGER.error("Could not find announcement slide: %s", option)
            return
        
        presentation_uuid, slide_index = self._slides_cache[option]
        _LOGGER.info("Triggering announcement slide %s (presentation: %s, slide: %d)", 
                     option, presentation_uuid, slide_index)
        
        try:
            await self.api.trigger_slide(presentation_uuid, slide_index)
        except Exception as e:
            _LOGGER.error("Error triggering announcement slide: %s", e, exc_info=True)


class ProPresenterLookSelect(ProPresenterBaseEntity, SelectEntity):
    """Select entity for choosing ProPresenter looks."""

    _attr_translation_key = "look"
    _attr_name = "Look"

    def __init__(
        self,
        static_coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(streaming_coordinator, config_entry, static_coordinator=static_coordinator)
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
            
            _LOGGER.debug("Triggering look %s (UUID: %s)", option, look_uuid)
            
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

    _attr_icon = "mdi:script-text-outline"
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
                _LOGGER.debug("Macro '%s' (UUID: %s) triggered successfully", option, macro_uuid)
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

    _attr_icon = "mdi:video-input-hdmi"
    _attr_name = "Trigger Video Input"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(streaming_coordinator, config_entry, static_coordinator=coordinator)
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
                _LOGGER.info("Video input '%s' triggered successfully", option)
                
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
