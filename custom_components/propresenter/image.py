"""Image platform for ProPresenter integration."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import logging

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .base import ProPresenterBaseEntity
from .coordinator import ProPresenterCoordinator, ProPresenterStreamingCoordinator
from .utils import get_nested_value

_LOGGER = logging.getLogger(__name__)


def create_black_image(width: int = 1920, height: int = 1080) -> bytes:
    """Create a black JPEG image of specified dimensions."""
    try:
        from PIL import Image
        
        # Create a black image
        img = Image.new('RGB', (width, height), color='black')
        
        # Convert to JPEG bytes
        output = BytesIO()
        img.save(output, format='JPEG', quality=95)
        return output.getvalue()
    except ImportError:
        # Fallback to 1x1 black pixel if PIL not available
        return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\xff\xd9'


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ProPresenter image entities."""
    coordinator: ProPresenterCoordinator = config_entry.runtime_data["coordinator"]
    streaming_coordinator: ProPresenterStreamingCoordinator = config_entry.runtime_data["streaming_coordinator"]
    
    entities = [
        ProPresenterPresentationThumbnail(hass, coordinator, streaming_coordinator, config_entry),
        ProPresenterPresentationNextSlideThumbnail(hass, coordinator, streaming_coordinator, config_entry),
        ProPresenterPresentationPreviousSlideThumbnail(hass, coordinator, streaming_coordinator, config_entry),
        ProPresenterAnnouncementThumbnail(hass, coordinator, streaming_coordinator, config_entry),
    ]
    
    async_add_entities(entities)


class SlideNotesMixin:
    """Mixin class for fetching and caching slide notes."""
    
    def _init_notes_cache(self):
        """Initialize notes caching variables."""
        self._cached_notes_pres_uuid: str | None = None
        self._cached_notes_pres_details: dict | None = None
        self._current_slide_notes: str | None = None
    
    async def _async_fetch_slide_notes(self, pres_uuid: str, slide_index: int) -> None:
        """Fetch presentation details and extract slide notes."""
        try:
            # Only fetch presentation details if presentation changed
            if pres_uuid != self._cached_notes_pres_uuid:
                pres_details = await self.api.get_presentation_details(pres_uuid)
                self._cached_notes_pres_uuid = pres_uuid
                self._cached_notes_pres_details = pres_details
            else:
                pres_details = self._cached_notes_pres_details
            
            # Extract notes from cached presentation data
            notes = self._extract_slide_notes(pres_details, slide_index)
            self._current_slide_notes = notes or ""
        except Exception as e:
            _LOGGER.debug("Error fetching slide notes: %s", e)
            self._current_slide_notes = None

        self.async_write_ha_state()
    
    def _extract_slide_notes(self, pres_details: dict | None, slide_index: int) -> str | None:
        """Extract slide notes from presentation details by slide index."""
        if not pres_details:
            return None
            
        presentation_data = pres_details.get("presentation", {})
        groups = presentation_data.get("groups", [])
        current_index = 0
        
        for group in groups:
            slides = group.get("slides", [])
            for slide in slides:
                if current_index == slide_index:
                    return slide.get("notes") or slide.get("notes_html") or ""
                current_index += 1
        
        return None


class ProPresenterPresentationThumbnail(SlideNotesMixin, ProPresenterBaseEntity, ImageEntity):
    """Image entity showing the current presentation slide thumbnail."""

    _attr_name = "Presentation Current Slide"
    _attr_icon = "mdi:presentation"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the presentation thumbnail image entity."""
        ProPresenterBaseEntity.__init__(self, streaming_coordinator, config_entry, static_coordinator=coordinator)
        ImageEntity.__init__(self, hass)
        self.api = coordinator.api
        self._attr_unique_id = f"{config_entry.entry_id}_presentation_thumbnail"
        self._cached_image: bytes | None = None
        self._black_image: bytes | None = None  # Cache the black image
        self._current_pres_uuid: str | None = None
        self._current_slide_index: int | None = None
        self._current_slide_label: str | None = None
        self._image_last_updated: datetime | None = None
        self._slide_layer_active: bool = True  # Track slide layer status
        # Cache presentation info to preserve when layer is off
        self._cached_presentation_name: str | None = None
        self._cached_presentation_uuid: str | None = None
        self._cached_slide_index: int | None = None
        # Initialize notes caching from mixin
        self._init_notes_cache()
    
    @property
    def image_last_updated(self) -> datetime | None:
        """Return when the image was last updated."""
        return self._image_last_updated

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Check if slide layer status changed
        status_layers = self.coordinator.data.get("status_layers", {})
        slide_layer_active = status_layers.get("slide", False)
        
        if slide_layer_active != self._slide_layer_active:
            self._slide_layer_active = slide_layer_active
            # Update timestamp to force frontend refresh
            self._image_last_updated = dt_util.utcnow()
            self.async_write_ha_state()
        
        # Check if slide changed and trigger update
        slide_index_data = self.coordinator.data.get("slide_index")
        if slide_index_data:
            presentation_index_info = slide_index_data.get("presentation_index")
            if presentation_index_info:
                pres_uuid = get_nested_value(presentation_index_info, "presentation_id", "uuid")
                slide_index = presentation_index_info.get("index")
                pres_name = get_nested_value(presentation_index_info, "presentation_id", "name", default="Unknown")
                
                # Cache presentation info for attributes (preserve even when layer is off)
                self._cached_presentation_name = pres_name
                self._cached_presentation_uuid = pres_uuid
                self._cached_slide_index = slide_index
                
                # If slide changed, clear cache to force refresh
                if pres_uuid != self._current_pres_uuid or slide_index != self._current_slide_index:
                    # Update current slide tracking (so we know what's displayed)
                    self._current_pres_uuid = pres_uuid
                    self._current_slide_index = slide_index

                    # Update timestamp so frontend will refetch the image
                    # Use HA's timezone-aware now() function
                    self._image_last_updated = dt_util.utcnow()
                    
                    # Clear image cache to force fetch on next image request
                    self._cached_image = None
                    
                    # Fetch slide notes asynchronously
                    if pres_uuid and slide_index is not None:
                        self.hass.async_create_task(self._async_fetch_slide_notes(pres_uuid, slide_index))
                    
                    self.async_write_ha_state()
        
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, str | int | bool | None]:
        """Return extra state attributes."""
        status_layers = self.coordinator.data.get("status_layers", {})
        
        # Use cached presentation info (preserved even when layer is off)
        attributes = {
            "slide_layer_active": status_layers.get("slide", False),
            "presentation_name": self._cached_presentation_name,
            "presentation_uuid": self._cached_presentation_uuid,
            "slide_index": self._cached_slide_index,
            "slide_notes": self._current_slide_notes,
        }
        
        return attributes

    @property
    def image_url(self) -> str | None:
        """Return the URL of the current slide thumbnail."""
        slide_index_data = self.coordinator.data.get("slide_index")
        if not slide_index_data:
            return None
        
        presentation_index_info = slide_index_data.get("presentation_index")
        if not presentation_index_info:
            return None
            
        pres_uuid = get_nested_value(presentation_index_info, "presentation_id", "uuid")
        slide_index = presentation_index_info.get("index")
        
        if pres_uuid is None or slide_index is None:
            return None
        
        # Build thumbnail URL with quality parameter (200-800, higher = better quality)
        return f"http://{self.api.host}:{self.api.port}/v1/presentation/{pres_uuid}/thumbnail/{slide_index}?quality=800"

    async def async_image(self) -> bytes | None:
        """Return the image of the current slide, or black image if slide layer is cleared."""
        # Check if slide layer is active from streaming coordinator
        status_layers = self.coordinator.data.get("status_layers", {})
        slide_layer_active = status_layers.get("slide", False)
        
        # If slide layer is cleared/off, return black image
        if not slide_layer_active:
            # Create black image if not cached (will match thumbnail size)
            if not self._black_image:
                self._black_image = create_black_image(1920, 1080)  # Standard HD size
            return self._black_image
        
        slide_index_data = self.coordinator.data.get("slide_index")
        if not slide_index_data:
            return self._cached_image
        
        presentation_index_info = slide_index_data.get("presentation_index")
        if not presentation_index_info:
            return self._cached_image
            
        pres_uuid = get_nested_value(presentation_index_info, "presentation_id", "uuid")
        slide_index = presentation_index_info.get("index")
        
        if pres_uuid is None or slide_index is None:
            return self._cached_image
        
        # Check if we have a cached image for the current slide
        if pres_uuid == self._current_pres_uuid and slide_index == self._current_slide_index and self._cached_image:
            return self._cached_image
        
        # Fetch new thumbnail
        try:
            thumbnail_data = await self.api.get_presentation_thumbnail(pres_uuid, slide_index, quality=800)
            if thumbnail_data:
                self._cached_image = thumbnail_data
                self._current_pres_uuid = pres_uuid
                self._current_slide_index = slide_index
            return thumbnail_data
        except Exception as e:
            _LOGGER.error("Error fetching presentation thumbnail: %s", e)
            return self._cached_image


class ProPresenterPresentationSlideThumbnailBase(SlideNotesMixin, ProPresenterBaseEntity, ImageEntity):
    """Base class for next/previous slide thumbnails."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
        unique_id_suffix: str,
        slide_offset: int,  # -1 for previous, +1 for next
        name_type: str,  # "previous" or "next"
    ) -> None:
        """Initialize the slide thumbnail image entity."""
        ProPresenterBaseEntity.__init__(self, streaming_coordinator, config_entry, static_coordinator=coordinator)
        ImageEntity.__init__(self, hass)
        self.api = coordinator.api
        self._attr_unique_id = f"{config_entry.entry_id}_{unique_id_suffix}"
        self._cached_image: bytes | None = None
        self._current_pres_uuid: str | None = None
        self._current_slide_index: int | None = None
        self._image_last_updated: datetime | None = None
        self._slide_offset = slide_offset
        self._name_type = name_type
        # Initialize notes caching from mixin
        self._init_notes_cache()
    
    @property
    def image_last_updated(self) -> datetime | None:
        """Return when the image was last updated."""
        return self._image_last_updated

    def _calculate_target_index(self, current_index: int | None) -> int | None:
        """Calculate the target slide index based on offset."""
        if current_index is None:
            return None
        target_index = current_index + self._slide_offset
        return target_index if target_index >= 0 else None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        slide_index_data = self.coordinator.data.get("slide_index")
        if slide_index_data:
            presentation_index_info = slide_index_data.get("presentation_index")
            if presentation_index_info:
                pres_uuid = get_nested_value(presentation_index_info, "presentation_id", "uuid")
                slide_index = presentation_index_info.get("index")
                target_index = self._calculate_target_index(slide_index)
                
                if pres_uuid != self._current_pres_uuid or target_index != self._current_slide_index:
                    self._current_pres_uuid = pres_uuid
                    self._current_slide_index = target_index
                    self._image_last_updated = dt_util.utcnow()
                    self._cached_image = None
                    
                    # Fetch slide notes asynchronously
                    if pres_uuid and target_index is not None:
                        self.hass.async_create_task(self._async_fetch_slide_notes(pres_uuid, target_index))
                    
                    self.async_write_ha_state()
        
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, str | int | bool | None]:
        """Return extra state attributes."""
        attributes = {
            "presentation_uuid": self._current_pres_uuid,
            "slide_index": self._current_slide_index,
            "slide_notes": self._current_slide_notes,
        }
        
        return attributes

    @property
    def image_url(self) -> str | None:
        """Return the URL of the target slide thumbnail."""
        slide_index_data = self.coordinator.data.get("slide_index")
        if not slide_index_data:
            return None
        
        presentation_index_info = slide_index_data.get("presentation_index")
        if not presentation_index_info:
            return None
            
        pres_uuid = get_nested_value(presentation_index_info, "presentation_id", "uuid")
        slide_index = presentation_index_info.get("index")
        target_index = self._calculate_target_index(slide_index)
        
        if pres_uuid is None or target_index is None:
            return None
        
        return f"http://{self.api.host}:{self.api.port}/v1/presentation/{pres_uuid}/thumbnail/{target_index}?quality=800"

    async def async_image(self) -> bytes | None:
        """Return the image of the target slide."""
        slide_index_data = self.coordinator.data.get("slide_index")
        if not slide_index_data:
            return self._cached_image
        
        presentation_index_info = slide_index_data.get("presentation_index")
        if not presentation_index_info:
            return self._cached_image
            
        pres_uuid = get_nested_value(presentation_index_info, "presentation_id", "uuid")
        slide_index = presentation_index_info.get("index")
        target_index = self._calculate_target_index(slide_index)
        
        if pres_uuid is None or target_index is None:
            return self._cached_image
        
        if pres_uuid == self._current_pres_uuid and target_index == self._current_slide_index and self._cached_image:
            return self._cached_image
        
        try:
            thumbnail_data = await self.api.get_presentation_thumbnail(pres_uuid, target_index, quality=800)
            if thumbnail_data:
                self._cached_image = thumbnail_data
                self._current_pres_uuid = pres_uuid
                self._current_slide_index = target_index
            return thumbnail_data
        except Exception as e:
            _LOGGER.error("Error fetching %s slide thumbnail: %s", self._name_type, e)
            return self._cached_image


class ProPresenterPresentationNextSlideThumbnail(ProPresenterPresentationSlideThumbnailBase):
    """Image entity showing the next presentation slide thumbnail."""

    _attr_name = "Presentation Next Slide Thumbnail"
    _attr_icon = "mdi:presentation-play"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the next slide thumbnail image entity."""
        super().__init__(
            hass, coordinator, streaming_coordinator, config_entry,
            unique_id_suffix="presentation_next_slide_thumbnail",
            slide_offset=1,
            name_type="next"
        )


class ProPresenterPresentationPreviousSlideThumbnail(ProPresenterPresentationSlideThumbnailBase):
    """Image entity showing the previous presentation slide thumbnail."""

    _attr_name = "Presentation Previous Slide Thumbnail"
    _attr_icon = "mdi:skip-previous"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the previous slide thumbnail image entity."""
        super().__init__(
            hass, coordinator, streaming_coordinator, config_entry,
            unique_id_suffix="presentation_previous_slide_thumbnail",
            slide_offset=-1,
            name_type="previous"
        )


class ProPresenterAnnouncementThumbnail(ProPresenterBaseEntity, ImageEntity):
    """Image entity showing the current announcement slide thumbnail."""

    _attr_name = "Announcement Thumbnail"
    _attr_icon = "mdi:bullhorn"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ProPresenterCoordinator,
        streaming_coordinator: ProPresenterStreamingCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the announcement thumbnail image entity."""
        ProPresenterBaseEntity.__init__(self, streaming_coordinator, config_entry, static_coordinator=coordinator)
        ImageEntity.__init__(self, hass)
        self.api = coordinator.api
        self._attr_unique_id = f"{config_entry.entry_id}_announcement_thumbnail"
        self._cached_image: bytes | None = None
        self._current_pres_uuid: str | None = None
        self._current_slide_index: int | None = None
        self._current_slide_label: str | None = None
        self._image_last_updated: datetime | None = None
    
    @property
    def image_last_updated(self) -> datetime | None:
        """Return when the image was last updated."""
        return self._image_last_updated

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Check if slide changed and trigger update
        slide_index_data = self.coordinator.data.get("announcement_slide_index")
        if slide_index_data:
            announcement_index_info = slide_index_data.get("announcement_index")
            if announcement_index_info:
                pres_uuid = get_nested_value(announcement_index_info, "presentation_id", "uuid")
                slide_index = announcement_index_info.get("index")
                
                # If slide changed, clear cache to force refresh
                if pres_uuid != self._current_pres_uuid or slide_index != self._current_slide_index:
                    # Update current slide tracking (so we know what's displayed)
                    self._current_pres_uuid = pres_uuid
                    self._current_slide_index = slide_index

                    # Update timestamp so frontend will refetch the image
                    # Use HA's timezone-aware now() function
                    self._image_last_updated = dt_util.utcnow()
                    
                    # Clear image cache to force fetch on next image request
                    self._cached_image = None
                    self.async_write_ha_state()
        
        super()._handle_coordinator_update()

    @property
    def image_url(self) -> str | None:
        """Return the URL of the current announcement slide thumbnail."""
        slide_index_data = self.coordinator.data.get("announcement_slide_index")
        if not slide_index_data:
            return None
        
        announcement_index_info = slide_index_data.get("announcement_index")
        if not announcement_index_info:
            return None
            
        pres_uuid = get_nested_value(announcement_index_info, "presentation_id", "uuid")
        slide_index = announcement_index_info.get("index")
        
        if pres_uuid is None or slide_index is None:
            return None
        
        # Build thumbnail URL with quality parameter
        return f"http://{self.api.host}:{self.api.port}/v1/presentation/{pres_uuid}/thumbnail/{slide_index}?quality=800"

    async def async_image(self) -> bytes | None:
        """Return the image of the current announcement slide."""
        slide_index_data = self.coordinator.data.get("announcement_slide_index")
        if not slide_index_data:
            return self._cached_image
        
        announcement_index_info = slide_index_data.get("announcement_index")
        if not announcement_index_info:
            return self._cached_image
            
        pres_uuid = get_nested_value(announcement_index_info, "presentation_id", "uuid")
        slide_index = announcement_index_info.get("index")
        
        if pres_uuid is None or slide_index is None:
            return self._cached_image
        
        # Check if we have a cached image for the current slide
        if pres_uuid == self._current_pres_uuid and slide_index == self._current_slide_index and self._cached_image:
            return self._cached_image
        
        # Fetch new thumbnail
        try:
            thumbnail_data = await self.api.get_presentation_thumbnail(pres_uuid, slide_index, quality=800)
            if thumbnail_data:
                self._cached_image = thumbnail_data
                self._current_pres_uuid = pres_uuid
                self._current_slide_index = slide_index
                _LOGGER.debug("Updated announcement thumbnail for slide %d", slide_index)
            return thumbnail_data
        except Exception as e:
            _LOGGER.error("Error fetching announcement thumbnail: %s", e)
            return self._cached_image
