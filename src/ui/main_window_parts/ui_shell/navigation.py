from .legacy import MainWindowUiShellMixin as _LegacyMainWindowUiShellMixin


class MainWindowUiShellNavigationMixin:
    _toggle_filter_panel = _LegacyMainWindowUiShellMixin._toggle_filter_panel
    _sync_filter_states = _LegacyMainWindowUiShellMixin._sync_filter_states
    refresh_incremental_baselines = _LegacyMainWindowUiShellMixin.refresh_incremental_baselines
    _get_selected_baseline_session_id = _LegacyMainWindowUiShellMixin._get_selected_baseline_session_id
    _set_scan_stage = _LegacyMainWindowUiShellMixin._set_scan_stage
    _set_scan_stage_code = _LegacyMainWindowUiShellMixin._set_scan_stage_code
    _on_page_changed = _LegacyMainWindowUiShellMixin._on_page_changed
    _navigate_to = _LegacyMainWindowUiShellMixin._navigate_to
