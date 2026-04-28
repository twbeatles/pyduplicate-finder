from __future__ import annotations

from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel, QProgressBar, QCheckBox, QMessageBox, QGroupBox, QTreeWidget, QTreeWidgetItem, QToolBar, QSpinBox, QLineEdit, QMenu, QSplitter, QTextEdit, QScrollArea, QStyle, QToolButton, QSizePolicy, QListWidget, QDoubleSpinBox, QInputDialog, QStackedWidget, QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt, Slot, QSize, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence, QIcon, QPixmap, QFont, QCursor

import os
import sys
import platform
import subprocess
import string
import ctypes
import json
import logging
import re
from datetime import datetime
from typing import Any, TYPE_CHECKING

from src.core.history import HistoryManager
from src.core.cache_manager import CacheManager
from src.core.preset_manager import PresetManager, get_default_config
from src.core.file_lock_checker import FileLockChecker
from src.core.empty_folder_finder import cleanup_empty_parent_folders
from src.core.quarantine_manager import QuarantineManager
from src.core.preflight import PreflightAnalyzer
from src.core.selection_rules import parse_rules
from src.core.operation_queue import Operation
from src.core.scan_engine import ScanConfig, validate_similar_image_dependency
from src.core.result_schema import dump_results_v2, load_results_any
from src.core.result_groups import classify_result_group
from src.core.scan_types import (
    EXEMPTION_ACTION_IGNORE,
    EXEMPTION_ACTION_SAFELIST,
    EXEMPTION_KIND_CONTENT_HASH,
    EXEMPTION_KIND_EXACT_PATH,
    EXEMPTION_KIND_PATH_GLOB,
)
from src.core.scheduler import ScheduleConfig
from src.ui.empty_folder_dialog import EmptyFolderDialog
from src.ui.history_messages import parse_structured_history_message
from src.ui.components.results_tree import ResultsTreeWidget
from src.ui.components.sidebar import Sidebar
from src.ui.components.toast import ToastManager
from src.ui.dialogs.preset_dialog import PresetDialog
from src.ui.dialogs.exclude_patterns_dialog import ExcludePatternsDialog
from src.ui.dialogs.shortcut_settings_dialog import ShortcutSettingsDialog
from src.ui.dialogs.selection_rules_dialog import SelectionRulesDialog
from src.ui.dialogs.preflight_dialog import PreflightDialog
from src.ui.dialogs.operation_log_dialog import OperationLogDialog
from src.utils.i18n import strings
from src.ui.theme import ModernTheme
from src.ui.pages.scan_page import build_scan_page
from src.ui.pages.results_page import build_results_page
from src.ui.pages.tools_page import build_tools_page
from src.ui.pages.settings_page import build_settings_page
from src.ui.controllers.scan_controller import ScanController
from src.ui.controllers.ops_controller import OpsController
from src.ui.controllers.scheduler_controller import SchedulerController
from src.ui.controllers.operation_flow_controller import OperationFlowController
from src.ui.controllers.navigation_controller import NavigationController
from src.ui.controllers.results_controller import ResultsController, ResultEntry
from src.ui.controllers.preview_controller import PreviewController
from src.ui.main_window_parts.typing_contract import DuplicateFinderTypingContract

logger = logging.getLogger(__name__)

def _mw():
    import src.ui.main_window as main_window_module

    return main_window_module



class MainWindowToolsFlowMixin(DuplicateFinderTypingContract):
    def refresh_insights_page(self: Any):
        if not hasattr(self, "lbl_insight_scans_value"):
            return
        try:
            conn = self.cache_manager._get_conn()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) FROM scan_sessions")
            total_sessions, completed_sessions = cur.fetchone() or (0, 0)
            cur.execute(
                """
                SELECT COUNT(*), SUM(CASE WHEN status IN ('partial', 'failed', 'abandoned') THEN 1 ELSE 0 END)
                FROM (
                    SELECT status FROM scan_sessions ORDER BY updated_at DESC LIMIT 20
                )
                """
            )
            fail_sample, fail_count = cur.fetchone() or (0, 0)
            cur.execute("SELECT COALESCE(SUM(bytes_saved_est), 0) FROM file_operations")
            saved_bytes = int((cur.fetchone() or [0])[0] or 0)
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(size), 0) FROM quarantine_items WHERE status='quarantined'"
            )
            quarantine_count, quarantine_bytes = cur.fetchone() or (0, 0)
            cur.execute(
                """
                SELECT s.id, s.updated_at, s.status, s.progress_message, COUNT(DISTINCT r.group_key)
                FROM scan_sessions s
                LEFT JOIN scan_results r ON r.session_id = s.id
                GROUP BY s.id, s.updated_at, s.status, s.progress_message
                ORDER BY s.updated_at DESC
                LIMIT 10
                """
            )
            session_rows = cur.fetchall()
        except Exception:
            logger.exception("Failed to refresh insights page")
            return

        self.lbl_insight_scans_value.setText(f"{int(completed_sessions or 0)}/{int(total_sessions or 0)}")
        self.lbl_insight_savings_value.setText(self.format_size(int(saved_bytes or 0)))
        sample_size = max(1, int(fail_sample or 0))
        self.lbl_insight_fail_rate_value.setText(f"{(int(fail_count or 0) / sample_size) * 100:.0f}%")
        self.lbl_insight_quarantine_value.setText(
            f"{int(quarantine_count or 0)} / {self.format_size(int(quarantine_bytes or 0))}"
        )

        if hasattr(self, "tbl_insight_sessions"):
            self.tbl_insight_sessions.setRowCount(len(session_rows))
            for row_idx, row in enumerate(session_rows):
                updated = float(row[1] or 0.0)
                dt = datetime.fromtimestamp(updated).strftime("%Y-%m-%d %H:%M") if updated else "-"
                self.tbl_insight_sessions.setItem(row_idx, 0, QTableWidgetItem(str(int(row[0] or 0))))
                self.tbl_insight_sessions.setItem(row_idx, 1, QTableWidgetItem(dt))
                self.tbl_insight_sessions.setItem(row_idx, 2, QTableWidgetItem(str(row[2] or "")))
                self.tbl_insight_sessions.setItem(row_idx, 3, QTableWidgetItem(str(int(row[4] or 0))))
                fields = parse_structured_history_message(str(row[3] or ""))
                self.tbl_insight_sessions.setItem(row_idx, 4, QTableWidgetItem(fields.get("watch_events", "")))
                self.tbl_insight_sessions.setItem(row_idx, 5, QTableWidgetItem(str(row[3] or "")))

        if hasattr(self, "tbl_insight_jobs"):
            runs = self.cache_manager.list_scan_job_runs(limit=10)
            self.tbl_insight_jobs.setRowCount(len(runs))
            for row_idx, run in enumerate(runs):
                started = float(run.get("started_at") or 0.0)
                dt = datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M") if started else "-"
                self.tbl_insight_jobs.setItem(row_idx, 0, QTableWidgetItem(dt))
                self.tbl_insight_jobs.setItem(row_idx, 1, QTableWidgetItem(str(run.get("job_name") or "")))
                self.tbl_insight_jobs.setItem(row_idx, 2, QTableWidgetItem(str(run.get("status") or "")))
                self.tbl_insight_jobs.setItem(row_idx, 3, QTableWidgetItem(str(int(run.get("groups_count") or 0))))
                self.tbl_insight_jobs.setItem(row_idx, 4, QTableWidgetItem(str(int(run.get("files_count") or 0))))
                fields = parse_structured_history_message(str(run.get("message") or ""))
                self.tbl_insight_jobs.setItem(row_idx, 5, QTableWidgetItem(fields.get("missing_folders", "")))
                self.tbl_insight_jobs.setItem(row_idx, 6, QTableWidgetItem(fields.get("export_failed", "")))
                self.tbl_insight_jobs.setItem(row_idx, 7, QTableWidgetItem(fields.get("watch_events", "")))
                self.tbl_insight_jobs.setItem(row_idx, 8, QTableWidgetItem(str(run.get("message") or "")))

    def perform_post_cleanup_empty_dirs(self: Any, removed_paths):
        if not removed_paths:
            return
        try:
            enabled = bool(self.chk_post_cleanup_empty_dirs.isChecked()) if hasattr(self, "chk_post_cleanup_empty_dirs") else False
        except Exception:
            enabled = False
        if not enabled:
            return

        deleted, failed = cleanup_empty_parent_folders(
            removed_paths,
            stop_roots=list(self.selected_folders or []),
        )
        if not deleted and not failed:
            return

        try:
            op_id = self.cache_manager.create_operation(
                "empty_folder_cleanup",
                {"paths": list(removed_paths or []), "count": len(deleted)},
                status="running",
            )
            batch = [(path, "deleted_empty_dir", "ok", "", None, None, "") for path in deleted]
            batch.extend((path, "deleted_empty_dir", "fail", reason, None, None, "") for path, reason in failed)
            if op_id and batch:
                self.cache_manager.append_operation_items(op_id, batch)
                final_status = "partial" if failed and deleted else ("failed" if failed else "completed")
                self.cache_manager.finish_operation(
                    op_id,
                    final_status,
                    f"empty_folder_cleanup:{len(deleted)}",
                    bytes_total=0,
                    bytes_saved_est=0,
                )
        except Exception:
            logger.exception("Failed to log empty folder cleanup operation")

        try:
            self.refresh_operations_list()
            self.refresh_insights_page()
        except Exception:
            pass

        if deleted and hasattr(self, "toast_manager") and self.toast_manager:
            self.toast_manager.info(
                strings.tr("msg_empty_cleanup_done").format(count=len(deleted)),
                duration=2500,
            )

    def _apply_quarantine_retention(self: Any):
        """Best-effort retention policy application."""
        try:
            if hasattr(self, "chk_quarantine_enabled") and not self.chk_quarantine_enabled.isChecked():
                return
            days = self._to_int(self.settings.value("quarantine/max_days", 30), 30)
            max_bytes = self._to_int(self.settings.value("quarantine/max_bytes", 10 * 1024 * 1024 * 1024), 10 * 1024 * 1024 * 1024)
            purged = self.quarantine_manager.apply_retention(max_days=days, max_bytes=max_bytes)
            # Log retention purges as a purge operation (additive; no-op if DB insert fails).
            if purged:
                try:
                    op_id = self.cache_manager.create_operation("purge", {"retention": True, "count": len(purged)}, status="completed")
                    batch = []
                    for item_id in purged:
                        it = self.cache_manager.get_quarantine_item(int(item_id)) or {}
                        batch.append((it.get("orig_path") or "", "purged", "ok", "retention", it.get("size"), it.get("mtime"), it.get("quarantine_path") or ""))
                    if op_id and batch:
                        self.cache_manager.append_operation_items(op_id, batch)
                        self.cache_manager.finish_operation(op_id, "completed", f"Retention purged {len(purged)}", 0, 0)
                except Exception:
                    pass
            if purged and hasattr(self, "toast_manager") and self.toast_manager:
                self.toast_manager.info(strings.tr("msg_quarantine_purged").format(len(purged)), duration=2500)
        except Exception:
            pass

    def choose_quarantine_folder(self: Any):
        path = QFileDialog.getExistingDirectory(self, strings.tr("btn_choose_folder"), "")
        if not path:
            return
        self.txt_quarantine_path.setText(path)

    def apply_quarantine_settings(self: Any):
        try:
            enabled = bool(self.chk_quarantine_enabled.isChecked())
            days = int(self.spin_quarantine_days.value())
            gb = int(self.spin_quarantine_gb.value())
            override = str(self.txt_quarantine_path.text() or "").strip()

            self.settings.setValue("quarantine/enabled", enabled)
            self.settings.setValue("quarantine/max_days", days)
            self.settings.setValue("quarantine/max_bytes", gb * 1024 * 1024 * 1024)
            self.settings.setValue("quarantine/path_override", override)

            self.quarantine_manager._quarantine_dir = override or None
            self._apply_quarantine_retention()
            self.refresh_quarantine_list()
            if hasattr(self, "toast_manager") and self.toast_manager:
                self.toast_manager.info(strings.tr("msg_settings_applied"), duration=2000)
        except Exception as e:
            _mw().QMessageBox.warning(self, strings.tr("app_title"), str(e))

    def refresh_exemption_list(self: Any):
        if not hasattr(self, "tbl_exemptions"):
            return
        search = ""
        try:
            search = str(self.txt_exemption_search.text() or "").strip().lower()
        except Exception:
            search = ""
        items = self.cache_manager.list_scan_exemptions()
        if search:
            items = [
                item
                for item in items
                if search
                in " ".join(
                    [
                        str(item.get("kind") or ""),
                        str(item.get("value") or ""),
                        str(item.get("action") or ""),
                        str(item.get("note") or ""),
                    ]
                ).lower()
            ]
        self.tbl_exemptions.setRowCount(len(items))
        for row_idx, item in enumerate(items):
            created = float(item.get("created_at") or 0.0)
            dt = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M") if created else "-"
            id_item = QTableWidgetItem(str(int(item.get("id") or 0)))
            id_item.setData(Qt.ItemDataRole.UserRole, dict(item))
            self.tbl_exemptions.setItem(row_idx, 0, id_item)
            self.tbl_exemptions.setItem(row_idx, 1, QTableWidgetItem(str(item.get("kind") or "")))
            self.tbl_exemptions.setItem(row_idx, 2, QTableWidgetItem(str(item.get("value") or "")))
            self.tbl_exemptions.setItem(row_idx, 3, QTableWidgetItem(str(item.get("action") or "")))
            self.tbl_exemptions.setItem(row_idx, 4, QTableWidgetItem(str(item.get("note") or "")))
            self.tbl_exemptions.setItem(row_idx, 5, QTableWidgetItem(dt))

    def _selected_exemption_row(self: Any) -> dict:
        try:
            row = self.tbl_exemptions.currentRow()
            if row < 0:
                return {}
            item = self.tbl_exemptions.item(row, 0)
            return dict(item.data(Qt.ItemDataRole.UserRole) or {}) if item else {}
        except Exception:
            return {}

    def on_exemption_selection_changed(self: Any):
        item = self._selected_exemption_row()
        if not item:
            return
        try:
            idx = self.cmb_exemption_kind.findData(str(item.get("kind") or ""))
            self.cmb_exemption_kind.setCurrentIndex(idx if idx >= 0 else 0)
            idx = self.cmb_exemption_action.findData(str(item.get("action") or ""))
            self.cmb_exemption_action.setCurrentIndex(idx if idx >= 0 else 0)
            self.txt_exemption_value.setText(str(item.get("value") or ""))
            self.txt_exemption_note.setText(str(item.get("note") or ""))
        except Exception:
            pass

    def save_exemption_from_form(self: Any):
        try:
            kind = str(self.cmb_exemption_kind.currentData() or "")
            action = str(self.cmb_exemption_action.currentData() or "")
            value = str(self.txt_exemption_value.text() or "").strip()
            note = str(self.txt_exemption_note.text() or "").strip()
            if not kind or not action or not value:
                _mw().QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_items"))
                return
            self.cache_manager.add_scan_exemption(kind=kind, value=value, action=action, note=note)
            self.refresh_exemption_list()
            if hasattr(self, "toast_manager") and self.toast_manager:
                self.toast_manager.info(strings.tr("msg_rules_saved"), duration=1800)
        except Exception as e:
            _mw().QMessageBox.warning(self, strings.tr("app_title"), str(e))

    def delete_selected_exemption(self: Any):
        item = self._selected_exemption_row()
        if not item:
            return
        self.cache_manager.delete_scan_exemption(int(item.get("id") or 0))
        self.refresh_exemption_list()

    def _save_scan_exemption_rule(self: Any, *, kind: str, value: str, action: str, note: str = ""):
        if not kind or not value or not action:
            return
        self.cache_manager.add_scan_exemption(kind=kind, value=value, action=action, note=note)
        try:
            self.refresh_exemption_list()
        except Exception:
            pass
        if hasattr(self, "toast_manager") and self.toast_manager:
            self.toast_manager.info(strings.tr("msg_rules_saved"), duration=1800)

    def open_selection_rules_dialog(self: Any):
        dlg = SelectionRulesDialog(self.selection_rules_json, self)
        if dlg.exec():
            self.selection_rules_json = dlg.get_rules()
            self.selection_rules = parse_rules(self.selection_rules_json)
            try:
                self.settings.setValue("rules/selection_json", json.dumps(self.selection_rules_json))
            except Exception:
                pass
            if hasattr(self, "toast_manager") and self.toast_manager:
                self.toast_manager.info(strings.tr("msg_rules_saved"), duration=2000)

    def _parse_quarantine_date(self: Any, value: str, *, end_of_day: bool = False):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.strptime(text, "%Y-%m-%d")
            if end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59)
            return float(dt.timestamp())
        except Exception:
            return None

    def change_quarantine_page(self: Any, delta: int):
        current = int(getattr(self, "_quarantine_page", 0) or 0)
        self._quarantine_page = max(0, current + int(delta or 0))
        self.refresh_quarantine_list()

    def refresh_quarantine_list(self: Any, reset_page: bool = False):
        if not hasattr(self, "tbl_quarantine"):
            return
        if reset_page:
            self._quarantine_page = 0
        search = ""
        try:
            search = str(self.txt_quarantine_search.text() or "").strip()
        except Exception:
            search = ""
        status_filter = "quarantined"
        try:
            status_filter = str(self.cmb_quarantine_status.currentData() or "")
        except Exception:
            status_filter = "quarantined"
        size_min = None
        size_max = None
        try:
            raw = str(self.txt_quarantine_min_size.text() or "").strip()
            size_min = int(raw) if raw else None
        except Exception:
            size_min = None
        try:
            raw = str(self.txt_quarantine_max_size.text() or "").strip()
            size_max = int(raw) if raw else None
        except Exception:
            size_max = None
        created_from = None
        created_to = None
        try:
            created_from = self._parse_quarantine_date(str(self.txt_quarantine_date_from.text() or ""))
            created_to = self._parse_quarantine_date(str(self.txt_quarantine_date_to.text() or ""), end_of_day=True)
        except Exception:
            pass
        page_size = 50
        page = max(0, int(getattr(self, "_quarantine_page", 0) or 0))
        items = self.cache_manager.list_quarantine_items(
            limit=page_size + 1,
            offset=page * page_size,
            status_filter=status_filter or None,
            search=search,
            size_min=size_min,
            size_max=size_max,
            created_from=created_from,
            created_to=created_to,
        )
        has_next = len(items) > page_size
        items = items[:page_size]
        self.tbl_quarantine.setRowCount(len(items))
        from datetime import datetime

        for r, it in enumerate(items):
            item_id = int(it.get("id") or 0)
            created = it.get("created_at") or 0
            dt = datetime.fromtimestamp(float(created)).strftime("%Y-%m-%d %H:%M") if created else "-"

            i0 = QTableWidgetItem(it.get("orig_path") or "")
            i0.setData(Qt.ItemDataRole.UserRole, item_id)
            self.tbl_quarantine.setItem(r, 0, i0)

            i1 = QTableWidgetItem(self.format_size(int(it.get("size") or 0)))
            self.tbl_quarantine.setItem(r, 1, i1)

            i2 = QTableWidgetItem(dt)
            self.tbl_quarantine.setItem(r, 2, i2)

            i3 = QTableWidgetItem(it.get("status") or "")
            self.tbl_quarantine.setItem(r, 3, i3)
        if hasattr(self, "lbl_quarantine_page"):
            self.lbl_quarantine_page.setText(f"{page + 1}")
        if hasattr(self, "btn_quarantine_prev"):
            self.btn_quarantine_prev.setEnabled(page > 0)
        if hasattr(self, "btn_quarantine_next"):
            self.btn_quarantine_next.setEnabled(has_next)

    def _selected_quarantine_item_ids(self: Any) -> list:
        ids = []
        try:
            rows = {i.row() for i in self.tbl_quarantine.selectedIndexes()}
            for r in sorted(rows):
                it = self.tbl_quarantine.item(r, 0)
                if not it:
                    continue
                item_id = it.data(Qt.ItemDataRole.UserRole)
                if item_id:
                    ids.append(int(item_id))
        except Exception:
            pass
        return ids

    def restore_selected_quarantine(self: Any):
        item_ids = self._selected_quarantine_item_ids()
        if not item_ids:
            return
        items = [self.cache_manager.get_quarantine_item(i) for i in item_ids]
        items = [i for i in items if i]
        rep = self.preflight_analyzer.analyze_restore(items)
        dlg = PreflightDialog(rep, self)
        if not dlg.exec():
            return
        if not dlg.can_proceed:
            return
        self._start_operation(Operation("restore", options={"item_ids": item_ids}))

    def purge_selected_quarantine(self: Any):
        item_ids = self._selected_quarantine_item_ids()
        if not item_ids:
            return
        items = [self.cache_manager.get_quarantine_item(i) for i in item_ids]
        items = [i for i in items if i]
        rep = self.preflight_analyzer.analyze_purge(items)
        dlg = PreflightDialog(rep, self)
        if not dlg.exec():
            return
        if not dlg.can_proceed:
            return
        res = _mw().QMessageBox.warning(
            self,
            strings.tr("confirm_delete_title"),
            strings.tr("confirm_purge_items").format(len(item_ids)),
            _mw().QMessageBox.StandardButton.Yes | _mw().QMessageBox.StandardButton.No,
        )
        if res != _mw().QMessageBox.StandardButton.Yes:
            return
        self._start_operation(Operation("purge", options={"item_ids": item_ids}))

    def purge_all_quarantine(self: Any):
        items = self.cache_manager.list_quarantine_items(limit=5000, offset=0, status_filter="quarantined")
        item_ids = [int(i.get("id") or 0) for i in items if i]
        if not item_ids:
            return
        rep = self.preflight_analyzer.analyze_purge(items)
        dlg_pf = PreflightDialog(rep, self)
        if not dlg_pf.exec():
            return
        if not dlg_pf.can_proceed:
            return
        res = _mw().QMessageBox.warning(
            self,
            strings.tr("confirm_delete_title"),
            strings.tr("confirm_purge_all").format(len(item_ids)),
            _mw().QMessageBox.StandardButton.Yes | _mw().QMessageBox.StandardButton.No,
        )
        if res != _mw().QMessageBox.StandardButton.Yes:
            return
        self._start_operation(Operation("purge", options={"item_ids": item_ids}))

    def refresh_operations_list(self: Any):
        if not hasattr(self, "tbl_ops"):
            return
        ops = self.cache_manager.list_operations(limit=200, offset=0)
        from datetime import datetime

        self.tbl_ops.setRowCount(len(ops))
        for r, op in enumerate(ops):
            op_id = int(op.get("id") or 0)
            created = op.get("created_at") or 0
            dt = datetime.fromtimestamp(float(created)).strftime("%Y-%m-%d %H:%M") if created else "-"

            i0 = QTableWidgetItem(str(op_id))
            try:
                raw_options = str(op.get("options_json") or "").strip()
                op["options"] = json.loads(raw_options) if raw_options else {}
            except Exception:
                op["options"] = {}
            i0.setData(Qt.ItemDataRole.UserRole, op)
            self.tbl_ops.setItem(r, 0, i0)
            self.tbl_ops.setItem(r, 1, QTableWidgetItem(dt))
            self.tbl_ops.setItem(r, 2, QTableWidgetItem(str(op.get("op_type") or "")))
            self.tbl_ops.setItem(r, 3, QTableWidgetItem(str(op.get("status") or "")))
            self.tbl_ops.setItem(r, 4, QTableWidgetItem(str(op.get("message") or "")))

    def _selected_operation_row(self: Any) -> dict:
        try:
            row = self.tbl_ops.currentRow()
            if row < 0:
                return {}
            it = self.tbl_ops.item(row, 0)
            if not it:
                return {}
            data = it.data(Qt.ItemDataRole.UserRole)
            return data or {}
        except Exception:
            return {}

    def view_selected_operation(self: Any):
        op = self._selected_operation_row()
        if not op:
            return
        dlg = OperationLogDialog(self.cache_manager, op, self)
        if str(op.get("op_type") or "") == "hardlink_consolidate":
            dlg.btn_undo_hardlink.clicked.connect(lambda: self._undo_hardlink_from_operation(op, dlg))
        if dlg.exec():
            payload = getattr(dlg, "retry_payload", None)
            if payload and isinstance(payload, dict):
                op_type = str(payload.get("op_type") or "")
                paths = list(payload.get("paths") or [])
                options = dict(payload.get("options") or {})
                self._start_operation(Operation(op_type, paths=paths, options=options))

    def _undo_hardlink_from_operation(self: Any, op: dict, dlg: OperationLogDialog):
        # Collect quarantine item ids created by the operation.
        op_id = int(op.get("id") or 0)
        items = self.cache_manager.get_operation_items(op_id)
        item_ids = []
        canonical = None
        for it in items:
            if it.get("action") != "hardlinked" or it.get("result") != "ok":
                continue
            canonical = canonical or (it.get("detail") or None)
            qpath = it.get("quarantine_path") or ""
            if not qpath:
                continue
            qitem = self.cache_manager.get_quarantine_item_by_path(qpath)
            if qitem and qitem.get("status") == "quarantined":
                item_ids.append(int(qitem.get("id") or 0))
        item_ids = [i for i in item_ids if i]
        if not item_ids or not canonical:
            _mw().QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_items"))
            return

        qitems = [self.cache_manager.get_quarantine_item(i) for i in item_ids]
        qitems = [i for i in qitems if i]
        rep = self.preflight_analyzer.analyze_restore(qitems)
        # We'll replace existing hardlinks to canonical when restoring.
        rep.meta["allow_replace_hardlink_to"] = canonical
        dlg_pf = PreflightDialog(rep, self)
        if not dlg_pf.exec():
            return
        if not dlg_pf.can_proceed:
            return
        self._start_operation(Operation("restore", options={"item_ids": item_ids, "allow_replace_hardlink_to": canonical}))
        try:
            dlg.close()
        except Exception:
            pass

    def select_duplicates_by_rules(self: Any):
        if not self.scan_results:
            return
        rules = self.selection_rules or []
        if not rules:
            _mw().QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_rules"))
            return

        root = self.tree_widget.invisibleRootItem()
        self.tree_widget.begin_bulk_check_update()
        try:
            for i in range(root.childCount()):
                group = root.child(i)
                entries = [e for e, _ in self._group_entries_with_items(group)]
                decision = self.results_controller.build_selection_decision(entries, strategy="smart", rules=rules)
                keep_set = set(decision.keep_set or [])
                self._remember_selection_reasons(decision)
                for j in range(group.childCount()):
                    child = group.child(j)
                    p = child.data(0, Qt.ItemDataRole.UserRole)
                    if not p:
                        continue
                    child.setCheckState(0, Qt.CheckState.Unchecked if p in keep_set else Qt.CheckState.Checked)
        finally:
            self.tree_widget.end_bulk_check_update()

    def _is_group_key_hardlink_eligible(self: Any, key) -> bool:
        try:
            return bool(classify_result_group(key).hardlink_eligible)
        except Exception:
            return False

    def hardlink_consolidate_checked(self: Any):
        # Build per-group operations based on checked files (targets) and unchecked (canonical).
        try:
            enabled = bool(self.chk_enable_hardlink.isChecked())
        except Exception:
            enabled = False
        if not enabled:
            _mw().QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_hardlink_disabled"))
            return

        root = self.tree_widget.invisibleRootItem()
        ops = []
        issues = []
        total_targets = 0
        for i in range(root.childCount()):
            group = root.child(i)
            key = group.data(0, Qt.ItemDataRole.UserRole + 1)
            if not self._is_group_key_hardlink_eligible(key):
                continue

            checked = []
            unchecked = []
            for j in range(group.childCount()):
                child = group.child(j)
                p = child.data(0, Qt.ItemDataRole.UserRole)
                if not p:
                    continue
                if child.checkState(0) == Qt.CheckState.Checked:
                    checked.append(p)
                else:
                    unchecked.append(p)
            if not checked or not unchecked:
                continue

            canonical = unchecked[0]
            targets = list(checked)
            total_targets += len(targets)
            rep = self.preflight_analyzer.analyze_hardlink(canonical, targets)
            issues.extend(list(rep.issues or []))
            if rep.has_blockers:
                dlg = PreflightDialog(rep, self)
                dlg.exec()
                return
            ops.append(Operation("hardlink_consolidate", options={"canonical": canonical, "targets": targets}))

        if not ops:
            _mw().QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_items"))
            return

        # Show an aggregate preflight dialog if there are warnings.
        try:
            from src.core.preflight import PreflightReport

            agg = PreflightReport(op_type="hardlink_consolidate", issues=issues)
            agg.meta["eligible_count"] = int(total_targets)
            dlg = PreflightDialog(agg, self)
            if not dlg.exec():
                return
            if not dlg.can_proceed:
                return
        except Exception:
            pass

        self._enqueue_operations(ops)

    def _enqueue_operations(self: Any, ops: list):
        self.operation_flow_controller.enqueue_operations(self, ops)

    def _start_next_operation(self: Any):
        self.operation_flow_controller.start_next_operation(self)

    def _start_operation(self: Any, op: Operation, allow_queue_continue: bool = False):
        self.operation_flow_controller.start_operation(self, op, allow_queue_continue=allow_queue_continue)

    def _cancel_operation(self: Any):
        self.operation_flow_controller.cancel_operation(self)

    def _on_op_progress(self: Any, val: int, msg: str):
        self.operation_flow_controller.on_progress(self, val, msg)

    def _on_op_finished(self: Any, result, allow_queue_continue: bool):
        self.operation_flow_controller.on_finished(self, result, allow_queue_continue)
