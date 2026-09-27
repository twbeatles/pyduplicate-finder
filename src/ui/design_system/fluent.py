"""Fluent design tokens and helpers (pure PySide6, no third-party dependency).

This module ports the WinUI 3 Fluent visual language onto the existing
``ModernTheme`` palette instead of adopting ``PySide6-Fluent-Widgets``:
no new runtime dependency, no packaging change beyond hidden-import
registration, and full ``QSettings``/i18n contract compatibility.

Covered Fluent patterns:
- Accent scale (rest / hover / pressed) for light + dark modes.
- Layer fills + stroke tokens for NavigationView / Card / InfoBar surfaces.
- InfoBar severity colors (WinUI ``InfoBarSeverity``: info/success/warning/error).
- ``build_fluent_fragment``: QSS appended after the base ModernTheme sheet.
- ``apply_fluent_button``: semantic button-kind properties consumed by QSS.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Literal

FluentMode = Literal["light", "dark"]
FluentButtonKind = Literal["accent", "standard", "subtle"]
InfoSeverity = Literal["info", "success", "warning", "error"]

# WinUI default system accent (rest/hover/pressed), per color mode.
FLUENT_ACCENT: dict[str, dict[str, str]] = {
    "light": {
        "rest": "#0F6CBD",
        "hover": "#115EA3",
        "pressed": "#0C3B5E",
        "subtle_fill": "rgba(15, 108, 189, 0.10)",
        "focus_ring": "rgba(15, 108, 189, 0.45)",
    },
    "dark": {
        "rest": "#4CC2FF",
        "hover": "#77D1FF",
        "pressed": "#3AA0D6",
        "subtle_fill": "rgba(76, 194, 255, 0.14)",
        "focus_ring": "rgba(76, 194, 255, 0.45)",
    },
}

# Layered surfaces + strokes (NavigationView background, card-on-card, dividers).
FLUENT_SURFACE: dict[str, dict[str, str]] = {
    "light": {
        "nav_rest": "rgba(255, 255, 255, 0.00)",
        "nav_hover": "rgba(255, 255, 255, 0.16)",
        "nav_pressed": "rgba(255, 255, 255, 0.24)",
        "nav_selected": "rgba(255, 255, 255, 0.26)",
        "stroke": "rgba(255, 255, 255, 0.18)",
    },
    "dark": {
        "nav_rest": "rgba(255, 255, 255, 0.00)",
        "nav_hover": "rgba(255, 255, 255, 0.08)",
        "nav_pressed": "rgba(255, 255, 255, 0.12)",
        "nav_selected": "rgba(255, 255, 255, 0.14)",
        "stroke": "rgba(255, 255, 255, 0.10)",
    },
}

# WinUI InfoBar severity fills (bg / border / fg / icon glyph).
INFO_SEVERITY: dict[str, dict[str, dict[str, str]]] = {
    "light": {
        "info": {"bg": "#F3F3F3", "border": "#E1E1E1", "fg": "#1B1B1B", "icon": "#616161"},
        "success": {"bg": "#DFF6DD", "border": "#9FD89F", "fg": "#0F7B0F", "icon": "#0F7B0F"},
        "warning": {"bg": "#FFF4CE", "border": "#E6C34D", "fg": "#7A5D00", "icon": "#9D5D00"},
        "error": {"bg": "#FDE7E9", "border": "#F1AEB5", "fg": "#C42B1C", "icon": "#C42B1C"},
    },
    "dark": {
        "info": {"bg": "#2B2B2B", "border": "#3D3D3D", "fg": "#FFFFFF", "icon": "#BDBDBD"},
        "success": {"bg": "#1A3A24", "border": "#2E7D32", "fg": "#6CCB5F", "icon": "#6CCB5F"},
        "warning": {"bg": "#433519", "border": "#7A6200", "fg": "#F9D423", "icon": "#FCE100"},
        "error": {"bg": "#442726", "border": "#8C2323", "fg": "#FF99A4", "icon": "#FF99A4"},
    },
}

INFO_ICONS: dict[str, str] = {
    "info": "\u2139",
    "success": "\u2713",
    "warning": "\u26A0",
    "error": "\u2715",
}

VALID_SEVERITIES: tuple[str, ...] = ("info", "success", "warning", "error")
VALID_BUTTON_KINDS: tuple[str, ...] = ("accent", "standard", "subtle")


def normalize_mode(mode: str | None) -> str:
    """Clamp an arbitrary theme name to ``light`` / ``dark``."""
    return "dark" if str(mode or "light").lower() == "dark" else "light"


def accent_for(mode: str | None = "light") -> dict[str, str]:
    """Accent scale for a color mode (unknown modes fall back to light)."""
    return dict(FLUENT_ACCENT[normalize_mode(mode)])


def surface_for(mode: str | None = "light") -> dict[str, str]:
    """NavigationView layer fills for a color mode."""
    return dict(FLUENT_SURFACE[normalize_mode(mode)])


def info_colors(severity: str | None = "info", mode: str | None = "light") -> dict[str, str]:
    """InfoBar/toast severity colors (unknown severities fall back to info)."""
    key = severity if severity in VALID_SEVERITIES else "info"
    return dict(INFO_SEVERITY[normalize_mode(mode)][key])


def apply_fluent_button(button, kind: str = "standard"):
    """Tag a button with its Fluent kind; QSS in the fragment styles it.

    Uses dynamic properties (not objectName) so existing ``btn_primary`` /
    ``btn_secondary`` ID styling keeps precedence and nothing visual
    regresses on already-styled buttons.
    """
    if kind not in VALID_BUTTON_KINDS:
        kind = "standard"
    with suppress(Exception):
        button.setProperty("fluent_button", True)
        button.setProperty("fluent_kind", kind)
    return button


def build_fluent_fragment(mode: str | None = "light") -> str:
    """Fluent QSS appended after the base ModernTheme stylesheet.

    Radii reuse the shared ``RADIUS_SM``/``RADIUS_MD`` scale (6px/8px) so the
    encoding/token regression tests stay green; later rules win at equal
    specificity, so accent focus rings and InfoBar severities override the
    base sheet without touching it.
    """
    m = normalize_mode(mode)
    accent = FLUENT_ACCENT[m]
    return f"""
            /* ==================== FLUENT: ACCENT FOCUS ==================== */
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
                border: 1px solid {accent["rest"]};
            }}

            /* ==================== FLUENT: BUTTON KINDS ==================== */
            QPushButton[fluent_kind="accent"] {{
                background-color: {accent["rest"]};
                border: 1px solid {accent["rest"]};
                border-radius: 6px;
                color: #ffffff;
                font-weight: 600;
                padding: 8px 18px;
            }}
            QPushButton[fluent_kind="accent"]:hover {{
                background-color: {accent["hover"]};
                border-color: {accent["hover"]};
            }}
            QPushButton[fluent_kind="accent"]:pressed {{
                background-color: {accent["pressed"]};
                border-color: {accent["pressed"]};
            }}
            QPushButton[fluent_kind="accent"]:disabled {{
                background-color: transparent;
                border-color: rgba(128, 128, 128, 0.4);
                color: rgba(128, 128, 128, 0.8);
            }}
            QPushButton[fluent_kind="standard"]:hover {{
                border-color: {accent["rest"]};
            }}
            QPushButton[fluent_kind="subtle"] {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 6px 12px;
            }}
            QPushButton[fluent_kind="subtle"]:hover {{
                background-color: {accent["subtle_fill"]};
                border-color: {accent["subtle_fill"]};
            }}

            /* ==================== FLUENT: INFOBAR ==================== */
            QFrame#InfoBar {{
                border-radius: 8px;
                border: 1px solid {INFO_SEVERITY[m]["info"]["border"]};
                background-color: {INFO_SEVERITY[m]["info"]["bg"]};
            }}
            QFrame#InfoBar[severity="success"] {{
                border-color: {INFO_SEVERITY[m]["success"]["border"]};
                background-color: {INFO_SEVERITY[m]["success"]["bg"]};
            }}
            QFrame#InfoBar[severity="warning"] {{
                border-color: {INFO_SEVERITY[m]["warning"]["border"]};
                background-color: {INFO_SEVERITY[m]["warning"]["bg"]};
            }}
            QFrame#InfoBar[severity="error"] {{
                border-color: {INFO_SEVERITY[m]["error"]["border"]};
                background-color: {INFO_SEVERITY[m]["error"]["bg"]};
            }}
            QLabel#InfoBarTitle {{
                font-weight: 600;
            }}
            QPushButton#InfoBarClose {{
                background: transparent;
                border: none;
                border-radius: 6px;
                padding: 6px 8px;
                min-width: 24px;
            }}
            QPushButton#InfoBarClose:hover {{
                background-color: {accent["subtle_fill"]};
            }}
        """


__all__ = [
    "FLUENT_ACCENT",
    "FLUENT_SURFACE",
    "INFO_ICONS",
    "INFO_SEVERITY",
    "VALID_BUTTON_KINDS",
    "VALID_SEVERITIES",
    "accent_for",
    "apply_fluent_button",
    "build_fluent_fragment",
    "info_colors",
    "normalize_mode",
    "surface_for",
]
