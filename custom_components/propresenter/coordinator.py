"""DataUpdateCoordinator for ProPresenter integration."""

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ProPresenterAPI, ProPresenterConnectionError
from .const import CONF_PORT, DEFAULT_PORT, DOMAIN
from .utils import collect_playlist_uuids

_LOGGER = logging.getLogger(__name__)


class ProPresenterCoordinator(DataUpdateCoordinator):
    """ProPresenter coordinator - handles infrequently changing data via polling (firmware, name, etc)."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.config_entry = config_entry
        self.streaming_coordinator = None  # Set later by streaming coordinator
        self._last_known_version = None  # Track version to only update device info when it changes
        
        # Get configuration values
        host = config_entry.data[CONF_HOST]
        port = config_entry.data.get(CONF_PORT, DEFAULT_PORT)
        
        # Initialize API
        self.api = ProPresenterAPI(host, port)
        
        # Initialize DataUpdateCoordinator with longer interval for static data
        # Dynamic data will be handled by streaming
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({host}:{port})",
            update_method=self.async_update_data,
            update_interval=timedelta(seconds=30),  # Poll static data like version every 30 seconds
        )

    async def async_update_data(self) -> dict[str, Any]:
        """Fetch static/rarely-changing data from API.
        
        Poll ONLY truly static data here.
        Dynamic data (looks, props, playlists state, current_look, slide_index) 
        comes via streaming coordinator to avoid unnecessary API load.
        """
        try:
            # Version info - truly static (only changes on PP upgrade)
            version_info = await self.api.get_version()
            
            # Clear groups - rarely change (only when user adds/removes in PP)
            clear_groups = await self.api.get_clear_groups()
            
            # Macros - rarely change (only when user creates/deletes)
            macros = await self.api.get_macros()
            
            # Presentation playlist structure - cache on first fetch
            # Only re-fetch if not in cache (user can call refresh service)
            if not hasattr(self, '_cached_presentation_playlists'):
                presentation_playlists = await self.api.get_presentation_playlists()
                # Collect all playlist UUIDs (including nested ones)
                playlist_uuids = []
                collect_playlist_uuids(presentation_playlists, playlist_uuids)
                
                # Fetch details for all playlists ONCE
                presentation_playlist_details_list = []
                for playlist_uuid in playlist_uuids:
                    details = await self.api.get_presentation_playlist_details(playlist_uuid)
                    if details:
                        presentation_playlist_details_list.append(details)
                
                self._cached_presentation_playlists = presentation_playlists
                self._cached_presentation_playlist_details = presentation_playlist_details_list
            
            # Audio playlist structure - cache on first fetch
            if not hasattr(self, '_cached_audio_playlists'):
                audio_playlists = await self.api.get_audio_playlists()
                audio_playlist_details_list = []
                if audio_playlists and isinstance(audio_playlists, list):
                    for playlist in audio_playlists:
                        playlist_id = playlist.get("id", {})
                        playlist_uuid = playlist_id.get("uuid")
                        if playlist_uuid:
                            details = await self.api.get_audio_playlist_details(playlist_uuid)
                            if details:
                                audio_playlist_details_list.append(details)
                
                self._cached_audio_playlists = audio_playlists
                self._cached_audio_playlist_details = audio_playlist_details_list
            
            # Media playlist structure - cache on first fetch
            if not hasattr(self, '_cached_media_playlists'):
                media_playlists = await self.api.get_media_playlists()
                media_playlist_details_list = []
                if media_playlists and isinstance(media_playlists, list):
                    for playlist in media_playlists:
                        playlist_id = playlist.get("id", {})
                        playlist_uuid = playlist_id.get("uuid")
                        if playlist_uuid:
                            try:
                                details = await self.api.get_media_playlist_details(playlist_uuid)
                                if details:
                                    media_playlist_details_list.append(details)
                            except Exception as e:
                                _LOGGER.debug("Could not fetch media playlist details for %s: %s", playlist_uuid, e)
                
                self._cached_media_playlists = media_playlists
                self._cached_media_playlist_details = media_playlist_details_list
            
            # Fetch timers
            timers = await self.api.get_timers() or []
            
            # Fetch video inputs
            video_inputs = await self.api.get_video_inputs() or []
            
            data = {
                "version": version_info,
                "clear_groups": clear_groups,
                "macros": macros,
                "timers": timers,
                "video_inputs": video_inputs,
                # Return cached playlist data
                "presentation_playlists": self._cached_presentation_playlists,
                "presentation_playlist_details_list": self._cached_presentation_playlist_details,
                "audio_playlists": self._cached_audio_playlists,
                "audio_playlist_details_list": self._cached_audio_playlist_details,
                "media_playlists": self._cached_media_playlists,
                "media_playlist_details_list": self._cached_media_playlist_details,
            }
            # Cache the successful data
            self._data = data
            
            # Check if version has changed and update device registry if needed
            # This only calls async_update_device() if version actually changed
            await self.update_device_firmware_version()
            
            return data
        except ProPresenterConnectionError as err:
            raise UpdateFailed(f"Error communicating with ProPresenter: {err}") from err

    async def async_shutdown(self) -> None:
        """Close API connection on shutdown."""
        await self.api.close()

    async def update_device_firmware_version(self) -> None:
        """Update device registry with current firmware version.
        
        This only updates if the version has actually changed since last check.
        """
        if not self.data:
            return
        
        version_info = self.data.get("version", {})
        host_description = version_info.get("host_description", "")
        current_version = "Unknown"
        if host_description.startswith("ProPresenter "):
            current_version = host_description.replace("ProPresenter ", "")
        
        # Only update device registry if version has changed
        if current_version == self._last_known_version:
            return
        
        self._last_known_version = current_version
        
        try:
            device_registry = async_get_device_registry(self.hass)
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, self.config_entry.entry_id)}
            )
            
            if device:
                device_registry.async_update_device(
                    device.id,
                    sw_version=current_version
                )
        except Exception as err:
            _LOGGER.debug(f"Could not update device registry: {err}")

    def invalidate_playlist_cache(self) -> None:
        """Invalidate cached playlist data to force refresh on next poll."""
        if hasattr(self, '_cached_presentation_playlists'):
            delattr(self, '_cached_presentation_playlists')
        if hasattr(self, '_cached_presentation_playlist_details'):
            delattr(self, '_cached_presentation_playlist_details')
        if hasattr(self, '_cached_audio_playlists'):
            delattr(self, '_cached_audio_playlists')
        if hasattr(self, '_cached_audio_playlist_details'):
            delattr(self, '_cached_audio_playlist_details')
        if hasattr(self, '_cached_media_playlists'):
            delattr(self, '_cached_media_playlists')
        if hasattr(self, '_cached_media_playlist_details'):
            delattr(self, '_cached_media_playlist_details')


class ProPresenterStreamingCoordinator(DataUpdateCoordinator):
    """Streaming coordinator for frequently changing ProPresenter data."""

    def __init__(self, hass: HomeAssistant, api: ProPresenterAPI, static_coordinator: ProPresenterCoordinator = None) -> None:
        """Initialize streaming coordinator."""
        self.hass = hass
        self.api = api
        self.static_coordinator = static_coordinator
        self._stream_task = None
        self._poll_task = None
        self.connected = False  # Track connection state globally
        self._last_logged_error = None  # Track last error to avoid log spam
        self._error_count = 0  # Count consecutive errors
        
        # Set reference back to static coordinator
        if static_coordinator:
            static_coordinator.streaming_coordinator = self
        
        self._data = {
            "active_presentation": {},
            "stage_screens": [],
            "stage_layouts": [],
            "layout_map": [],
            "messages": [],
            "props": [],  # Props stream instead of poll
            "looks": [],  # Looks stream instead of poll
            "current_look": {},  # Current look streams
            "status_layers": {},
            "audience_screens_status": False,
            "stage_screens_status": False,
            "stage_message": "",
            "capture_status": {},  # Capture status streams
            "timers": [],  # Timer configurations stream
            "timers_current": [],  # Current timer states stream
            "audio_transport_state": {},  # Audio transport streams
            "audio_transport_time": 0.0,
            "presentation_transport_state": {},  # Media/video transport streams
            "presentation_transport_time": 0.0,
            "active_media_playlist": {},  # Active media playlist (polled separately)
            "video_input": {},  # Current video input streams
        }
        
        # Initialize DataUpdateCoordinator without update_interval (no polling)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_streaming",
            update_method=self.async_update_data,
        )

    async def async_update_data(self) -> dict[str, Any]:
        """Fetch initial data on first load, then return cached data from streaming updates."""
        # If data is still at initial state, fetch it once
        # Check if we haven't loaded messages yet (they should always be fetched initially)
        if not self._data.get("messages"):
            try:
                # Fetch all initial data in parallel for faster startup
                results = await asyncio.gather(
                    self.api.get_active_presentation(),
                    self.api.get_stage_screens(),
                    self.api.get_stage_layouts(),
                    self.api.get_stage_layout_map(),
                    self.api.get_messages(),
                    self.api.get_props(),
                    self.api.get_looks(),
                    self.api.get_current_look(),
                    self.api.get_status_layers(),
                    self.api.get_audience_screens_status(),
                    self.api.get_stage_screens_status(),
                    self.api.get_stage_message(),
                    self.api.get_audio_transport_state(),
                    self.api.get_presentation_transport_state(),
                    self.api.get_active_media_playlist(),
                    return_exceptions=True
                )
                
                # Unpack results (handle None values and exceptions)
                keys = [
                    "active_presentation", "stage_screens", "stage_layouts", "layout_map",
                    "messages", "props", "looks", "current_look", "status_layers",
                    "audience_screens_status", "stage_screens_status", "stage_message",
                    "audio_transport_state", "presentation_transport_state", "active_media_playlist"
                ]
                
                for i, key in enumerate(keys):
                    result = results[i]
                    if isinstance(result, Exception):
                        _LOGGER.warning("Failed to fetch %s during startup: %s", key, result)
                        self._data[key] = {} if key in ["active_presentation", "current_look", "audio_transport_state", "presentation_transport_state", "active_media_playlist", "stage_message"] else []
                    else:
                        self._data[key] = result or ({} if key in ["active_presentation", "current_look", "audio_transport_state", "presentation_transport_state", "active_media_playlist", "stage_message"] else [])
                
            except Exception as err:
                raise UpdateFailed(f"Error fetching initial data: {err}")
        
        return self._data

    async def _handle_status_update(self, path: str, data: Any) -> None:
        """Handle incoming status update from stream."""
        # Update data dictionary based on path (no logging for performance)
        if path == "presentation/current" or path == "presentation/active":
            self._data["active_presentation"] = data
        elif path == "presentation/slide_index":
            self._data["slide_index"] = data
        elif path == "announcement/slide_index":
            self._data["announcement_slide_index"] = data
        elif path == "stage/screens":
            self._data["stage_screens"] = data
        elif path == "stage/layouts":
            self._data["stage_layouts"] = data
        elif path == "stage/layout_map":
            self._data["layout_map"] = data
        elif path == "messages":
            self._data["messages"] = data
        elif path == "props":
            self._data["props"] = data
        elif path == "looks":
            self._data["looks"] = data
        elif path == "look/current":
            self._data["current_look"] = data
        elif path == "status/layers":
            self._data["status_layers"] = data
        elif path == "status/audience_screens":
            self._data["audience_screens_status"] = data
        elif path == "status/stage_screens":
            self._data["stage_screens_status"] = data
        elif path == "capture/status":
            self._data["capture_status"] = data
        elif path == "timers":
            self._data["timers"] = data
        elif path == "timers/current":
            self._data["timers_current"] = data
        elif path == "transport/audio/current":
            self._data["audio_transport_state"] = data
        elif path == "transport/audio/time":
            self._data["audio_transport_time"] = data
        elif path == "transport/presentation/current":
            self._data["presentation_transport_state"] = data
        elif path == "transport/presentation/time":
            self._data["presentation_transport_time"] = data
        elif path == "stage/message":
            self._data["stage_message"] = data
        
        # Notify listeners that data has changed
        self.async_set_updated_data(self._data)

    async def start_streaming(self) -> None:
        """Start the streaming connection."""
        if self._stream_task and not self._stream_task.done():
            return
        
        # Create background tasks that don't block HA startup
        # Using asyncio.create_task instead of hass.async_create_task
        # so HA doesn't wait for them during startup
        self._stream_task = asyncio.create_task(self._run_stream())
        
        # Start polling task for active media playlist
        self._poll_task = asyncio.create_task(self._poll_active_playlist())
    
    async def _poll_active_playlist(self) -> None:
        """Poll for active media playlist changes"""
        while True:
            try:
                await asyncio.sleep(2)  # Poll every 2 seconds
                active_media = await self.api.get_active_media_playlist() or {}
                
                # Only update if it changed
                if active_media != self._data.get("active_media_playlist"):
                    self._data["active_media_playlist"] = active_media
                    self.async_set_updated_data(self._data)
            except Exception:
                await asyncio.sleep(5)

    async def _run_stream(self) -> None:
        """Run the streaming connection (with auto-reconnect)."""
        reconnect_delay = 5  # Start with 5 second delay
        max_reconnect_delay = 30  # Max 30 seconds between attempts
        
        while True:
            try:
                # Reset delay on successful connection
                reconnect_delay = 5
                
                await self.api.stream_status_updates(
                    [
                        "presentation/current",
                        "presentation/slide_index",
                        "announcement/slide_index",
                        "stage/screens",
                        "stage/layouts",
                        "stage/layout_map",
                        "messages",
                        "props",  # Props stream (no polling)
                        "looks",  # Looks stream (no polling)
                        "look/current",  # Current look streams
                        "status/layers",
                        "status/audience_screens",
                        "status/stage_screens",
                        "capture/status",  # Capture status streams
                        "timers",  # Timer configurations stream
                        "timers/current",  # Timer states stream
                        "transport/audio/current",  # Audio transport state
                        "transport/audio/time",  # Audio transport time
                        "transport/presentation/current",  # Media/video transport state
                        "transport/presentation/time",  # Media/video transport time
                        "stage/message",
                    ],
                    self._handle_status_update
                )
                # If we get here, stream connected successfully
                self.connected = True
                self.last_update_success = True
                
                # When reconnecting, refresh the static coordinator to get fresh version info
                # (which will automatically update device registry if version changed)
                if self.static_coordinator:
                    try:
                        await self.static_coordinator.async_refresh()
                    except Exception as err:
                        _LOGGER.debug(f"Could not refresh static coordinator on reconnect: {err}")
                
                self.async_update_listeners()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                error_msg = str(err) if err else "Connection lost"
                
                # Rate limit error logging - only log if error message changed or error count reaches threshold
                should_log = False
                if error_msg != self._last_logged_error:
                    # New error type - always log it
                    should_log = True
                    self._error_count = 1
                    self._last_logged_error = error_msg
                elif self._error_count == 1:
                    # Log the first repeat of the same error
                    should_log = True
                    self._error_count += 1
                elif self._error_count % 10 == 0:
                    # Then log every 10th occurrence
                    should_log = True
                    self._error_count += 1
                else:
                    self._error_count += 1
                
                # Check if this might be an unsupported version issue (400 Bad Request on streaming)
                version_hint = ""
                if "400" in error_msg and self.static_coordinator:
                    try:
                        version_data = self.static_coordinator.data.get("version", {})
                        host_description = version_data.get("host_description", "")
                        if host_description:
                            version_hint = f" - Current version: {host_description}. If using v7.9 or below, the /v1/status/updates endpoint is not supported. Please upgrade to v7.9.1 or higher."
                    except Exception:
                        pass
                
                if should_log:
                    _LOGGER.warning(
                        "Stream disconnected: %s. Reconnecting in %d seconds...%s",
                        error_msg,
                        reconnect_delay,
                        version_hint
                    )
                
                # Mark entities as unavailable when disconnected
                self.connected = False
                self.last_update_success = False
                self.async_update_listeners()
                # Also mark static coordinator unavailable
                if self.static_coordinator:
                    self.static_coordinator.last_update_success = False
                    self.static_coordinator.async_update_listeners()
                
                await asyncio.sleep(reconnect_delay)
                
                # Exponential backoff for reconnection attempts
                reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)

    async def async_shutdown(self) -> None:
        """Stop the streaming connection."""
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
