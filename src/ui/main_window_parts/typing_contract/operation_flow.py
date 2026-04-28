from __future__ import annotations

from typing import Any, Protocol


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
    _current_result_meta: Any
    _current_result_existence_map: Any

    def format_size(self, size: int) -> str: ...
    def _apply_quarantine_retention(self) -> None: ...
    def refresh_quarantine_list(self) -> None: ...
    def refresh_operations_list(self) -> None: ...
    def _remove_paths_from_results(self, deleted_paths: list[str]) -> None: ...
    def _render_results(self, results, *, selected_paths=None, file_meta=None, existence_map=None, selected_count=None) -> None: ...
    def _build_current_file_state_entries(self) -> dict[str, dict[str, Any]]: ...
    def perform_post_cleanup_empty_dirs(self, removed_paths) -> None: ...
    def update_undo_redo_buttons(self) -> None: ...
