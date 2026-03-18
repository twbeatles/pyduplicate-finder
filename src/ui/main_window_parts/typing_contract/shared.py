from __future__ import annotations

from typing import TYPE_CHECKING, Any


class CommonWindowHost:
    if TYPE_CHECKING:
        current_session_id: int | None
        scan_results: dict[str, object]
        selected_folders: list[str]
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
        tree_widget: Any
        splitter: Any

        def __getattr__(self, name: str) -> Any: ...
