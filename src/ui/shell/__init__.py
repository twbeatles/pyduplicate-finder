"""Fluent shell package (경로 B)."""

from src.ui.shell.navigation import (
    ALL_PAGES,
    BOTTOM_PAGES,
    DEFAULT_PAGE,
    PAGE_INDICES,
    PAGE_ORDER,
    SHORTCUTS,
    can_switch_page,
    is_known_page,
)
from src.ui.shell.view_state import (
    SCREEN_MARGIN,
    horizontal_split_sizes,
    needed_horizontal_width,
    orientation_for_width,
    preferred_window_size,
    vertical_split_sizes,
)

__all__ = [
    "ALL_PAGES",
    "BOTTOM_PAGES",
    "DEFAULT_PAGE",
    "PAGE_INDICES",
    "PAGE_ORDER",
    "SCREEN_MARGIN",
    "SHORTCUTS",
    "can_switch_page",
    "horizontal_split_sizes",
    "is_known_page",
    "needed_horizontal_width",
    "orientation_for_width",
    "preferred_window_size",
    "vertical_split_sizes",
]
