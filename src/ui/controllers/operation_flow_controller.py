from __future__ import annotations

import logging
from typing import Any, cast

from PySide6.QtWidgets import QMessageBox, QProgressDialog

from src.core.empty_folder_finder import cleanup_empty_parent_folders
from src.core.operation_queue import Operation, OperationWorker
from src.ui.main_window_parts.typing_contract import OperationFlowHost
from src.ui.dialogs.preflight_dialog import PreflightDialog
from src.utils.i18n import strings

logger = logging.getLogger(__name__)


class OperationFlowController:
    def enqueue_operations(self, host: Any, ops: list[Operation]) -> None:
        h = cast(OperationFlowHost, host)
        h._op_queue = list(ops or [])
        self.start_next_operation(h)

    def start_next_operation(self, host: Any) -> None:
        h = cast(OperationFlowHost, host)
        if not h._op_queue:
            return
        op = h._op_queue.pop(0)
        self.start_operation(h, op, allow_queue_continue=True)

    def start_operation(self, host: Any, op: Operation, allow_queue_continue: bool = False) -> None:
        h = cast(OperationFlowHost, host)
        if h._op_worker and h._op_worker.isRunning():
            return

        rep = None
        if op.op_type in ("delete_quarantine", "delete_trash"):
            if op.op_type == "delete_quarantine":
                qdir = None
                try:
                    qdir = h.quarantine_manager.get_quarantine_dir()
                except Exception:
                    qdir = None
                rep = h.preflight_analyzer.analyze_delete(op.paths, quarantine_dir=qdir)
            else:
                rep = h.preflight_analyzer.analyze_delete_trash(op.paths)

            dlg = PreflightDialog(rep, cast(Any, h))
            if not dlg.exec() or not dlg.can_proceed:
                h._op_queue.clear()
                return

            try:
                eligible = list(getattr(rep, "eligible_paths", []) or [])
                count = len(eligible)
                opt = getattr(op, "options", {}) or {}
                filter_active = bool(opt.get("filter_active"))
                try:
                    visible_checked = int(opt.get("visible_checked") or 0)
                except Exception:
                    visible_checked = 0
                visible_checked = min(visible_checked, count) if count else visible_checked

                size_str = h.format_size(int(getattr(rep, "bytes_total", 0) or 0))
                info_lines = [
                    strings.tr("confirm_delete_selected_counts").format(total=count, visible=visible_checked),
                    strings.tr("msg_total_size").format(size=size_str),
                ]
                if filter_active:
                    info_lines.append(strings.tr("msg_delete_includes_hidden"))

                if op.op_type == "delete_trash":
                    msg = strings.tr("confirm_trash_delete").format(count)
                else:
                    msg = strings.tr("confirm_delete_quarantine").format(count=count)
                if info_lines:
                    msg = msg + "\n\n" + "\n".join(info_lines)

                res = QMessageBox.question(
                    cast(Any, host),
                    strings.tr("confirm_delete_title"),
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if res != QMessageBox.StandardButton.Yes:
                    h._op_queue.clear()
                    return

                op.paths = eligible
            except Exception:
                pass
        elif op.op_type == "hardlink_consolidate":
            raw_targets = op.options.get("targets")
            targets = list(raw_targets) if isinstance(raw_targets, (list, tuple)) else []
            rep = h.preflight_analyzer.analyze_hardlink(
                str(op.options.get("canonical") or ""),
                targets,
            )
            dlg = PreflightDialog(rep, cast(Any, h))
            if not dlg.exec() or not dlg.can_proceed:
                h._op_queue.clear()
                return

        h._op_progress = QProgressDialog(strings.tr("status_working"), strings.tr("btn_cancel"), 0, 100, cast(Any, h))
        h._op_progress.setWindowTitle(strings.tr("app_title"))
        h._op_progress.setAutoClose(False)
        h._op_progress.setAutoReset(False)
        h._op_progress.canceled.connect(lambda: self.cancel_operation(h))
        h._op_progress.show()

        h._op_worker = OperationWorker(
            cache_manager=h.cache_manager,
            quarantine_manager=h.quarantine_manager,
            history_manager=h.history_manager,
            op=op,
        )
        h._op_worker.progress_updated.connect(lambda val, msg: self.on_progress(h, val, msg))
        h._op_worker.operation_result.connect(
            lambda result: self.on_finished(h, result, allow_queue_continue)
        )
        h._op_worker.start()

    @staticmethod
    def cancel_operation(host: Any) -> None:
        h = cast(OperationFlowHost, host)
        try:
            if h._op_worker:
                h._op_worker.stop()
        except Exception:
            pass

    @staticmethod
    def on_progress(host: Any, val: int, msg: str) -> None:
        h = cast(OperationFlowHost, host)
        try:
            if h._op_progress:
                h._op_progress.setValue(int(val))
                h._op_progress.setLabelText(str(msg or ""))
        except Exception:
            pass

    def on_finished(self, host: Any, result: Any, allow_queue_continue: bool) -> None:
        h = cast(OperationFlowHost, host)
        try:
            if h._op_progress:
                h._op_progress.setValue(100)
                h._op_progress.close()
        except Exception:
            pass
        h._op_progress = None

        try:
            h._op_worker = None
        except Exception:
            pass

        try:
            if result and getattr(result, "op_type", "") in ("delete_quarantine", "hardlink_consolidate", "purge"):
                h._apply_quarantine_retention()
            h.refresh_quarantine_list()
            h.refresh_operations_list()
        except Exception:
            pass

        try:
            if result and getattr(result, "op_type", "") in (
                "delete_quarantine",
                "delete_trash",
                "hardlink_consolidate",
            ):
                removed = list(getattr(result, "succeeded", []) or [])
                if removed:
                    h._remove_paths_from_results(removed)
                    selected = (
                        h.cache_manager.load_selected_paths(h.current_session_id)
                        if h.current_session_id
                        else []
                    )
                    h._render_results(h.scan_results, selected_paths=list(selected))
                    if h.current_session_id:
                        h.cache_manager.save_scan_results(h.current_session_id, h.scan_results)
        except Exception:
            pass

        try:
            if (
                result
                and getattr(result, "op_type", "") in ("delete_quarantine", "delete_trash", "hardlink_consolidate")
                and hasattr(h, "perform_post_cleanup_empty_dirs")
            ):
                h.perform_post_cleanup_empty_dirs(list(getattr(result, "succeeded", []) or []))
        except Exception:
            logger.exception("Post-delete empty folder cleanup failed")

        try:
            msg = getattr(result, "message", "") or strings.tr("status_done")
            h.status_label.setText(msg)
            if hasattr(h, "toast_manager") and h.toast_manager:
                if getattr(result, "status", "") == "failed":
                    h.toast_manager.error(msg, duration=3500)
                elif getattr(result, "status", "") == "partial":
                    h.toast_manager.warning(msg, duration=3500)
                else:
                    h.toast_manager.success(msg, duration=2500)
        except Exception:
            pass

        try:
            failed = list(getattr(result, "failed", []) or [])
            if failed and not allow_queue_continue:
                res = QMessageBox.question(
                    cast(Any, host),
                    strings.tr("app_title"),
                    strings.tr("msg_retry_failed").format(len(failed)),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if res == QMessageBox.StandardButton.Yes:
                    retry_op = h.ops_controller.build_retry_operation(result)
                    if retry_op:
                        self.start_operation(h, retry_op)
                        return
        except Exception:
            pass

        try:
            h.update_undo_redo_buttons()
        except Exception:
            pass

        if allow_queue_continue and h._op_queue and getattr(result, "status", "") not in ("cancelled", "failed"):
            self.start_next_operation(h)
        else:
            h._op_queue.clear()
