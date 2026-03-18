from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .shared import CommonWindowHost


class SettingsFlowHost(CommonWindowHost):
    if TYPE_CHECKING:
        btn_cache_apply: Any
        btn_cache_copy: Any
        btn_cache_open: Any
        btn_exclude_patterns: Any
        btn_include_patterns: Any
        btn_preset_settings: Any
        btn_shortcuts_settings: Any
        lbl_cache_desc: Any
        lbl_cache_hash_cleanup_days: Any
        lbl_cache_session_keep_latest: Any
        lbl_cache_title: Any
        lbl_preset_title: Any
        lbl_settings_hint: Any
        lbl_settings_title: Any
        lbl_shortcut_title: Any
        spin_cache_hash_cleanup_days: Any
        spin_cache_session_keep_latest: Any
