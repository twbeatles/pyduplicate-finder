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
from src.core.quarantine_manager import QuarantineManager
from src.core.preflight import PreflightAnalyzer
from src.core.selection_rules import parse_rules
from src.core.operation_queue import Operation
from src.core.scan_engine import ScanConfig, validate_similar_image_dependency
from src.core.result_schema import dump_results_v2, load_results_any
from src.core.scheduler import ScheduleConfig
from src.ui.empty_folder_dialog import EmptyFolderDialog
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

    def refresh_quarantine_list(self: Any):
        if not hasattr(self, "tbl_quarantine"):
            return
        search = ""
        try:
            search = str(self.txt_quarantine_search.text() or "").strip()
        except Exception:
            search = ""
        items = self.cache_manager.list_quarantine_items(limit=200, offset=0, status_filter="quarantined", search=search)
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
                paths = self.tree_widget.get_group_paths(group)
                keep_set, _delete_set = self.results_controller.build_keep_delete_by_rules(paths, rules)
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
            if isinstance(key, (tuple, list)) and key:
                if key[0] == "NAME_ONLY":
                    return False
                for part in key:
                    if isinstance(part, str) and part.startswith("similar_"):
                        return False
            return True
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
