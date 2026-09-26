"""Public UI library (srtgo patterns ported to pure PySide6)."""

from src.ui.design_system import tokens
from src.ui.design_system.components import (
    COMFORTABLE,
    COMPACT,
    PRESETS,
    DensitySwitch,
    create_card,
    create_empty_state,
    create_filter_row,
    create_hseparator,
    create_metric_card,
    create_page_header,
    create_section,
    create_section_header,
    create_status_row,
    create_vseparator,
)
from src.ui.design_system.layouts import (
    apply_page_margins,
    create_master_detail,
    create_scroll_with_action_bar,
)
from src.ui.design_system.system_theme import (
    SystemThemeWatcher,
    normalize_bool,
    resolve_startup_theme,
    system_theme,
)

__all__ = [
    "COMFORTABLE",
    "COMPACT",
    "PRESETS",
    "DensitySwitch",
    "SystemThemeWatcher",
    "apply_page_margins",
    "create_card",
    "create_empty_state",
    "create_filter_row",
    "create_hseparator",
    "create_master_detail",
    "create_metric_card",
    "create_page_header",
    "create_scroll_with_action_bar",
    "create_section",
    "create_section_header",
    "create_status_row",
    "create_vseparator",
    "normalize_bool",
    "resolve_startup_theme",
    "system_theme",
    "tokens",
]
