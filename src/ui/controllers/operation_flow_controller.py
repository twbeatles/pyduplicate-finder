from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import QMessageBox, QProgressDialog

from src.core.operation_queue import Operation, OperationWorker
from src.ui.dialogs.preflight_dialog import PreflightDialog
from src.utils.i18n import strings

logger = logging.getLogger(__name__)


class OperationFlowController:
    def enqueue_operations(self, host: Any, ops: list[Operation]) -> None:
        host._op_queue = list(ops or [])
        self.start_next_operation(host)

    def start_next_operation(self, host: Any) -> None:
        if not host._op_queue:
            return
        op = host._op_queue.pop(0)
        self.start_operation(host, op, allow_queue_continue=True)

    def start_operation(self, host: Any, op: Operation, allow_queue_continue: bool = False) -> None:
        if host._op_worker and host._op_worker.isRunning():
            return

        rep = None
        if op.op_type in ("delete_quarantine", "delete_trash"):
            if op.op_type == "delete_quarantine":
                qdir = None
                try:
                    qdir = host.quarantine_manager.get_quarantine_dir()
                except Exception:
                    qdir = None
                rep = host.preflight_analyzer.analyze_delete(op.paths, quarantine_dir=qdir)
            else:
                rep = host.preflight_analyzer.analyze_delete_trash(op.paths)

            dlg = PreflightDialog(rep, host)
            if not dlg.exec() or not dlg.can_proceed:
                host._op_queue.clear()
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

                size_str = host.format_size(int(getattr(rep, "bytes_total", 0) or 0))
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
                    host,
                    strings.tr("confirm_delete_title"),
                    msg,
                    QMessageBox.Yes | QMessageBox.No,
                )
                if res != QMessageBox.Yes:
                    host._op_queue.clear()
                    return

                op.paths = eligible
            except Exception:
                pass
        elif op.op_type == "hardlink_consolidate":
            rep = host.preflight_analyzer.analyze_hardlink(
                str(op.options.get("canonical") or ""),
                list(op.options.get("targets") or []),
            )
            dlg = PreflightDialog(rep, host)
            if not dlg.exec() or not dlg.can_proceed:
                host._op_queue.clear()
                return

        host._op_progress = QProgressDialog(strings.tr("status_working"), strings.tr("btn_cancel"), 0, 100, host)
        host._op_progress.setWindowTitle(strings.tr("app_title"))
        host._op_progress.setAutoClose(False)
        host._op_progress.setAutoReset(False)
        host._op_progress.canceled.connect(lambda: self.cancel_operation(host))
        host._op_progress.show()

        host._op_worker = OperationWorker(
            cache_manager=host.cache_manager,
            quarantine_manager=host.quarantine_manager,
            history_manager=host.history_manager,
            op=op,
        )
        host._op_worker.progress_updated.connect(lambda val, msg: self.on_progress(host, val, msg))
        host._op_worker.operation_result.connect(
            lambda result: self.on_finished(host, result, allow_queue_continue)
        )
        host._op_worker.start()

    @staticmethod
    def cancel_operation(host: Any) -> None:
        try:
            if host._op_worker:
                host._op_worker.stop()
        except Exception:
            pass

    @staticmethod
    def on_progress(host: Any, val: int, msg: str) -> None:
        try:
            if host._op_progress:
                host._op_progress.setValue(int(val))
                host._op_progress.setLabelText(str(msg or ""))
        except Exception:
            pass

    def on_finished(self, host: Any, result: Any, allow_queue_continue: bool) -> None:
        try:
            if host._op_progress:
                host._op_progress.setValue(100)
                host._op_progress.close()
        except Exception:
            pass
        host._op_progress = None

        try:
            host._op_worker = None
        except Exception:
            pass

        try:
            if result and getattr(result, "op_type", "") in ("delete_quarantine", "hardlink_consolidate", "purge"):
                host._apply_quarantine_retention()
            host.refresh_quarantine_list()
            host.refresh_operations_list()
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
                    host._remove_paths_from_results(removed)
                    selected = (
                        host.cache_manager.load_selected_paths(host.current_session_id)
                        if host.current_session_id
                        else []
                    )
                    host._render_results(host.scan_results, selected_paths=list(selected))
                    if host.current_session_id:
                        host.cache_manager.save_scan_results(host.current_session_id, host.scan_results)
        except Exception:
            pass

        try:
            msg = getattr(result, "message", "") or strings.tr("status_done")
            host.status_label.setText(msg)
            if hasattr(host, "toast_manager") and host.toast_manager:
                if getattr(result, "status", "") == "failed":
                    host.toast_manager.error(msg, duration=3500)
                elif getattr(result, "status", "") == "partial":
                    host.toast_manager.warning(msg, duration=3500)
                else:
                    host.toast_manager.success(msg, duration=2500)
        except Exception:
            pass

        try:
            failed = list(getattr(result, "failed", []) or [])
            if failed and not allow_queue_continue:
                res = QMessageBox.question(
                    host,
                    strings.tr("app_title"),
                    strings.tr("msg_retry_failed").format(len(failed)),
                    QMessageBox.Yes | QMessageBox.No,
                )
                if res == QMessageBox.Yes:
                    retry_op = host.ops_controller.build_retry_operation(result)
                    if retry_op:
                        self.start_operation(host, retry_op)
                        return
        except Exception:
            pass

        if allow_queue_continue and host._op_queue and getattr(result, "status", "") not in ("cancelled", "failed"):
            self.start_next_operation(host)
        else:
            host._op_queue.clear()
