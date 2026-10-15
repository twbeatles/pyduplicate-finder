"""UI adapters package (경로 B)."""

from src.ui.adapters.legacy_widget_refs import REQUIRED_WIDGETS, missing_widgets
from src.ui.adapters.settings_binding import (
    APP_NAME,
    DEFAULTS,
    KEY_DENSITY,
    KEY_FOLLOW_SYSTEM,
    KEY_LANGUAGE,
    KEY_THEME,
    ORG_NAME,
    migrate_settings,
    read_setting,
    write_setting,
)

__all__ = [
    "APP_NAME",
    "DEFAULTS",
    "KEY_DENSITY",
    "KEY_FOLLOW_SYSTEM",
    "KEY_LANGUAGE",
    "KEY_THEME",
    "ORG_NAME",
    "REQUIRED_WIDGETS",
    "migrate_settings",
    "missing_widgets",
    "read_setting",
    "write_setting",
]
