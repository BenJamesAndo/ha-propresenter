"""Utility functions for ProPresenter integration."""

from __future__ import annotations

from typing import Any


def get_nested_value(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely get a nested value from a dictionary.

    Args:
        data: The dictionary to extract from
        *keys: The keys to traverse (e.g., "id", "name")
        default: The default value if any key is missing

    Returns:
        The value at the nested key path, or default if not found

    Example:
        get_nested_value(item, "id", "name", default="Unknown")
        # Instead of: item.get("id", {}).get("name", "Unknown")
    """
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key, {})
        else:
            return default
    return result if result != {} else default


def generate_slide_label(slide: dict[str, Any], slide_index: int) -> str:
    """Generate a label for a slide from its label, text, or index.

    Args:
        slide: The slide dict with 'label' and 'text' fields
        slide_index: The index of the slide (0-based)

    Returns:
        A string label for the slide
    """
    slide_label = slide.get("label", "")
    if not slide_label:
        slide_text = slide.get("text", "").strip()
        if slide_text:
            # Use first 40 chars of text
            slide_label = slide_text[:40] + ("..." if len(slide_text) > 40 else "")
        else:
            slide_label = f"Slide {slide_index + 1}"
    return slide_label


def make_unique_display_name(
    base_name: str,
    cache: dict[str, Any],
    slide_index: int,
) -> str:
    """Create a unique display name by appending slide index if needed.

    Args:
        base_name: The base display name
        cache: The cache dict to check for duplicates
        slide_index: The slide index to append if duplicate

    Returns:
        A unique display name
    """
    if base_name in cache:
        return f"{base_name} (#{slide_index + 1})"
    return base_name


def collect_playlist_uuids(items: list[dict[str, Any]], uuids_list: list[str]) -> None:
    """Recursively collect playlist UUIDs from items and their children.

    Args:
        items: List of playlist items
        uuids_list: List to append UUIDs to (modified in place)
    """
    for item in items:
        field_type = item.get("field_type", "")
        playlist_uuid = get_nested_value(item, "id", "uuid")

        if field_type == "playlist" and playlist_uuid:
            uuids_list.append(playlist_uuid)
        elif field_type == "group":
            children = item.get("children", [])
            if children:
                collect_playlist_uuids(children, uuids_list)
