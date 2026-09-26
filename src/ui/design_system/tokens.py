"""Shared design tokens (srtgo Fluent patterns ported to pure PySide6).

Single source of truth for spacing/typography/radius/brand/status/density
used by new ``src.ui.design_system`` components and page refactors.
No third-party dependency beyond PySide6; no QSS hard-coding here —
consumers map these tokens onto existing ``ModernTheme`` objectNames.
"""

from __future__ import annotations

# 8pt grid (srtgo root margins 16 + card padding 12 + row spacing 8).
SPACING_XS = 4
SPACING_SM = 6
SPACING_MD = 8
SPACING_LG = 12
SPACING_XL = 16
SPACING_2XL = 20
SPACING_3XL = 24

MARGIN_PAGE = 16
MARGIN_CARD = 12
MARGIN_CARD_TOP = 16

RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 8

# Typography scale (pt). BASE < MD < LG restores the hierarchy that
# ``src/ui/theme/stylesheet.py`` flattened (BASE == MD == 10pt).
FONT_SIZE_XS = 8
FONT_SIZE_SM = 9
FONT_SIZE_BASE = 10
FONT_SIZE_MD = 11
FONT_SIZE_LG = 12
FONT_SIZE_XL = 13
FONT_SIZE_2XL = 16

FONT_WEIGHT_NORMAL = 400
FONT_WEIGHT_MEDIUM = 500
FONT_WEIGHT_SEMIBOLD = 600
FONT_WEIGHT_BOLD = 700

# Brand accent (srtgo rail accent #E4002B reused as primary action color).
BRAND_PRIMARY = "#E4002B"
BRAND_SECONDARY = "#00A0E3"

# Status colors (srtgo theme.py).
STATUS_SUCCESS = "#2ECC71"
STATUS_WARNING = "#F1C40F"
STATUS_ERROR = "#E74C3C"
STATUS_INFO = "#3498DB"
AVAILABLE_DARK = "#4CAF50"
AVAILABLE_LIGHT = "#1B7F3B"

# Dark-mode legibility neutrals (srtgo apply_native_widget_style).
DARK_TEXT = "#E8E8E8"
DARK_BG = "#2B2B2B"
DARK_BORDER = "#3E3E3E"
DARK_SELECTED_ROW = "#3A3A3A"
DARK_HEADER_BG = "#333333"

# Window geometry (srtgo preferred_window_size clamp).
DEFAULT_WINDOW_WIDTH = 1100
DEFAULT_WINDOW_HEIGHT = 800
MIN_WINDOW_WIDTH = 640
MIN_WINDOW_HEIGHT = 560

# Card minimum widths (srtgo condition 400 / result 360).
CONDITION_CARD_MIN_WIDTH = 400
RESULT_CARD_MIN_WIDTH = 360

# Splitter handle width (srtgo 8px; results splitter keeps legacy 12px).
SPLITTER_HANDLE = 8

# Density presets: comfortable (default) vs compact.
DENSITY_COMFORTABLE = {
    "page_margin": MARGIN_PAGE,
    "card_margin": MARGIN_CARD,
    "row_spacing": SPACING_MD,
    "section_spacing": SPACING_LG,
    "row_height": 32,
}
DENSITY_COMPACT = {
    "page_margin": SPACING_LG,
    "card_margin": SPACING_MD,
    "row_spacing": SPACING_SM,
    "section_spacing": SPACING_MD,
    "row_height": 28,
}

FONT_SCALE_PTS = (
    FONT_SIZE_XS,
    FONT_SIZE_SM,
    FONT_SIZE_BASE,
    FONT_SIZE_MD,
    FONT_SIZE_LG,
    FONT_SIZE_XL,
    FONT_SIZE_2XL,
)

__all__ = [
    "AVAILABLE_DARK",
    "AVAILABLE_LIGHT",
    "BRAND_PRIMARY",
    "BRAND_SECONDARY",
    "CONDITION_CARD_MIN_WIDTH",
    "DARK_BG",
    "DARK_BORDER",
    "DARK_HEADER_BG",
    "DARK_SELECTED_ROW",
    "DARK_TEXT",
    "DEFAULT_WINDOW_HEIGHT",
    "DEFAULT_WINDOW_WIDTH",
    "DENSITY_COMFORTABLE",
    "DENSITY_COMPACT",
    "FONT_SCALE_PTS",
    "FONT_SIZE_2XL",
    "FONT_SIZE_BASE",
    "FONT_SIZE_LG",
    "FONT_SIZE_MD",
    "FONT_SIZE_SM",
    "FONT_SIZE_XL",
    "FONT_SIZE_XS",
    "FONT_WEIGHT_BOLD",
    "FONT_WEIGHT_MEDIUM",
    "FONT_WEIGHT_NORMAL",
    "FONT_WEIGHT_SEMIBOLD",
    "MARGIN_CARD",
    "MARGIN_CARD_TOP",
    "MARGIN_PAGE",
    "MIN_WINDOW_HEIGHT",
    "MIN_WINDOW_WIDTH",
    "RADIUS_LG",
    "RADIUS_MD",
    "RADIUS_SM",
    "RESULT_CARD_MIN_WIDTH",
    "SPACING_2XL",
    "SPACING_3XL",
    "SPACING_LG",
    "SPACING_MD",
    "SPACING_SM",
    "SPACING_XL",
    "SPACING_XS",
    "SPLITTER_HANDLE",
    "STATUS_ERROR",
    "STATUS_INFO",
    "STATUS_SUCCESS",
    "STATUS_WARNING",
]
