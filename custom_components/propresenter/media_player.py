"""Media player platform for ProPresenter integration."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from .base import ProPresenterBaseEntity
from .coordinator import ProPresenterCoordinator, ProPresenterStreamingCoordinator
from .utils import get_nested_value

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ProPresenter media player entities."""
    coordinators = config_entry.runtime_data
    coordinator: ProPresenterCoordinator = coordinators["coordinator"]
    streaming_coordinator: ProPresenterStreamingCoordinator = coordinators["streaming_coordinator"]
    
    # Create media player entities with coordinators
    entities = [
        ProPresenterMediaPlayer(coordinator, streaming_coordinator, config_entry),
        ProPresenterVideoMediaPlayer(coordinator, streaming_coordinator, config_entry),
        ProPresenterPropMediaPlayer(coordinator, streaming_coordinator, config_entry),
    ]
    
    async_add_entities(entities)


class ProPresenterMediaPlayer(ProPresenterBaseEntity, MediaPlayerEntity):
    """Media player entity for ProPresenter audio control."""

    _attr_name = "Audio Player"
    _attr_icon = "mdi:music"
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.SEEK
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the media player."""
        super().__init__(coordinator, config_entry)
        self.streaming_coordinator = streaming_coordinator
        self._attr_unique_id = f"{config_entry.entry_id}_audio_player"
        self._position_updated_at: datetime | None = None
        self._last_selected_source = None  # Remember last selected audio track
        self._previous_active_source = None  # Track previous active track to detect PP changes
        
        # Subscribe to streaming coordinator updates
        self.async_on_remove(
            streaming_coordinator.async_add_listener(self._handle_streaming_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the main coordinator."""
        # Always track the current active audio track (so we can restore it after turn_off)
        current_active_source = self.source
        
        if current_active_source:
            self._last_selected_source = current_active_source
        
        self._previous_active_source = current_active_source
        super()._handle_coordinator_update()

    def _handle_streaming_coordinator_update(self) -> None:
        """Handle updated data from the streaming coordinator (fast audio transport updates)."""
        # Update the timestamp when streaming coordinator provides new data
        self._position_updated_at = dt_util.utcnow()
        
        # Check if an unknown audio track is playing and clear cache if needed
        audio_transport_state = self.streaming_coordinator.data.get("audio_transport_state", {})
        media_name = audio_transport_state.get("name")
        
        if media_name:
            # Check if this audio track exists in our cached audio list
            audio_playlist_details_list = self.coordinator.data.get("audio_playlist_details_list", [])
            track_found = False
            
            for playlist_details in audio_playlist_details_list:
                items = playlist_details.get("items", [])
                for item in items:
                    if item.get("type") == "audio":
                        track_name = get_nested_value(item, "id", "name", default="")
                        if track_name == media_name:
                            track_found = True
                            break
                if track_found:
                    break
            
            # If audio is playing but not in our cache, clear the cache to refresh
            if not track_found:
                self.coordinator.invalidate_playlist_cache()
                # Trigger a coordinator refresh to reload audio playlists
                self.hass.async_create_task(self.coordinator.async_request_refresh())
        
        # Only write state if entity is added to hass
        if self.hass is not None:
            self.async_write_ha_state()

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the player."""
        # Check audio transport state for actual playback status (from streaming coordinator)
        audio_transport_state = self.streaming_coordinator.data.get("audio_transport_state", {})
        
        # If there's no transport state data, return OFF (layer is cleared)
        if not audio_transport_state:
            return MediaPlayerState.OFF
        
        # Check if currently playing (field is "is_playing" not "isplaying")
        is_playing = audio_transport_state.get("is_playing", False)
        
        if is_playing:
            return MediaPlayerState.PLAYING
        
        # If not playing but has media loaded, return PAUSED
        has_media = audio_transport_state.get("name") or audio_transport_state.get("uuid")
        if has_media:
            return MediaPlayerState.PAUSED
        
        # No media loaded = OFF
        return MediaPlayerState.OFF

    @property
    def media_content_type(self) -> str:
        """Content type of current playing media."""
        return MediaType.MUSIC

    @property
    def media_title(self) -> str | None:
        """Title of current playing media."""
        # Get the current track name from transport state (from streaming coordinator)
        audio_transport_state = self.streaming_coordinator.data.get("audio_transport_state", {})
        
        # The field is "name" not "media_name"
        media_name = audio_transport_state.get("name")
        
        if media_name:
            # Remove file extension if present
            if "." in media_name:
                media_name = media_name.rsplit(".", 1)[0]
            return media_name
        
        return None

    @property
    def media_duration(self) -> int | None:
        """Duration of current playing media in seconds."""
        audio_transport_state = self.streaming_coordinator.data.get("audio_transport_state", {})
        duration = audio_transport_state.get("duration")
        
        if duration is not None:
            return int(duration)
        return None

    @property
    def media_position(self) -> int | None:
        """Position of current playing media in seconds."""
        audio_transport_time = self.streaming_coordinator.data.get("audio_transport_time")
        
        if audio_transport_time is not None:
            return int(audio_transport_time)
        return None

    @property
    def media_position_updated_at(self) -> datetime | None:
        """When was the position last updated."""
        return self._position_updated_at

    @property
    def source_list(self) -> list[str] | None:
        """List of available audio tracks from all playlists."""
        audio_playlist_details_list = self.coordinator.data.get("audio_playlist_details_list", [])
        
        if not audio_playlist_details_list:
            return None
        
        track_list = []
        
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
                    
                    track_list.append(display_name)
        
        return track_list if track_list else None

    @property
    def source(self) -> str | None:
        """Name of the current input source."""
        # ProPresenter API doesn't provide currently playing track info
        # So we return the focused playlist name
        audio_playlist_info = self.coordinator.data.get("audio_playlist")
        if audio_playlist_info:
            return audio_playlist_info.get("name", "Unknown")
        return None

    async def async_media_play(self) -> None:
        """Send play command."""
        await self.coordinator.api.audio_play()
        # Streaming will update state automatically

    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self.coordinator.api.audio_pause()
        # Streaming will update state automatically

    async def async_media_seek(self, position: float) -> None:
        """Seek to position in seconds."""
        await self.coordinator.api.audio_seek(position)

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self.coordinator.api.audio_next()
        # Streaming will update state automatically

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        await self.coordinator.api.audio_previous()
        # Streaming will update state automatically

    async def async_select_source(self, source: str) -> None:
        """Select audio track to play."""
        
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
                        if full_display_name == source:
                            playlist_uuid = current_playlist_uuid
                            track_uuid = get_nested_value(item, "id", "uuid")
                            found = True
                            break
                    else:
                        if display_track_name == source or track_name == source:
                            playlist_uuid = current_playlist_uuid
                            track_uuid = get_nested_value(item, "id", "uuid")
                            found = True
                            break
            
            if found:
                break
        
        if not playlist_uuid or not track_uuid:
            _LOGGER.error(f"Could not find track: {source}")
            return
        
        await self.coordinator.api.trigger_audio_track(playlist_uuid, track_uuid)
    
    async def async_turn_on(self) -> None:
        """Turn on - resume if paused."""
        # If already playing, do nothing
        if self.state == MediaPlayerState.PLAYING:
            return
        
        # If paused, just resume
        if self.state == MediaPlayerState.PAUSED:
            await self.async_media_play()
    
    async def async_turn_off(self) -> None:
        """Turn off - stop and clear audio."""
        # Save the current active source for tracking purposes
        current_source = self.source
        if current_source:
            self._last_selected_source = current_source
        
        # Pause and clear
        await self.async_media_pause()
        await self.coordinator.api.trigger_clear_layer("audio")


class ProPresenterVideoMediaPlayer(ProPresenterBaseEntity, MediaPlayerEntity):
    """Media player entity for ProPresenter video/media control."""

    _attr_name = "Media Player"
    _attr_icon = "mdi:image-area"

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the media player."""
        super().__init__(coordinator, config_entry)
        self.streaming_coordinator = streaming_coordinator
        self._attr_unique_id = f"{config_entry.entry_id}_video_player"
        self._position_updated_at: datetime | None = None
        self._cached_thumbnail: bytes | None = None
        self._cached_thumbnail_uuid: str | None = None
        self._last_selected_source = None  # Remember last selected media
        self._previous_active_source = None  # Track previous active media to detect PP changes
        self._media_action_slide_info: tuple[str | None, int | None] = (None, None)  # Remember originating slide for Media Actions
        self._previous_media_layer_state: bool | None = None  # Track if media layer was active in previous update (None = first run)
        
        # Subscribe to streaming coordinator updates
        self.async_on_remove(
            streaming_coordinator.async_add_listener(self._handle_streaming_coordinator_update)
        )

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        # Get current media type
        active_media = self.streaming_coordinator.data.get("active_media_playlist", {})
        item = active_media.get("item") if active_media else None
        media_type = item.get("type", "video") if item else "video"
        
        # Base features for all media
        features = (
            MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
        )
        
        # Add playback controls only for video (not for images)
        if media_type == "video":
            features |= (
                MediaPlayerEntityFeature.PLAY
                | MediaPlayerEntityFeature.PAUSE
                | MediaPlayerEntityFeature.SEEK
            )
        
        return features

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the main coordinator."""
        # Always track the current active media (so we can restore it after turn_off)
        current_active_source = self.source
        
        if current_active_source:
            # Save whatever is currently playing/loaded
            self._last_selected_source = current_active_source
        
        self._previous_active_source = current_active_source
        super()._handle_coordinator_update()

    def _handle_streaming_coordinator_update(self) -> None:
        """Handle updated data from the streaming coordinator (streaming updates)."""
        # Track Media Action originating slide
        status_layers = self.streaming_coordinator.data.get("status_layers", {})
        media_layer_active = status_layers.get("media", False)
        active_media = self.streaming_coordinator.data.get("active_media_playlist", {})
        item = active_media.get("item") if active_media else None
        
        is_media_action_active = media_layer_active and not item
        
        # If media layer is active but no playlist item, it's a Media Action
        if is_media_action_active:
            # Only capture slide info when we see a TRUE TRANSITION:
            # - Previous state must be explicitly False (not None for first run)
            # - Current state is True
            if self._previous_media_layer_state is False:
                current_slide_info = self._get_current_slide_info()
                self._media_action_slide_info = current_slide_info
        else:
            # Media stopped or switched to playlist media - clear the saved slide info
            if self._media_action_slide_info != (None, None):
                self._media_action_slide_info = (None, None)
        
        # Remember current media layer state for next update
        self._previous_media_layer_state = is_media_action_active
        
        # Update the timestamp when streaming coordinator provides new data
        self._position_updated_at = dt_util.utcnow()
        
        # Only write state if entity is added to hass
        if self.hass is not None:
            self.async_write_ha_state()


    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the player."""
        # Check presentation transport state for actual playback status
        transport_state = self.streaming_coordinator.data.get("presentation_transport_state", {})
        
        # If there's no transport state data, return OFF (layer is cleared)
        if not transport_state:
            return MediaPlayerState.OFF
        
        # Check if currently playing
        is_playing = transport_state.get("is_playing", False)
        
        if is_playing:
            return MediaPlayerState.PLAYING
        
        # If not playing but has media loaded, return PAUSED
        has_media = transport_state.get("name") or transport_state.get("uuid")
        if has_media:
            return MediaPlayerState.PAUSED
        
        # No media loaded = OFF
        return MediaPlayerState.OFF

    @property
    def media_title(self) -> str | None:
        """Return the title of current playing media."""
        transport_state = self.streaming_coordinator.data.get("presentation_transport_state", {})
        name = transport_state.get("name", "")
        # Keep the full filename with extension for display
        return name if name else None

    @property
    def media_duration(self) -> int | None:
        """Return the duration of current playing media in seconds."""
        transport_state = self.streaming_coordinator.data.get("presentation_transport_state", {})
        duration = transport_state.get("duration")
        return int(duration) if duration else None

    @property
    def media_position(self) -> int | None:
        """Return the current playback position in seconds."""
        transport_time = self.streaming_coordinator.data.get("presentation_transport_time")
        return int(transport_time) if transport_time is not None else None

    @property
    def media_position_updated_at(self) -> datetime | None:
        """Return when the playback position was last updated."""
        return self._position_updated_at

    @property
    def media_content_type(self) -> str:
        """Return the content type of current playing media."""
        # Check if the current media is an image or video
        active_media = self.streaming_coordinator.data.get("active_media_playlist", {})
        item = active_media.get("item") if active_media else None
        media_type = item.get("type", "video") if item else "video"
        
        if media_type == "image":
            return MediaType.IMAGE
        return MediaType.VIDEO

    def _get_current_slide_info(self) -> tuple[str | None, int | None]:
        """Get current presentation UUID and slide index from coordinator data.
        
        Returns:
            Tuple of (presentation_uuid, slide_index) or (None, None) if not available.
        """
        slide_index_data = self.streaming_coordinator.data.get("slide_index")
        if not slide_index_data:
            return None, None
        
        pres_index = slide_index_data.get("presentation_index")
        if not pres_index:
            return None, None
        
        pres_id = pres_index.get("presentation_id", {})
        pres_uuid = pres_id.get("uuid")
        slide_index = pres_index.get("index")
        return pres_uuid, slide_index

    @property
    def media_image_hash(self) -> str | None:
        """Hash value for media image."""
        # Only return hash if we have an active media item (not idle or off)
        if self.state in (MediaPlayerState.IDLE, MediaPlayerState.OFF):
            return None
        
        # Return the UUID as the hash - this tells HA when the image has changed
        active_media = self.streaming_coordinator.data.get("active_media_playlist", {})
        item = active_media.get("item") if active_media else None
        
        if item:
            # Media from playlist - use media UUID
            return item.get("uuid")
        
        # Check if media is playing from a Media Action (slide tab)
        status_layers = self.streaming_coordinator.data.get("status_layers", {})
        media_layer_active = status_layers.get("media", False)
        
        if media_layer_active:
            # Media from Media Action - use saved originating slide info
            pres_uuid, slide_index = self._media_action_slide_info
            
            if pres_uuid is not None and slide_index is not None:
                return f"{pres_uuid}_{slide_index}"
        
        return None

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        transport_state = self.streaming_coordinator.data.get("presentation_transport_state", {})
        
        if not transport_state:
            return None
        
        name = transport_state.get("name", "")
        # Keep the full filename with extension
        return name if name else None

    @property
    def source_list(self) -> list[str]:
        """Return the list of available media sources."""
        media_playlist_details_list = self.coordinator.data.get("media_playlist_details_list", [])
        
        if not media_playlist_details_list:
            return []
        
        sources = []
        
        for playlist_details in media_playlist_details_list:
            if not playlist_details:
                continue
            
            playlist_id = playlist_details.get("id")
            if not playlist_id:
                continue
            
            playlist_name = playlist_id.get("name", "Unknown Playlist")
            items = playlist_details.get("items", [])
            
            for item in items:
                if not item:
                    continue
                
                # Include both video and image types
                if item.get("type") in ["video", "image"]:
                    item_id = item.get("id")
                    if not item_id:
                        continue
                    
                    item_name = item_id.get("name", "")
                    if not item_name:
                        continue
                    
                    # If we have multiple playlists, prefix with playlist name
                    if len(media_playlist_details_list) > 1:
                        display_name = f"{playlist_name} - {item_name}"
                    else:
                        display_name = item_name
                    
                    sources.append(display_name)
        
        return sources

    async def async_media_play(self) -> None:
        """Send play command."""
        await self.coordinator.api.presentation_play()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self.coordinator.api.presentation_pause()

    async def async_media_seek(self, position: float) -> None:
        """Send seek command."""
        await self.coordinator.api.presentation_seek(position)

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Fetch media image of current playing media."""
        try:
            # Get the current media item UUID from the active playlist
            active_media = self.streaming_coordinator.data.get("active_media_playlist", {})
            item = active_media.get("item") if active_media else None
            media_uuid = item.get("uuid") if item else None
            
            # Check if media is playing from a Media Action (media layer active but no playlist)
            status_layers = self.streaming_coordinator.data.get("status_layers", {})
            media_layer_active = status_layers.get("media", False)
            
            if media_layer_active and not media_uuid:
                # Media is playing from a Media Action (slide tab), not from media playlist
                # Use the saved originating slide info (not current slide)
                _LOGGER.debug("Media playing from Media Action - using saved originating slide thumbnail")
                
                pres_uuid, slide_index = self._media_action_slide_info
                
                if pres_uuid is not None and slide_index is not None:
                    cache_key = f"{pres_uuid}_{slide_index}"
                    
                    # Check cache
                    if cache_key == self._cached_thumbnail_uuid and self._cached_thumbnail:
                        return self._cached_thumbnail, "image/jpeg"
                    
                    # Fetch slide thumbnail
                    thumbnail_data = await self.coordinator.api.get_presentation_thumbnail(
                        pres_uuid, slide_index, quality=400
                    )
                    
                    if thumbnail_data:
                        self._cached_thumbnail = thumbnail_data
                        self._cached_thumbnail_uuid = cache_key
                        return thumbnail_data, "image/jpeg"
                
                return None, None
            
            if not media_uuid:
                return None, None
            
            # Check if we already have this thumbnail cached
            if media_uuid == self._cached_thumbnail_uuid and self._cached_thumbnail:
                return self._cached_thumbnail, "image/jpeg"
            
            # Fetch new thumbnail
            thumbnail_data = await self.coordinator.api.get_media_thumbnail(media_uuid, quality=400)
            
            if thumbnail_data:
                self._cached_thumbnail = thumbnail_data
                self._cached_thumbnail_uuid = media_uuid
                return thumbnail_data, "image/jpeg"
            else:
                _LOGGER.warning(f"No thumbnail data received for UUID: {media_uuid}")
            
            return None, None
        except Exception as err:
            _LOGGER.error(f"Error fetching media thumbnail: {err}", exc_info=True)
            return None, None

    async def async_select_source(self, source: str) -> None:
        """Select media source to play."""
        media_playlist_details_list = self.coordinator.data.get("media_playlist_details_list", [])
        
        if not media_playlist_details_list:
            _LOGGER.error("No media playlist data available")
            return
        
        # Search through all playlists to find the item
        playlist_uuid = None
        item_uuid = None
        found = False
        
        for playlist_details in media_playlist_details_list:
            if not playlist_details:
                continue
            
            playlist_id = playlist_details.get("id")
            if not playlist_id:
                continue
            
            current_playlist_uuid = playlist_id.get("uuid")
            playlist_name = playlist_id.get("name", "Unknown Playlist")
            items = playlist_details.get("items", [])
            
            for item in items:
                if not item:
                    continue
                
                # Support both video and image types
                if item.get("type") in ["video", "image"]:
                    item_id = item.get("id")
                    if not item_id:
                        continue
                    
                    item_name = item_id.get("name", "")
                    item_item_uuid = item_id.get("uuid")
                    
                    if not item_name or not item_item_uuid:
                        continue
                    
                    # Check if this is the selected item
                    # Handle both "Playlist - Item" and "Item" formats
                    if len(media_playlist_details_list) > 1:
                        full_display_name = f"{playlist_name} - {item_name}"
                        if full_display_name == source:
                            playlist_uuid = current_playlist_uuid
                            item_uuid = item_item_uuid
                            found = True
                            break
                    else:
                        if item_name == source:
                            playlist_uuid = current_playlist_uuid
                            item_uuid = item_item_uuid
                            found = True
                            break
            
            if found:
                break
        
        if not playlist_uuid or not item_uuid:
            _LOGGER.error(f"Could not find media item: {source}")
            return
        
        await self.coordinator.api.trigger_media_item(playlist_uuid, item_uuid)
    
    async def async_turn_on(self) -> None:
        """Turn on - resume if paused."""
        # If already playing, do nothing
        if self.state == MediaPlayerState.PLAYING:
            return
        
        # If paused, just resume
        if self.state == MediaPlayerState.PAUSED:
            await self.async_media_play()
    
    async def async_turn_off(self) -> None:
        """Turn off - stop and clear media."""
        # Save the current active source for tracking purposes
        current_source = self.source
        if current_source:
            self._last_selected_source = current_source
        
        # Clear the media layer
        await self.coordinator.api.trigger_clear_layer("media")


class ProPresenterPropMediaPlayer(ProPresenterBaseEntity, MediaPlayerEntity):
    """Media player entity for ProPresenter props control."""

    _attr_name = "Props"
    _attr_icon = "mdi:layers-triple"
    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the props media player."""
        super().__init__(streaming_coordinator, config_entry, static_coordinator=coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}_prop_player"
        self._prop_uuid_map = {}  # Map display names to UUIDs
        self._last_selected_prop = None  # Remember last selected prop for turn_on
        self._previous_active_prop = None  # Track previous active prop to detect PP changes
    
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Always track the current active prop (so we can restore it after turn_off)
        current_active_prop = self.source
        
        if current_active_prop:
            # Save whatever is currently active
            self._last_selected_prop = current_active_prop
        
        self._previous_active_prop = current_active_prop
        super()._handle_coordinator_update()
        
    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the player."""
        props = self.coordinator.data.get("props", [])
        
        # Check if any prop is active
        for prop in props:
            if prop.get("is_active", False):
                return MediaPlayerState.ON
        
        return MediaPlayerState.OFF
    
    @property
    def source_list(self) -> list[str]:
        """Return list of available props."""
        props = self.coordinator.data.get("props", [])
        prop_names = []
        self._prop_uuid_map = {}  # Reset map
        
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
        
        return prop_names if prop_names else []
    
    @property
    def source(self) -> str | None:
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
            return None
        
        # Find the display name for this UUID in our map
        for display_name, uuid in self._prop_uuid_map.items():
            if uuid == active_uuid:
                return display_name
        
        return None
    
    @property
    def media_image_url(self) -> str | None:
        """Return the image URL of the current prop."""
        props = self.coordinator.data.get("props", [])
        
        # Find the active prop
        for prop in props:
            if prop.get("is_active", False):
                prop_data = prop.get("id", {})
                if isinstance(prop_data, dict):
                    prop_uuid = prop_data.get("uuid")
                    if prop_uuid:
                        # Return the thumbnail URL
                        # Use the static coordinator to access API
                        api = self.static_coordinator.api
                        return f"http://{api.host}:{api.port}/v1/prop/{prop_uuid}/thumbnail"
        
        return None
    
    @property
    def media_title(self) -> str | None:
        """Return the title of current prop."""
        return self.source
    
    @property
    def media_content_type(self) -> str:
        """Return the content type of current prop."""
        return MediaType.IMAGE  # Props can be images, videos, or text
    
    async def async_turn_on(self) -> None:
        """Turn on - does nothing."""
        pass
    
    async def async_turn_off(self) -> None:
        """Turn off - clear all props."""
        # Save the current active prop for tracking purposes
        current_prop = self.source
        if current_prop:
            self._last_selected_prop = current_prop
        
        await self.static_coordinator.api.trigger_clear_layer("props")
    
    async def async_select_source(self, source: str) -> None:
        """Select and trigger a prop."""
        # Look up the UUID from our map
        prop_uuid = self._prop_uuid_map.get(source)
        
        if not prop_uuid:
            _LOGGER.error("Could not find prop UUID for: %s", source)
            return
        
        _LOGGER.debug("Triggering prop %s (UUID: %s)", source, prop_uuid)
        await self.static_coordinator.api.trigger_prop(prop_uuid)
