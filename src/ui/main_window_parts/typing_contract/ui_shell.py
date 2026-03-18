from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .shared import CommonWindowHost


class UiShellHost(CommonWindowHost):
    if TYPE_CHECKING:
        btn_go_scan: Any
        btn_go_results: Any
        btn_tools_go_scan: Any
        btn_filter_toggle: Any
        btn_theme_settings: Any
        btn_empty_tools: Any
        btn_results_empty_add_folder: Any
        btn_results_empty_start_scan: Any
        chk_use_trash: Any
        cmb_baseline_session: Any
        filter_container: Any
        lbl_baseline_session: Any
        lbl_empty_desc: Any
        lbl_empty_title: Any
        lbl_filter_advanced: Any
        lbl_filter_basic: Any
        lbl_filter_compare: Any
        lbl_filter_count: Any
        lbl_filter_strategy: Any
        lbl_folder_count: Any
        lbl_preview_header: Any
        lbl_results_empty: Any
        lbl_results_hint: Any
        lbl_results_meta: Any
        lbl_results_page_title: Any
        lbl_results_title: Any
        lbl_scan_stage: Any
        lbl_scan_summary: Any
        lbl_tools_hint: Any
        lbl_tools_target: Any
        lbl_tools_title: Any
        page_stack: Any
        results_stack: Any
        sidebar: Any
        txt_result_filter: Any
