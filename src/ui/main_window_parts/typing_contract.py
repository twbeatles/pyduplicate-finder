from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol


class DuplicateFinderTypingContract:
    # TYPE_CHECKING: dynamically injected widgets from page builders.
    if TYPE_CHECKING:
        action_newest: Any
        action_oldest: Any
        action_pattern: Any
        action_smart: Any
        btn_add_drive: Any
        btn_add_folder: Any
        btn_cache_apply: Any
        btn_cache_copy: Any
        btn_cache_open: Any
        btn_clear_folder: Any
        btn_delete: Any
        btn_empty_tools: Any
        btn_exclude_patterns: Any
        btn_export: Any
        btn_filter_toggle: Any
        btn_go_results: Any
        btn_go_scan: Any
        btn_hardlink_checked: Any
        btn_include_patterns: Any
        btn_ops_refresh: Any
        btn_ops_view: Any
        btn_preset_settings: Any
        btn_quarantine_apply: Any
        btn_quarantine_pick: Any
        btn_quarantine_purge: Any
        btn_quarantine_purge_all: Any
        btn_quarantine_refresh: Any
        btn_quarantine_restore: Any
        btn_remove_folder: Any
        btn_results_empty_add_folder: Any
        btn_results_empty_start_scan: Any
        btn_rules_apply: Any
        btn_rules_edit: Any
        btn_schedule_apply: Any
        btn_schedule_pick: Any
        btn_select_rules: Any
        btn_select_smart: Any
        btn_shortcuts_settings: Any
        btn_show_options: Any
        btn_start_scan: Any
        btn_stop_scan: Any
        btn_theme_settings: Any
        btn_tools_go_scan: Any
        chk_byte_compare: Any
        chk_detect_folder_dup: Any
        chk_enable_hardlink: Any
        chk_follow_symlinks: Any
        chk_incremental_rescan: Any
        chk_mixed_mode: Any
        chk_name_only: Any
        chk_protect_system: Any
        chk_quarantine_enabled: Any
        chk_same_name: Any
        chk_schedule_enabled: Any
        chk_schedule_export_csv: Any
        chk_schedule_export_json: Any
        chk_similar_image: Any
        chk_skip_hidden: Any
        chk_strict_mode: Any
        chk_use_trash: Any
        cmb_baseline_session: Any
        cmb_schedule_frequency: Any
        cmb_schedule_weekday: Any
        filter_container: Any
        lbl_action_meta: Any
        lbl_baseline_session: Any
        lbl_cache_desc: Any
        lbl_cache_hash_cleanup_days: Any
        lbl_cache_session_keep_latest: Any
        lbl_cache_title: Any
        lbl_empty_desc: Any
        lbl_empty_title: Any
        lbl_ext: Any
        lbl_filter_advanced: Any
        lbl_filter_basic: Any
        lbl_filter_compare: Any
        lbl_filter_count: Any
        lbl_filter_strategy: Any
        lbl_folder_count: Any
        lbl_hardlink_title: Any
        lbl_image_preview: Any
        lbl_info_preview: Any
        lbl_min_size: Any
        lbl_ops_title: Any
        lbl_preset_title: Any
        lbl_preview_header: Any
        lbl_preview_meta: Any
        lbl_preview_name: Any
        lbl_preview_path: Any
        lbl_quarantine_days: Any
        lbl_quarantine_desc: Any
        lbl_quarantine_gb: Any
        lbl_quarantine_settings_title: Any
        lbl_quarantine_title: Any
        lbl_results_empty: Any
        lbl_results_hint: Any
        lbl_results_meta: Any
        lbl_results_page_title: Any
        lbl_results_title: Any
        lbl_rules_desc: Any
        lbl_rules_title: Any
        lbl_scan_stage: Any
        lbl_scan_summary: Any
        lbl_schedule_frequency: Any
        lbl_schedule_output: Any
        lbl_schedule_time: Any
        lbl_schedule_title: Any
        lbl_schedule_weekday: Any
        lbl_settings_hint: Any
        lbl_settings_title: Any
        lbl_shortcut_title: Any
        lbl_similarity: Any
        lbl_strict_max_errors: Any
        lbl_theme_title: Any
        lbl_tools_hint: Any
        lbl_tools_target: Any
        lbl_tools_title: Any
        list_folders: Any
        preview_info: Any
        results_stack: Any
        spin_cache_hash_cleanup_days: Any
        spin_cache_session_keep_latest: Any
        spin_min_size: Any
        spin_quarantine_days: Any
        spin_quarantine_gb: Any
        spin_similarity: Any
        spin_strict_max_errors: Any
        splitter: Any
        tbl_ops: Any
        tbl_quarantine: Any
        tree_widget: Any
        txt_extensions: Any
        txt_quarantine_path: Any
        txt_quarantine_search: Any
        txt_result_filter: Any
        txt_schedule_output: Any
        txt_schedule_time: Any
        txt_text_preview: Any

        current_session_id: int | None
        _scheduled_run_context: dict[str, object] | None
        _current_scan_stage_code: str | None

        _pending_selected_add: set[str]
        _pending_selected_remove: set[str]

        cache_manager: Any
        history_manager: Any
        quarantine_manager: Any
        preflight_analyzer: Any
        scan_controller: Any
        ops_controller: Any
        scheduler_controller: Any
        operation_flow_controller: Any
        navigation_controller: Any
        results_controller: Any
        preview_controller: Any
        settings: Any
        status_label: Any
        progress_bar: Any
        toast_manager: Any

        def __getattr__(self, name: str) -> Any: ...


class NavigationHost(Protocol):
    page_stack: Any
    status_label: Any
    sidebar: Any
    btn_stop_scan: Any
    toast_manager: Any

    def refresh_quarantine_list(self) -> None: ...
    def refresh_operations_list(self) -> None: ...


class OperationFlowHost(Protocol):
    _op_queue: list[Any]
    _op_progress: Any
    _op_worker: Any
    preflight_analyzer: Any
    quarantine_manager: Any
    cache_manager: Any
    history_manager: Any
    ops_controller: Any
    status_label: Any
    toast_manager: Any
    current_session_id: Any
    scan_results: Any

    def format_size(self, size: int) -> str: ...
    def _apply_quarantine_retention(self) -> None: ...
    def refresh_quarantine_list(self) -> None: ...
    def refresh_operations_list(self) -> None: ...
    def _remove_paths_from_results(self, deleted_paths: list[str]) -> None: ...
    def _render_results(self, results, *, selected_paths=None, file_meta=None, existence_map=None, selected_count=None) -> None: ...
    def update_undo_redo_buttons(self) -> None: ...
