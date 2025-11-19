"""ProPresenter API Client."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)


class ProPresenterAPIError(Exception):
    """Base exception for ProPresenter API errors."""


class ProPresenterConnectionError(ProPresenterAPIError):
    """Exception for connection errors."""


class ProPresenterAuthError(ProPresenterAPIError):
    """Exception for authentication errors."""


class ProPresenterAPI:
    """ProPresenter API client."""

    def __init__(self, host: str, port: int = 50001) -> None:
        """Initialize the ProPresenter API client.

        Args:
            host: The IP address or hostname of the ProPresenter instance
            port: The API port (default: 50001)
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with appropriate timeout settings."""
        if self._session is None or self._session.closed:
            # Configure timeout for long-lived streaming connections
            # Total timeout is disabled (None) to allow indefinite streaming
            # Sock_read timeout is high to allow for slow/infrequent updates
            timeout = aiohttp.ClientTimeout(
                total=None,  # No total timeout - allow indefinite streaming
                connect=10,  # 10 second connection timeout
                sock_read=300,  # 5 minutes between reads (generous for streaming)
            )
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def stream_status_updates(self, endpoints: list[str], callback):
        """Stream status updates from ProPresenter.

        This creates a persistent connection to /v1/status/updates and calls
        the callback function whenever updates are received.

        Args:
            endpoints: List of endpoints to monitor (e.g., ['transport/audio/current', 'transport/audio/time'])
            callback: Async function to call with update data (path, data)
        """
        url = f"{self.base_url}/v1/status/updates"
        session = await self._get_session()

        _LOGGER.info(f"Starting status update stream for endpoints: {endpoints}")

        try:
            # Use a longer timeout specifically for the streaming POST request
            # This overrides the session timeout for this particular request
            timeout = aiohttp.ClientTimeout(
                total=None,  # No total timeout for streaming
                sock_read=600,  # 10 minutes between reads (very generous)
            )

            async with session.post(
                url,
                json=endpoints,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            ) as response:
                response.raise_for_status()
                _LOGGER.info("Stream connection established, reading updates...")

                # Read the chunked response line by line
                async for line in response.content:
                    if line:
                        try:
                            # Each line is a JSON object with the update
                            import json

                            decoded_line = line.decode("utf-8").strip()
                            if decoded_line:
                                # No logging here - runs every second for timer updates
                                data = json.loads(decoded_line)
                                # Data format: {"url": "path", "data": {...}}
                                path = data.get("url")
                                update_data = data.get("data")
                                await callback(path, update_data)
                        except json.JSONDecodeError as err:
                            # Log at debug level - these are typically benign stream formatting lines
                            _LOGGER.debug(
                                f"Could not decode line: {line[:100]} - Error: {err}"
                            )
                        except Exception as err:
                            _LOGGER.error(
                                f"Error processing update: {err}", exc_info=True
                            )

        except aiohttp.ClientConnectorError as err:
            raise ProPresenterConnectionError(
                f"Cannot connect to ProPresenter at {self.host}:{self.port}"
            ) from err
        except aiohttp.ClientError as err:
            raise ProPresenterConnectionError(
                f"Error communicating with ProPresenter: {err}"
            ) from err

    async def _request(
        self, method: str, endpoint: str, json_data: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Make an API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            json_data: Optional JSON data for POST/PUT requests

        Returns:
            Response data as dictionary or None

        Raises:
            ProPresenterConnectionError: If connection fails
        """
        url = f"{self.base_url}{endpoint}"
        session = await self._get_session()

        try:
            async with async_timeout.timeout(10):
                async with session.request(method, url, json=json_data) as response:
                    if response.status == 404:
                        _LOGGER.debug("Endpoint not found: %s", endpoint)
                        return None

                    response.raise_for_status()

                    # Some endpoints return empty responses
                    if response.content_length == 0:
                        return None

                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        return await response.json()
                    return None

        except aiohttp.ClientConnectorError as err:
            raise ProPresenterConnectionError(
                f"Cannot connect to ProPresenter at {self.host}:{self.port}"
            ) from err
        except aiohttp.ClientError as err:
            raise ProPresenterConnectionError(
                f"Error communicating with ProPresenter: {err}"
            ) from err
        except TimeoutError as err:
            raise ProPresenterConnectionError(
                f"Timeout connecting to ProPresenter at {self.host}:{self.port}"
            ) from err

    async def get_version(self) -> dict[str, Any]:
        """Get ProPresenter version information.

        Returns:
            Version information dictionary

        Raises:
            ProPresenterConnectionError: If connection fails
        """
        data = await self._request("GET", "/version")
        if data is None:
            raise ProPresenterConnectionError("Failed to get version information")
        return data

    async def get_active_presentation(self) -> dict[str, Any] | None:
        """Get the currently active presentation.

        Returns:
            Active presentation information or None if no presentation is active
        """
        return await self._request("GET", "/v1/presentation/active")

    async def trigger_next(self) -> None:
        """Trigger the next slide/cue in the active presentation or playlist."""
        await self._request("GET", "/v1/trigger/next")

    async def trigger_previous(self) -> None:
        """Trigger the previous slide/cue in the active presentation or playlist."""
        await self._request("GET", "/v1/trigger/previous")

    async def find_my_mouse(self) -> None:
        """Execute the Find My Mouse operation to locate the cursor on screen."""
        await self._request("GET", "/v1/find_my_mouse")

    async def get_stage_screens(self) -> list[dict[str, Any]]:
        """Get list of all configured stage screens.

        Returns:
            List of stage screen configurations
        """
        data = await self._request("GET", "/v1/stage/screens")
        return data if data else []

    async def get_stage_layouts(self) -> list[dict[str, Any]]:
        """Get list of all configured stage layouts.

        Returns:
            List of stage layout configurations
        """
        data = await self._request("GET", "/v1/stage/layouts")
        return data if data else []

    async def get_stage_layout_map(self) -> dict[str, Any]:
        """Get current stage layout mapping (which layout is active on each screen).

        Returns:
            Dictionary mapping screen IDs to layout IDs
        """
        data = await self._request("GET", "/v1/stage/layout_map")
        return data if data else {}

    async def set_stage_screen_layout(self, screen_id: str, layout_id: str) -> None:
        """Set the stage layout for a specific screen.

        Args:
            screen_id: The ID of the stage screen
            layout_id: The ID of the layout to apply
        """
        endpoint = f"/v1/stage/screen/{screen_id}/layout/{layout_id}"
        await self._request("GET", endpoint)

    async def get_video_inputs(self) -> list[dict[str, Any]]:
        """Get list of all video inputs.

        Returns:
            List of video input configurations
        """
        data = await self._request("GET", "/v1/video_inputs")
        return data or []

    async def trigger_video_input(self, video_input_id: str) -> None:
        """Trigger a video input to display.

        Args:
            video_input_id: The UUID of the video input to trigger
        """
        endpoint = f"/v1/video_inputs/{video_input_id}/trigger"
        await self._request("GET", endpoint)

    async def get_messages(self) -> list[dict[str, Any]]:
        """Get list of all configured messages.

        Returns:
            List of message configurations
        """
        data = await self._request("GET", "/v1/messages")
        return data if data else []

    async def show_message(
        self, message_id: str, tokens: dict[str, str] | None = None
    ) -> None:
        """Show/trigger a message.

        Args:
            message_id: The UUID of the message to show
            tokens: Optional dictionary of token names to values for dynamic content.
                   Note: Duplicate token names are not supported due to ProPresenter API limitations.
                   If None, will fetch and use the stored token values from the message configuration
        """
        endpoint = f"/v1/message/{message_id}/trigger"

        # Fetch the message to get current token values
        message_data = await self._request("GET", f"/v1/message/{message_id}")
        if not message_data:
            _LOGGER.error(f"Failed to retrieve message {message_id}")
            await self._request("POST", endpoint, json_data=[])
            return

        _LOGGER.info(f"Retrieved message data for {message_id}: {message_data}")

        # Build token list with name and text (NO UUID needed!)
        # Format: [{"name": "token_name", "text": {"text": "value"}}]
        token_list = []
        for token in message_data.get("tokens", []):
            token_name = token.get("name")

            # Use provided token value if available, otherwise use stored value
            if tokens and token_name in tokens:
                token_value = tokens[token_name]
            else:
                # Use the stored value
                token_text = token.get("text", {})
                token_value = (
                    token_text.get("text", "") if isinstance(token_text, dict) else ""
                )

            if token_name:
                token_list.append({"name": token_name, "text": {"text": token_value}})

        _LOGGER.info(f"Triggering message with tokens: {token_list}")
        await self._request("POST", endpoint, json_data=token_list)

    async def hide_message(self, message_id: str) -> None:
        """Hide/clear a message.

        Args:
            message_id: The UUID of the message to hide
        """
        endpoint = f"/v1/message/{message_id}/clear"
        await self._request("GET", endpoint)

    async def update_message(
        self, message_id: str, message_data: dict[str, Any]
    ) -> None:
        """Update a message's properties.

        Args:
            message_id: The UUID of the message to update
            message_data: Dictionary with message properties (text, tokens, visible_on_network, etc.)
        """
        endpoint = f"/v1/message/{message_id}"
        await self._request("PUT", endpoint, json_data=message_data)

    async def update_message_token(
        self, message_id: str, token_index: int, token_value: str
    ) -> None:
        """Update the text value of a specific token in a message.

        LIMITATION: ProPresenter's API has a bug where PUT /v1/message/{id} does not
        actually persist token text changes. The only way to update token values is via
        POST /v1/message/{id}/trigger, which shows the message. This means updating a
        token value will briefly display the message.

        Additionally, when a message has duplicate token names (e.g., two tokens named
        "Message"), the trigger endpoint may update all tokens with that name instead of
        just the target token, causing unexpected behavior.

        RECOMMENDATION: Use only one token per unique name in ProPresenter messages.

        Args:
            message_id: The UUID of the message
            token_index: The index of the token to update (0-based)
            token_value: The new text value for the token
        """
        # Get the current message data
        endpoint = f"/v1/message/{message_id}"
        message_data = await self._request("GET", endpoint)

        if not message_data:
            _LOGGER.error(f"Failed to retrieve message {message_id}")
            return

        # Validate token index
        tokens = message_data.get("tokens", [])
        if token_index < 0 or token_index >= len(tokens):
            _LOGGER.error(
                f"Token index {token_index} out of range for message {message_id} (has {len(tokens)} tokens)"
            )
            return

        # Build token payload for trigger - include all tokens with their current values
        token_payload = []
        for i, token in enumerate(tokens):
            if i == token_index:
                # Use the new value for the target token
                token_payload.append(
                    {"name": token["name"], "text": {"text": token_value}}
                )
            else:
                # Keep existing values for other tokens
                token_payload.append(
                    {
                        "name": token["name"],
                        "text": {"text": token.get("text", {}).get("text", "")},
                    }
                )

        # Trigger to persist the values
        # This will show the message briefly (API limitation - no way to update without showing)
        trigger_endpoint = f"/v1/message/{message_id}/trigger"
        await self._request("POST", trigger_endpoint, json_data=token_payload)

    async def get_clear_groups(self) -> list[dict[str, Any]]:
        """Get list of all configured clear groups.

        Returns:
            List of clear group configurations with their layers
        """
        data = await self._request("GET", "/v1/clear/groups")
        return data if data else []

    async def get_props(self) -> list[dict[str, Any]]:
        """Get list of all configured props.

        Returns:
            List of prop configurations with their active status
        """
        data = await self._request("GET", "/v1/props")
        return data if data else []

    async def trigger_prop(self, prop_id: str) -> None:
        """Trigger/show a specific prop.

        Args:
            prop_id: The UUID of the prop to trigger
        """
        endpoint = f"/v1/prop/{prop_id}/trigger"
        await self._request("GET", endpoint)

    async def clear_prop(self, prop_id: str) -> None:
        """Clear a specific prop.

        Args:
            prop_id: The UUID of the prop to clear
        """
        endpoint = f"/v1/prop/{prop_id}/clear"
        await self._request("GET", endpoint)

    async def get_audio_playlist(self) -> dict[str, Any] | None:
        """Get the currently focused audio playlist.

        Returns:
            Audio playlist information or None
        """
        data = await self._request("GET", "/v1/audio/playlist/focused")
        return data

    async def get_audio_playlists(self) -> list[dict[str, Any]] | None:
        """Get all audio playlists.

        Returns:
            List of all audio playlists or None
        """
        data = await self._request("GET", "/v1/audio/playlists")
        return data

    async def get_audio_playlist_details(
        self, playlist_uuid: str
    ) -> dict[str, Any] | None:
        """Get detailed information about an audio playlist including all tracks.

        Args:
            playlist_uuid: The UUID of the playlist

        Returns:
            Playlist details with items/tracks
        """
        data = await self._request("GET", f"/v1/audio/playlist/{playlist_uuid}")
        return data

    async def trigger_audio_track(self, playlist_uuid: str, track_uuid: str) -> None:
        """Trigger/play a specific audio track.

        Args:
            playlist_uuid: The UUID of the playlist
            track_uuid: The UUID of the track to play
        """
        endpoint = f"/v1/trigger/audio/{playlist_uuid}/{track_uuid}"
        await self._request("GET", endpoint)

    # Media (video) playlist methods
    async def get_media_playlists(self) -> list[dict[str, Any]] | None:
        """Get all media playlists.

        Returns:
            List of all media playlists or None
        """
        data = await self._request("GET", "/v1/media/playlists")
        return data

    async def get_media_playlist_details(
        self, playlist_uuid: str
    ) -> dict[str, Any] | None:
        """Get detailed information about a media playlist including all items.

        Args:
            playlist_uuid: The UUID of the playlist

        Returns:
            Playlist details with items
        """
        data = await self._request("GET", f"/v1/media/playlist/{playlist_uuid}")
        return data

    async def get_active_media_playlist(self) -> dict[str, Any] | None:
        """Get the active media playlist and item.

        Returns:
            Dictionary with 'playlist' and 'item' keys or None
        """
        data = await self._request("GET", "/v1/media/playlist/active")
        return data

    async def trigger_media_item(self, playlist_uuid: str, item_uuid: str) -> None:
        """Trigger/play a specific media item.

        Args:
            playlist_uuid: The UUID of the playlist
            item_uuid: The UUID of the item to play
        """
        endpoint = f"/v1/trigger/media/{playlist_uuid}/{item_uuid}"
        await self._request("GET", endpoint)

    # Presentation playlist methods
    async def get_presentation_playlists(self) -> list[dict[str, Any]] | None:
        """Get all presentation playlists.

        Returns:
            List of all presentation playlists or None
        """
        data = await self._request("GET", "/v1/playlists")
        return data

    async def get_presentation_playlist_details(
        self, playlist_uuid: str
    ) -> dict[str, Any] | None:
        """Get detailed information about a presentation playlist including all items.

        Args:
            playlist_uuid: The UUID of the playlist

        Returns:
            Playlist details with items (presentations)
        """
        data = await self._request("GET", f"/v1/playlist/{playlist_uuid}")
        return data

    async def get_focused_playlist(self) -> dict[str, Any] | None:
        """Get the currently focused presentation playlist.

        Returns:
            Focused playlist details with items or None
        """
        data = await self._request("GET", "/v1/playlist/focused")
        return data

    async def get_media_thumbnail(
        self, media_uuid: str, quality: int = 400
    ) -> bytes | None:
        """Get thumbnail image for a media item.

        Args:
            media_uuid: The UUID of the media item (from playlist, not transport)
            quality: The desired quality (pixels in largest dimension), default 400

        Returns:
            JPEG image data as bytes or None if not available
        """
        endpoint = f"/v1/media/{media_uuid}/thumbnail"
        params = {"quality": quality}

        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}{endpoint}", params=params
            ) as response:
                if response.status == 200:
                    data = await response.read()
                    return data
                else:
                    _LOGGER.warning(
                        f"Thumbnail request failed with status {response.status}"
                    )
                    return None
        except Exception as err:
            _LOGGER.error(f"Error fetching thumbnail: {err}", exc_info=True)
            return None

    # Presentation transport methods (used for media layer control)
    async def get_presentation_transport_state(self) -> dict:
        """Get the current presentation transport state (playback status for media layer).

        Returns:
            Dictionary with transport state including:
            - is_playing (bool): Whether media is currently playing
            - name (str): Current media filename
            - duration (float): Media duration in seconds
            - uuid (str): Media UUID
            - audio_only (bool): Whether this is audio only
        """
        data = await self._request("GET", "/v1/transport/presentation/current")
        return data if data else {}

    async def get_presentation_transport_time(self) -> float:
        """Get the current presentation playback position in seconds.

        Returns:
            Current playback position in seconds
        """
        data = await self._request("GET", "/v1/transport/presentation/time")
        # The endpoint returns just a number, not a dict
        return float(data) if data is not None else 0.0

    async def presentation_play(self) -> None:
        """Start/resume presentation playback (for media layer)."""
        await self._request("GET", "/v1/transport/presentation/play")

    async def presentation_pause(self) -> None:
        """Pause presentation playback (for media layer)."""
        await self._request("GET", "/v1/transport/presentation/pause")

    async def presentation_seek(self, position: float) -> None:
        """Seek to a specific position in the presentation.

        Args:
            position: The position in seconds to seek to
        """
        await self._request(
            "PUT", "/v1/transport/presentation/time", json_data=position
        )

    async def get_status_layers(self) -> dict[str, bool]:
        """Get the status of all layers (which layers have active content).

        Returns:
            Dictionary with layer names and their active status
            Example: {"audio": true, "messages": true, "props": false, ...}
        """
        data = await self._request("GET", "/v1/status/layers")
        return data if data else {}

    async def get_audio_transport_state(self) -> dict:
        """Get the current audio transport state (playback status).

        Returns:
            Dictionary with transport state including:
            - is_playing (bool): Whether audio is currently playing
            - name (str): Current track filename
            - duration (float): Track duration in seconds
            - uuid (str): Track UUID
            - artist (str): Artist name if available
        """
        data = await self._request("GET", "/v1/transport/audio/current")
        return data if data else {}

    async def get_audio_transport_time(self) -> float:
        """Get the current audio playback position in seconds.

        Returns:
            Current playback position in seconds
        """
        data = await self._request("GET", "/v1/transport/audio/time")
        # The endpoint returns just a number, not a dict
        return float(data) if data is not None else 0.0

    async def audio_play(self) -> None:
        """Start/resume audio playback."""
        await self._request("GET", "/v1/transport/audio/play")

    async def audio_pause(self) -> None:
        """Pause audio playback."""
        await self._request("GET", "/v1/transport/audio/pause")

    async def audio_seek(self, position: float) -> None:
        """Seek to a specific position in the audio track.

        Args:
            position: The position in seconds to seek to
        """
        await self._request("PUT", "/v1/transport/audio/time", json_data=position)

    async def audio_next(self) -> None:
        """Skip to next audio track."""
        await self._request("GET", "/v1/audio/playlist/focused/next/trigger")

    async def audio_previous(self) -> None:
        """Skip to previous audio track."""
        await self._request("GET", "/v1/audio/playlist/focused/previous/trigger")

    async def trigger_clear_group(self, group_id: str) -> None:
        """Trigger a clear group (like Clear All).

        Args:
            group_id: The UUID of the clear group to trigger
        """
        endpoint = f"/v1/clear/group/{group_id}/trigger"
        await self._request("GET", endpoint)

    async def trigger_clear_layer(self, layer: str) -> None:
        """Clear a specific layer.

        Args:
            layer: The layer to clear. Valid values: audio, messages, props,
                   announcements, slide, media, video_input
        """
        endpoint = f"/v1/clear/layer/{layer}"
        await self._request("GET", endpoint)

    async def get_libraries(self) -> list[dict[str, Any]]:
        """Get list of all presentation libraries.

        Returns:
            List of library configurations
        """
        data = await self._request("GET", "/v1/libraries")
        return data if data else []

    async def get_library_presentations(self, library_id: str) -> list[dict[str, Any]]:
        """Get list of presentations in a library.

        Args:
            library_id: The UUID of the library

        Returns:
            List of presentations in the library
        """
        data = await self._request("GET", f"/v1/library/{library_id}")
        if data and isinstance(data, dict) and "items" in data:
            return data["items"]
        return []

    async def get_presentation_details(
        self, presentation_uuid: str
    ) -> dict[str, Any] | None:
        """Get detailed information about a presentation including all slides.

        Args:
            presentation_uuid: The UUID of the presentation

        Returns:
            Presentation details with slides
        """
        data = await self._request("GET", f"/v1/presentation/{presentation_uuid}")
        return data

    async def trigger_slide(self, presentation_uuid: str, slide_index: int) -> None:
        """Trigger a specific slide in a presentation by focusing it first.

        This method focuses the presentation first, which takes you to the Library view.
        If you want to stay in the playlist view, use trigger_slide_in_library() instead.

        Args:
            presentation_uuid: The UUID of the presentation
            slide_index: The index of the slide to trigger (0-based)
        """
        # First focus the presentation
        await self._request("GET", f"/v1/presentation/{presentation_uuid}/focus")

        # Then trigger the specific slide index in the focused presentation
        await self._request("GET", f"/v1/presentation/focused/{slide_index}/trigger")

    async def trigger_playlist_item(self, playlist_id: str, item_index: int) -> None:
        """Trigger a specific item in a playlist by its index.

        This triggers the playlist item (which loads the presentation) while
        keeping ProPresenter in the playlist view.

        Args:
            playlist_id: The UUID of the playlist
            item_index: The index of the item in the playlist (0-based)
        """
        endpoint = f"/v1/playlist/{playlist_id}/{item_index}/trigger"
        _LOGGER.info("Triggering playlist item via endpoint: %s", endpoint)
        result = await self._request("GET", endpoint)
        return result

    async def focus_playlist(self, playlist_id: str) -> None:
        """Focus a specific playlist.

        This ensures the playlist is focused in ProPresenter before triggering items,
        which helps maintain the playlist view.

        Args:
            playlist_id: The UUID of the playlist to focus
        """
        endpoint = f"/v1/playlist/{playlist_id}/focus"
        _LOGGER.info("Focusing playlist via endpoint: %s", endpoint)
        result = await self._request("GET", endpoint)
        return result

    async def trigger_focused_playlist_item(self, item_index: int) -> None:
        """Trigger a specific item in the currently focused playlist.

        This triggers an item in whatever playlist is currently focused,
        maintaining the playlist view.

        Args:
            item_index: The index of the item in the focused playlist (0-based)
        """
        endpoint = f"/v1/playlist/focused/{item_index}/trigger"
        _LOGGER.info("Triggering focused playlist item via endpoint: %s", endpoint)
        result = await self._request("GET", endpoint)
        return result

    async def trigger_active_presentation_slide(self, slide_index: int) -> None:
        """Trigger a specific slide in the currently active presentation.

        Args:
            slide_index: The index of the slide to trigger (0-based)
        """
        endpoint = f"/v1/presentation/active/{slide_index}/trigger"
        _LOGGER.info("Triggering active presentation slide via endpoint: %s", endpoint)
        result = await self._request("GET", endpoint)
        return result

    async def trigger_focused_presentation_slide(self, slide_index: int) -> None:
        """Trigger a specific slide in the currently focused presentation.

        This triggers a slide in whatever presentation is currently focused in the UI,
        which helps maintain the current view (e.g., playlist view).

        Args:
            slide_index: The index of the slide to trigger (0-based)
        """
        endpoint = f"/v1/presentation/focused/{slide_index}/trigger"
        _LOGGER.info("Triggering focused presentation slide via endpoint: %s", endpoint)
        result = await self._request("GET", endpoint)
        return result

    async def trigger_active_announcement_slide(self, slide_index: int) -> None:
        """Trigger a specific slide in the currently active announcement.

        This triggers a slide in whatever announcement is currently active/showing,
        without changing the ProPresenter UI view.

        Args:
            slide_index: The index of the slide to trigger (0-based)
        """
        endpoint = f"/v1/announcement/active/{slide_index}/trigger"
        _LOGGER.info("Triggering active announcement slide via endpoint: %s", endpoint)
        result = await self._request("GET", endpoint)
        return result

    async def trigger_focused_announcement_slide(self, slide_index: int) -> None:
        """Trigger a specific slide in the currently focused announcement.

        This triggers a slide in whatever announcement is currently focused in the UI,
        which helps maintain the current view (e.g., playlist view).

        Args:
            slide_index: The index of the slide to trigger (0-based)
        """
        endpoint = f"/v1/announcement/focused/{slide_index}/trigger"
        _LOGGER.info("Triggering focused announcement slide via endpoint: %s", endpoint)
        result = await self._request("GET", endpoint)
        return result

    async def trigger_slide_in_library(
        self, library_id: str, presentation_uuid: str, slide_index: int
    ) -> None:
        """Trigger a specific slide in a presentation within a library/playlist context.

        This method triggers the slide while keeping the ProPresenter UI in the playlist view,
        rather than switching to the Library view.

        Args:
            library_id: The UUID of the library/playlist containing the presentation
            presentation_uuid: The UUID of the presentation
            slide_index: The index of the slide to trigger (0-based)
        """
        endpoint = f"/v1/library/{library_id}/{presentation_uuid}/{slide_index}/trigger"
        _LOGGER.info("Triggering slide via library endpoint: %s", endpoint)
        result = await self._request("GET", endpoint)
        return result

    async def get_focused_presentation(self) -> dict[str, Any] | None:
        """Get the currently focused presentation.

        Returns:
            Focused presentation information or None if no presentation is focused
        """
        return await self._request("GET", "/v1/presentation/focused")

    async def get_presentation_slide_index(self) -> dict[str, Any] | None:
        """Get the current presentation and slide index.

        Returns:
            Current presentation and slide index information
        """
        return await self._request("GET", "/v1/presentation/slide_index")

    async def get_announcement_slide_index(self) -> dict[str, Any] | None:
        """Get the current announcement and slide index.

        Returns:
            Current announcement and slide index information
        """
        return await self._request("GET", "/v1/announcement/slide_index")

    async def get_presentation_thumbnail(
        self, presentation_uuid: str, slide_index: int, quality: int = 400
    ) -> bytes | None:
        """Get a thumbnail image for a specific slide in a presentation.

        Args:
            presentation_uuid: The UUID of the presentation
            slide_index: The index of the slide (0-based)
            quality: Image quality (200-800, default 400)

        Returns:
            The thumbnail image data as bytes, or None if error
        """
        url = f"/v1/presentation/{presentation_uuid}/thumbnail/{slide_index}?quality={quality}"
        session = await self._get_session()

        try:
            async with async_timeout.timeout(10):
                async with session.get(f"{self.base_url}{url}") as response:
                    if response.status == 200:
                        return await response.read()
                    elif response.status == 404:
                        _LOGGER.debug("Thumbnail not found: %s", url)
                        return None
                    else:
                        _LOGGER.warning(
                            "Error fetching thumbnail: %s - %s", response.status, url
                        )
                        return None
        except Exception as e:
            _LOGGER.error("Error fetching thumbnail %s: %s", url, e)
            return None

    async def get_looks(self) -> list[dict[str, Any]]:
        """Get list of all configured looks.

        Returns:
            List of look configurations
        """
        data = await self._request("GET", "/v1/looks")
        return data if data else []

    async def get_current_look(self) -> dict[str, Any] | None:
        """Get the currently active look.

        Returns:
            Current look information or None
        """
        data = await self._request("GET", "/v1/look/current")
        return data

    async def trigger_look(self, look_uuid: str) -> None:
        """Trigger/activate a specific look.

        Args:
            look_uuid: The UUID of the look to trigger
        """
        endpoint = f"/v1/look/{look_uuid}/trigger"
        await self._request("GET", endpoint)

    async def get_audience_screens_status(self) -> bool:
        """Get the current status of audience screens.

        Returns:
            True if audience screens are enabled, False if disabled
        """
        data = await self._request("GET", "/v1/status/audience_screens")
        # API returns a boolean
        return data if isinstance(data, bool) else False

    async def set_audience_screens_status(self, enabled: bool) -> None:
        """Enable or disable audience screens.

        Args:
            enabled: True to enable audience screens, False to disable
        """
        await self._request("PUT", "/v1/status/audience_screens", json_data=enabled)

    async def get_stage_screens_status(self) -> bool:
        """Get the current status of stage screens.

        Returns:
            True if stage screens are enabled, False if disabled
        """
        data = await self._request("GET", "/v1/status/stage_screens")
        # API returns a boolean
        return data if isinstance(data, bool) else False

    async def set_stage_screens_status(self, enabled: bool) -> None:
        """Enable or disable stage screens.

        Args:
            enabled: True to enable stage screens, False to disable
        """
        await self._request("PUT", "/v1/status/stage_screens", json_data=enabled)

    async def get_capture_status(self) -> dict[str, Any]:
        """Get the current capture status and time.

        Returns:
            Dict with status, capture_time, and status_text
        """
        return await self._request("GET", "/v1/capture/status")

    async def get_capture_settings(self) -> dict[str, Any]:
        """Get the current capture settings.

        Returns:
            Dict with source, audio_routing, and disk settings
        """
        return await self._request("GET", "/v1/capture/settings")

    async def capture_operation(self, operation: str) -> None:
        """Perform a capture operation (start or stop).

        Args:
            operation: The operation to perform ("start" or "stop")
        """
        await self._request("GET", f"/v1/capture/{operation}")

    async def get_timers(self) -> list[dict[str, Any]]:
        """Get all configured timers.

        Returns:
            List of timer configurations
        """
        return await self._request("GET", "/v1/timers")

    async def get_timers_current(self) -> list[dict[str, Any]]:
        """Get current time values for all timers.

        Returns:
            List of timer states with time and state
        """
        return await self._request("GET", "/v1/timers/current")

    async def timer_operation(self, timer_uuid: str, operation: str) -> None:
        """Perform a timer operation (start, stop, reset).

        Args:
            timer_uuid: The UUID of the timer
            operation: The operation to perform ("start", "stop", or "reset")
        """
        await self._request("GET", f"/v1/timer/{timer_uuid}/{operation}")

    async def update_timer(self, timer_uuid: str, timer_config: dict) -> bool:
        """Update timer configuration.

        Args:
            timer_uuid: The UUID of the timer
            timer_config: Complete timer configuration object

        Returns:
            True if successful, False otherwise
        """
        try:
            await self._request(
                "PUT", f"/v1/timer/{timer_uuid}", json_data=timer_config
            )
            return True
        except Exception as e:
            _LOGGER.error("Failed to update timer %s: %s", timer_uuid, e)
            return False

    async def get_stage_message(self) -> str:
        """Get the current stage message text.

        Returns:
            Current stage message text (empty string if no message)
        """
        data = await self._request("GET", "/v1/stage/message")
        # API returns a string
        return data if isinstance(data, str) else ""

    async def set_stage_message(self, message: str) -> None:
        """Set/show the stage message.

        Args:
            message: The message text to display on stage screens
        """
        await self._request("PUT", "/v1/stage/message", json_data=message)

    async def clear_stage_message(self) -> None:
        """Clear/hide the stage message."""
        await self._request("DELETE", "/v1/stage/message")

    async def get_macros(self) -> list[dict[str, Any]]:
        """Get list of all configured macros.

        Returns:
            List of macro configurations
        """
        data = await self._request("GET", "/v1/macros")
        return data if data else []

    async def trigger_macro(self, macro_id: str) -> None:
        """Trigger a specific macro.

        Args:
            macro_id: The UUID of the macro to trigger
        """
        endpoint = f"/v1/macro/{macro_id}/trigger"
        await self._request("GET", endpoint)

    async def test_connection(self) -> bool:
        """Test if the connection to ProPresenter is working.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            await self.get_version()
            return True
        except ProPresenterConnectionError:
            return False
