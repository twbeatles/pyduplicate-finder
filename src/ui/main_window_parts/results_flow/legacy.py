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
from src.core.result_schema import dump_results_v3, load_file_state_map, load_results_bundle_any
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
from src.ui.dialogs.session_compare_dialog import SessionCompareDialog
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



class MainWindowResultsFlowMixin(DuplicateFinderTypingContract):
    def populate_tree(self: Any, results):
        self._render_results(results, selected_paths=[])

    def format_size(self: Any, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024: return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def open_file(self: Any, item, column):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            if platform.system() == 'Windows':
                os.startfile(path)
            elif platform.system() == 'Darwin':
                subprocess.call(('open', path))
            else:
                subprocess.call(('xdg-open', path))

    def export_results(self: Any):
        if not self.scan_results:
            _mw().QMessageBox.warning(self, strings.tr("app_title"), strings.tr("msg_no_results"))
            return

        path, _ = QFileDialog.getSaveFileName(self, strings.tr("btn_export"), "duplicates.csv", "CSV Files (*.csv)")
        if not path: return

        try:
            from src.ui.exporting import export_scan_results_csv

            try:
                selected = self.tree_widget.get_checked_files()
            except Exception:
                selected = []

            export_scan_results_csv(
                scan_results=self.scan_results,
                out_path=path,
                selected_paths=selected,
                file_meta=self._current_result_meta,
                baseline_delta_map=self._current_baseline_delta_map,
                selection_reason_map=self._current_selection_reason_map,
                exemption_status_map=self._current_exemption_status_map,
                review_state_map=self._current_review_state_map,
                collection_role_map=self._current_collection_role_map,
            )
            _mw().QMessageBox.information(self, strings.tr("status_done"), strings.tr("status_done") + f":\n{path}")
        except Exception as e:
            _mw().QMessageBox.critical(self, strings.tr("app_title"), strings.tr("err_save").format(e))

    def _group_entries_with_items(self: Any, group):
        entries = []
        for j in range(group.childCount()):
            item = group.child(j)
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if not path:
                continue
            path = str(path)
            mtime = 0.0
            try:
                mtime = float(item.data(2, Qt.ItemDataRole.UserRole) or 0.0)
            except Exception:
                pass
            if not mtime:
                try:
                    mtime = float((self._current_result_meta.get(path) or (0, 0.0))[1] or 0.0)
                except Exception:
                    mtime = 0.0
            entries.append(
                (
                    ResultEntry(
                        path=path,
                        mtime=mtime,
                        extension=os.path.splitext(path)[1].lower().lstrip("."),
                        collection_role=str((self._current_collection_role_map or {}).get(path) or ""),
                        explicit_keep=False,
                        explicit_delete=False,
                        safelisted=str((self._current_exemption_status_map or {}).get(path) or "") == "safelisted",
                        readonly=not os.access(path, os.W_OK) if os.path.exists(path) else False,
                    ),
                    item,
                )
            )
        return entries

    def _remember_selection_reasons(self: Any, decision):
        reasons = dict(getattr(decision, "reasons", {}) or {})
        if not reasons:
            return
        self._current_selection_reason_map.update(reasons)

    def _set_review_state(self: Any, paths, state: str):
        values = [str(p) for p in (paths or []) if p]
        if not values:
            return
        for path in values:
            if state:
                self._current_review_state_map[path] = state
            else:
                self._current_review_state_map.pop(path, None)
            if not self.current_session_id:
                continue
            try:
                if state:
                    self.cache_manager.save_review_mark(
                        int(self.current_session_id),
                        target_type="file",
                        target_key=path,
                        state=state,
                    )
                else:
                    self.cache_manager.clear_review_mark(
                        int(self.current_session_id),
                        target_type="file",
                        target_key=path,
                    )
            except Exception:
                pass
        self.status_label.setText(strings.tr("status_done"))

    def _apply_keep_set_to_group(self: Any, group, keep_set: set[str]):
        for _entry, item in self._group_entries_with_items(group):
            p = item.data(0, Qt.ItemDataRole.UserRole)
            if not p:
                continue
            item.setCheckState(0, Qt.CheckState.Unchecked if str(p) in keep_set else Qt.CheckState.Checked)

    def _mtime_for_path(self: Any, path: str) -> float:
        try:
            meta = self._current_result_meta.get(str(path))
            if meta and len(meta) >= 2:
                return float(meta[1] or 0.0)
        except Exception:
            pass
        return 0.0

    def select_duplicates_smart(self: Any):
        root = self.tree_widget.invisibleRootItem()
        self.tree_widget.begin_bulk_check_update()
        try:
            for i in range(root.childCount()):
                group = root.child(i)
                entries = [e for e, _ in self._group_entries_with_items(group)]
                decision = self.results_controller.build_selection_decision(entries, strategy="smart")
                self._remember_selection_reasons(decision)
                self._apply_keep_set_to_group(group, decision.keep_set)
        finally:
            self.tree_widget.end_bulk_check_update()

    def select_duplicates_newest(self: Any):
        """Keep Oldest, Select Newest (Date based)"""
        root = self.tree_widget.invisibleRootItem()
        self.tree_widget.begin_bulk_check_update()
        try:
            for i in range(root.childCount()):
                group = root.child(i)
                entries = [e for e, _ in self._group_entries_with_items(group)]
                decision = self.results_controller.build_selection_decision(entries, strategy="oldest")
                self._remember_selection_reasons(decision)
                self._apply_keep_set_to_group(group, decision.keep_set)
        finally:
            self.tree_widget.end_bulk_check_update()

    def select_duplicates_oldest(self: Any):
        """Keep Newest, Select Oldest (Date based)"""
        root = self.tree_widget.invisibleRootItem()
        self.tree_widget.begin_bulk_check_update()
        try:
            for i in range(root.childCount()):
                group = root.child(i)
                entries = [e for e, _ in self._group_entries_with_items(group)]
                decision = self.results_controller.build_selection_decision(entries, strategy="newest")
                self._remember_selection_reasons(decision)
                self._apply_keep_set_to_group(group, decision.keep_set)
        finally:
            self.tree_widget.end_bulk_check_update()

    def select_duplicates_by_pattern(self: Any):
        """Select files matching a text pattern"""
        text, ok = QInputDialog.getText(self, strings.tr("ctx_select_pattern_title"), 
                                      strings.tr("ctx_select_pattern_msg"))
        if not ok or not text: return
        
        pattern = text.lower()
        root = self.tree_widget.invisibleRootItem()
        
        count = 0
        self.tree_widget.begin_bulk_check_update()
        try:
            for i in range(root.childCount()):
                group = root.child(i)
                for j in range(group.childCount()):
                    item = group.child(j)
                    path = item.data(0, Qt.ItemDataRole.UserRole) or ""
                    path = path.lower()
                    if pattern in path:
                        item.setCheckState(0, Qt.CheckState.Checked)
                        count += 1
        finally:
            self.tree_widget.end_bulk_check_update()
        
        self.status_label.setText(
            strings.tr("msg_selected_pattern").format(count=count, pattern=text)
        )

    def on_result_filter_text_changed(self: Any, text):
        self._pending_filter_text = str(text or "")
        self._result_filter_timer.start(120)

    def _apply_result_filter(self: Any):
        self.filter_results_tree(self._pending_filter_text)

    def filter_results_tree(self: Any, text):
        """Filter the result tree by filename/path."""
        delta_filter = ""
        if hasattr(self, "cmb_delta_filter"):
            try:
                delta_filter = str(self.cmb_delta_filter.currentData() or "")
            except Exception:
                delta_filter = ""
        visible_files, total_files = self.tree_widget.apply_filter(text, delta_filter=delta_filter)
        if hasattr(self, "lbl_filter_count"):
            if total_files == 0:
                self.lbl_filter_count.setText("")
            else:
                self.lbl_filter_count.setText(
                    strings.tr("msg_filter_count").format(visible=visible_files, total=total_files)
                )
        if hasattr(self, "btn_session_compare"):
            self.btn_session_compare.setEnabled(bool(self._current_baseline_delta_map))
        try:
            self._update_action_buttons_state()
        except Exception:
            pass

        try:
            self.refresh_incremental_baselines()
        except Exception:
            pass

    def _render_results(
        self,
        results,
        *,
        selected_paths=None,
        file_meta=None,
        existence_map=None,
        selected_count: int | None = None,
    ):
        selected = list(selected_paths or [])
        self._current_result_meta = dict(file_meta or {})
        self._current_result_existence_map = dict(existence_map or {})
        self.tree_widget.populate(
            results,
            selected_paths=selected,
            file_meta=self._current_result_meta,
            existence_map=self._current_result_existence_map,
            baseline_delta_map=self._current_baseline_delta_map,
        )
        self._saved_selected_paths = set(selected)
        self._pending_selected_add.clear()
        self._pending_selected_remove.clear()
        self._pending_filter_text = self.txt_result_filter.text() if hasattr(self, "txt_result_filter") else ""
        self.filter_results_tree(self._pending_filter_text)
        self._set_results_view(bool(results))
        if selected_count is None:
            selected_count = len(selected)
        self._update_results_summary(selected_count)
        self._update_action_buttons_state(selected_count=selected_count)

    def open_session_compare_dialog(self: Any):
        delta_map = dict(self._current_baseline_delta_map or {})
        if not delta_map:
            _mw().QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_session_compare_empty"))
            return
        baseline_session_id = 0
        try:
            baseline_session_id = int((self._last_incremental_stats or {}).get("base_session_id") or 0)
        except Exception:
            baseline_session_id = 0
        dlg = SessionCompareDialog(
            current_session_id=int(self.current_session_id or 0),
            baseline_session_id=baseline_session_id,
            delta_map=delta_map,
            parent=self,
        )
        dlg.exec()

    def delete_selected_files(self: Any):
        targets = []
        filter_active = bool(self.txt_result_filter.text().strip())
        visible_checked = 0
        group_rows = []

        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            group_sel = 0
            group_bytes = 0
            for j in range(group.childCount()):
                item = group.child(j)
                if item.checkState(0) == Qt.CheckState.Checked:
                    targets.append(item.data(0, Qt.ItemDataRole.UserRole))
                    group_sel += 1
                    try:
                        group_bytes += int(item.data(1, Qt.ItemDataRole.UserRole) or 0)
                    except Exception:
                        pass
                    if not item.isHidden():
                        visible_checked += 1
            if group_sel > 0:
                group_rows.append((group.text(0), group_sel, group_bytes))

        if not targets:
            _mw().QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_files_selected"))
            return

        # Check file locks before delete
        locked_files = self.file_lock_checker.get_locked_files(targets)
        if locked_files:
            locked_list = "\n".join(locked_files[:5])
            if len(locked_files) > 5:
                locked_list += f"\n... and {len(locked_files) - 5} more"
            _mw().QMessageBox.warning(
                self, strings.tr("app_title"),
                f"{strings.tr('msg_file_locked')}\n\n{locked_list}"
            )
            # Exclude locked targets
            targets = [t for t in targets if t not in locked_files]
            if not targets:
                return

        # Execute delete operation
        use_trash = self.chk_use_trash.isChecked()

        # Use persistent quarantine for undoable deletes if enabled.
        quarantine_enabled = str(self.settings.value("quarantine/enabled", True)).lower() == "true"
        if use_trash:
            op_type = "delete_trash"
        else:
            op_type = "delete_quarantine" if quarantine_enabled else "delete_trash"
            if not quarantine_enabled:
                _mw().QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_quarantine_disabled_fallback"))

        # Dry-run simulation summary before destructive flow.
        self._show_delete_dry_run(group_rows, total_selected=len(targets), visible_checked=visible_checked, filter_active=filter_active)

        # Preflight dialog is the confirmation surface; include filter warning in status bar/toast.
        if filter_active:
            try:
                self.status_label.setText(
                    strings.tr("confirm_delete_selected_counts").format(total=len(targets), visible=visible_checked)
                )
            except Exception:
                pass

        self._start_operation(
            Operation(
                op_type,
                paths=targets,
                options={"filter_active": filter_active, "visible_checked": visible_checked},
            )
        )

    def _show_delete_dry_run(self: Any, group_rows, *, total_selected: int, visible_checked: int, filter_active: bool):
        try:
            total_bytes = 0
            for _name, _count, b in (group_rows or []):
                total_bytes += int(b or 0)

            lines = [
                strings.tr("msg_delete_dry_run_summary").format(
                    total=int(total_selected or 0),
                    visible=int(visible_checked or 0),
                    size=self.format_size(int(total_bytes or 0)),
                )
            ]
            if filter_active:
                lines.append(strings.tr("msg_delete_includes_hidden"))

            limit = 8
            for idx, (name, count, bytes_total) in enumerate(group_rows[:limit]):
                lines.append(
                    strings.tr("msg_delete_dry_run_group_line").format(
                        idx=idx + 1,
                        count=int(count or 0),
                        size=self.format_size(int(bytes_total or 0)),
                        name=str(name or ""),
                    )
                )
            if len(group_rows) > limit:
                lines.append(strings.tr("msg_delete_dry_run_more").format(count=len(group_rows) - limit))

            _mw().QMessageBox.information(
                self,
                strings.tr("msg_delete_dry_run_title"),
                "\n".join(lines),
            )
        except Exception:
            pass

    def perform_undo(self: Any):
        self._start_operation(Operation("undo"))

    def perform_redo(self: Any):
        self._start_operation(Operation("redo"))

    def _remove_paths_from_results(self: Any, deleted_paths):
        """Issue #13: Remove deleted paths from scan_results dict."""
        if not self.scan_results or not deleted_paths:
            return
        
        keys_to_remove = []
        for key, paths in self.scan_results.items():
            # Remove deleted paths from this group
            remaining = [p for p in paths if p not in deleted_paths]
            if len(remaining) < 2:
                # No duplicates left in this group
                keys_to_remove.append(key)
            else:
                self.scan_results[key] = remaining
        
        for key in keys_to_remove:
            del self.scan_results[key]

        self._set_results_view(bool(self.scan_results))
        self._update_results_summary()

    def _prune_missing_results(self: Any):
        """Remove missing files from current scan_results. Returns True if changed."""
        if not self.scan_results:
            return False
        missing_paths = set()
        for paths in self.scan_results.values():
            for path in paths:
                if not os.path.exists(path):
                    missing_paths.add(path)

        if not missing_paths:
            return False
        self._remove_paths_from_results(missing_paths)
        return True

    def _prune_missing_results_after_restore(self: Any):
        if not self.current_session_id or not self.scan_results:
            return
        if not self._prune_missing_results():
            return
        selected_paths = [p for p in self._saved_selected_paths if os.path.exists(p)]
        self._render_results(self.scan_results, selected_paths=selected_paths, selected_count=len(selected_paths))
        self.cache_manager.save_scan_results(self.current_session_id, self.scan_results)
        self.cache_manager.save_selected_paths(self.current_session_id, selected_paths)

    def update_undo_redo_buttons(self: Any):
        self.action_undo.setEnabled(bool(self.history_manager.undo_stack))
        self.action_redo.setEnabled(bool(self.history_manager.redo_stack))

    def update_preview(self: Any, current, previous):
        if not current:
            return

        path = current.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            self.show_preview_info(strings.tr("msg_select_file"))
            return

        path = str(path)
        self._preview_request_id += 1
        request_id = int(self._preview_request_id)

        self._set_preview_info(path)
        self.show_preview_info(strings.tr("status_analyzing"), keep_info=True)

        try:
            self.preview_controller.request_preview(path, request_id)
        except Exception:
            self.show_preview_info(strings.tr("msg_preview_unavailable"), keep_info=True)

    def _on_preview_ready(self: Any, payload):
        try:
            req_id = int((payload or {}).get("request_id") or 0)
        except Exception:
            req_id = 0
        if req_id != int(getattr(self, "_preview_request_id", 0)):
            return

        path = str((payload or {}).get("path") or "")
        kind = str((payload or {}).get("kind") or "info")
        size = (payload or {}).get("size")
        mtime = (payload or {}).get("mtime")

        if kind == "folder":
            self._set_preview_info(path, is_folder=True, size=size, mtime=mtime)
            self.show_preview_info(strings.tr("msg_preview_folder_hint"), keep_info=True)
            return

        if kind == "image":
            image = (payload or {}).get("image")
            if image is not None:
                pixmap = QPixmap.fromImage(image)
                if not pixmap.isNull():
                    self._set_preview_info(path, size=size, mtime=mtime)
                    scaled = pixmap.scaled(
                        self.lbl_image_preview.size().boundedTo(QSize(400, 400)),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self.lbl_image_preview.setPixmap(scaled)
                    self.lbl_image_preview.show()
                    self.txt_text_preview.hide()
                    self.lbl_info_preview.hide()
                    return

        if kind == "text":
            content = str((payload or {}).get("text") or "")
            self._set_preview_info(path, size=size, mtime=mtime)
            self.txt_text_preview.setPlainText(content)
            font = QFont("Consolas")
            font.setStyleHint(QFont.StyleHint.Monospace)
            font.setPointSize(10)
            self.txt_text_preview.setFont(font)
            self.txt_text_preview.show()
            self.lbl_image_preview.hide()
            self.lbl_info_preview.hide()
            return

        self._set_preview_info(path, size=size, mtime=mtime)
        self.show_preview_info(strings.tr("msg_preview_unavailable"), keep_info=True)

    def show_preview_info(self: Any, msg, keep_info=False):
        self.lbl_image_preview.hide()
        self.txt_text_preview.hide()
        self.lbl_info_preview.setText(msg)
        self.lbl_info_preview.show()
        if keep_info:
            self.preview_info.show()
        else:
            self.preview_info.hide()

    def _set_preview_info(self: Any, path, is_folder=False, size=None, mtime=None):
        name = os.path.basename(path) or path
        self.lbl_preview_name.setText(name)
        self.lbl_preview_path.setText(path)

        if is_folder:
            self.lbl_preview_meta.setText(strings.tr("msg_preview_meta_folder"))
            self.preview_info.show()
            return

        size_str = strings.tr("msg_preview_meta_unknown")
        mtime_str = strings.tr("msg_preview_meta_unknown")

        size_val = size
        mtime_val = mtime

        if size_val is None or mtime_val is None:
            try:
                meta = self._current_result_meta.get(path)
                if meta and len(meta) >= 2:
                    if size_val is None:
                        size_val = int(meta[0] or 0)
                    if mtime_val is None:
                        mtime_val = float(meta[1] or 0.0)
            except Exception:
                pass

        if size_val is None:
            try:
                size_val = int(os.path.getsize(path))
            except Exception:
                size_val = None

        if mtime_val is None:
            try:
                mtime_val = float(os.path.getmtime(path))
            except Exception:
                mtime_val = None

        if size_val is not None:
            try:
                size_str = self.format_size(int(size_val))
            except Exception:
                pass

        if mtime_val is not None:
            try:
                mtime_str = datetime.fromtimestamp(float(mtime_val)).strftime('%Y-%m-%d %H:%M')
            except Exception:
                pass

        self.lbl_preview_meta.setText(strings.tr("msg_preview_meta").format(size=size_str, mtime=mtime_str))
        self.preview_info.show()

    def on_checked_files_changed(self: Any, paths):
        """Backward-compatible full-list handler."""
        new_set = set(paths or [])
        added = sorted(new_set - self._saved_selected_paths)
        removed = sorted(self._saved_selected_paths - new_set)
        self.on_checked_files_delta(added, removed, len(new_set), full_snapshot=new_set)

    def on_checked_files_delta(self: Any, added, removed, selected_count: int, full_snapshot=None):
        self._update_results_summary(int(selected_count or 0))
        self._update_action_buttons_state(selected_count=int(selected_count or 0))
        if not self.current_session_id:
            if full_snapshot is not None:
                self._saved_selected_paths = set(full_snapshot or set())
            else:
                if added:
                    self._saved_selected_paths.update(set(added))
                if removed:
                    self._saved_selected_paths.difference_update(set(removed))
            return

        add_set = set(added or [])
        remove_set = set(removed or [])
        if full_snapshot is not None:
            self._saved_selected_paths = set(full_snapshot or set())
        else:
            if add_set:
                self._saved_selected_paths.update(add_set)
            if remove_set:
                self._saved_selected_paths.difference_update(remove_set)

        if add_set:
            self._pending_selected_add.update(add_set)
            self._pending_selected_remove.difference_update(add_set)
        if remove_set:
            self._pending_selected_remove.update(remove_set)
            self._pending_selected_add.difference_update(remove_set)

        self._selection_save_timer.start(220)

    def _flush_selected_paths(self: Any):
        if not self.current_session_id:
            return
        if not self._pending_selected_add and not self._pending_selected_remove:
            return
        self.cache_manager.save_selected_paths_delta(
            self.current_session_id,
            add_paths=list(self._pending_selected_add),
            remove_paths=list(self._pending_selected_remove),
        )
        self._pending_selected_add.clear()
        self._pending_selected_remove.clear()

    def _set_results_view(self: Any, has_results: bool):
        if not hasattr(self, "results_stack"):
            return
        self.results_stack.setCurrentIndex(1 if has_results else 0)

    def _update_results_summary(self: Any, selected_count: int | None = None):
        if not hasattr(self, "lbl_results_meta"):
            return
        groups = len(self.scan_results) if self.scan_results else 0
        files = sum(len(paths) for paths in self.scan_results.values()) if self.scan_results else 0
        if selected_count is None:
            selected_count = len(self.tree_widget.get_checked_files()) if groups else 0
        summary = strings.tr("msg_results_summary").format(groups=groups, files=files, selected=selected_count)
        self.lbl_results_meta.setText(summary)

        # Scan page: show last summary + enable CTA when results exist.
        if hasattr(self, "lbl_scan_summary"):
            self.lbl_scan_summary.setText(summary if groups else "")
        if hasattr(self, "btn_go_results"):
            self.btn_go_results.setEnabled(bool(groups))

    def _update_action_buttons_state(self: Any, selected_count: int | None = None):
        """Enable/disable actions/buttons based on current state for better UX."""
        if selected_count is None:
            try:
                selected_count = len(self.tree_widget.get_checked_files())
            except Exception:
                selected_count = 0

        has_results = bool(self.scan_results)
        is_scanning = bool(getattr(self, "btn_stop_scan", None) and self.btn_stop_scan.isEnabled())
        is_interactive = not is_scanning

        if hasattr(self, "btn_delete"):
            self.btn_delete.setEnabled(is_interactive and selected_count > 0)
            base = strings.tr("btn_delete_selected")
            self.btn_delete.setText(f"{base} ({selected_count})" if selected_count > 0 else base)
        if hasattr(self, "btn_export"):
            self.btn_export.setEnabled(is_interactive and has_results)
        if hasattr(self, "btn_select_smart"):
            self.btn_select_smart.setEnabled(is_interactive and has_results)
        if hasattr(self, "btn_select_rules"):
            self.btn_select_rules.setEnabled(is_interactive and has_results and bool(self.selection_rules))

        if hasattr(self, "lbl_action_meta"):
            parts = [strings.tr("msg_selected_count").format(count=selected_count)]
            if hasattr(self, "txt_result_filter") and self.txt_result_filter.text().strip():
                parts.append(strings.tr("msg_filter_active"))
            self.lbl_action_meta.setText("  |  ".join(parts) if parts else "")

    def show_context_menu(self: Any, position):
        item = self.tree_widget.itemAt(position)
        if not item: return
        
        path = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu()

        # File item context (path is stored on leaf items).
        if path:
            path = str(path)
            action_open = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), strings.tr("ctx_open"), self)
            action_open.setEnabled(os.path.exists(path) and os.path.isfile(path))
            action_open.triggered.connect(lambda: self.open_file(item, 0))
            menu.addAction(action_open)

            folder = os.path.dirname(path)
            action_folder = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), strings.tr("ctx_open_folder"), self)
            action_folder.setEnabled(bool(folder) and os.path.isdir(folder))
            action_folder.triggered.connect(lambda: self.open_containing_folder(path))
            menu.addAction(action_folder)

            menu.addSeparator()

            action_copy = QAction(strings.tr("ctx_copy_path"), self)
            action_copy.triggered.connect(lambda: self.copy_to_clipboard(path))
            menu.addAction(action_copy)

            menu.addSeparator()
            action_review_keep = QAction(strings.tr("ctx_review_keep"), self)
            action_review_keep.triggered.connect(
                lambda: self._set_review_state([path], "reviewed_keep")
            )
            menu.addAction(action_review_keep)

            action_review_delete = QAction(strings.tr("ctx_review_delete_later"), self)
            action_review_delete.triggered.connect(
                lambda: self._set_review_state([path], "reviewed_delete_later")
            )
            menu.addAction(action_review_delete)

            action_review_clear = QAction(strings.tr("ctx_review_clear"), self)
            action_review_clear.triggered.connect(lambda: self._set_review_state([path], ""))
            menu.addAction(action_review_clear)

        else:
            # Group item context
            if item.childCount() <= 0:
                return
            key = item.data(0, Qt.ItemDataRole.UserRole + 1)

            act_check_all = QAction(strings.tr("ctx_group_check_all"), self)
            act_check_all.triggered.connect(lambda: self.tree_widget.set_group_checked(item, True))
            menu.addAction(act_check_all)

            act_uncheck_all = QAction(strings.tr("ctx_group_uncheck_all"), self)
            act_uncheck_all.triggered.connect(lambda: self.tree_widget.set_group_checked(item, False))
            menu.addAction(act_uncheck_all)

            menu.addSeparator()
            act_group_review_keep = QAction(strings.tr("ctx_group_review_keep"), self)
            act_group_review_keep.triggered.connect(
                lambda: self._set_review_state(self.tree_widget.get_group_paths(item), "reviewed_keep")
            )
            menu.addAction(act_group_review_keep)

            act_group_review_delete = QAction(strings.tr("ctx_group_review_delete_later"), self)
            act_group_review_delete.triggered.connect(
                lambda: self._set_review_state(self.tree_widget.get_group_paths(item), "reviewed_delete_later")
            )
            menu.addAction(act_group_review_delete)

            act_group_review_clear = QAction(strings.tr("ctx_group_review_clear"), self)
            act_group_review_clear.triggered.connect(
                lambda: self._set_review_state(self.tree_widget.get_group_paths(item), "")
            )
            menu.addAction(act_group_review_clear)

            if self.selection_rules:
                act_apply_rules = QAction(strings.tr("ctx_group_apply_rules"), self)

                def apply_rules():
                    entries = [e for e, _ in self._group_entries_with_items(item)]
                    decision = self.results_controller.build_selection_decision(entries, strategy="smart", rules=self.selection_rules)
                    keep_set = set(decision.keep_set or [])
                    self._remember_selection_reasons(decision)
                    self.tree_widget.begin_bulk_check_update()
                    try:
                        for j in range(item.childCount()):
                            child = item.child(j)
                            p = child.data(0, Qt.ItemDataRole.UserRole)
                            if not p:
                                continue
                            child.setCheckState(0, Qt.CheckState.Unchecked if p in keep_set else Qt.CheckState.Checked)
                    finally:
                        self.tree_widget.end_bulk_check_update()

                act_apply_rules.triggered.connect(apply_rules)
                menu.addAction(act_apply_rules)

            # Hardlink group (advanced)
            try:
                enabled = bool(self.chk_enable_hardlink.isChecked()) and self._is_group_key_hardlink_eligible(key)
            except Exception:
                enabled = False
            if enabled:
                act_hardlink = QAction(strings.tr("ctx_group_hardlink"), self)

                def hardlink_group():
                    checked = []
                    unchecked = []
                    for j in range(item.childCount()):
                        child = item.child(j)
                        p = child.data(0, Qt.ItemDataRole.UserRole)
                        if not p:
                            continue
                        if child.checkState(0) == Qt.CheckState.Checked:
                            checked.append(p)
                        else:
                            unchecked.append(p)
                    paths = self.tree_widget.get_group_paths(item)
                    if len(paths) < 2:
                        return
                    # Prefer canonical from unchecked; fallback to oldest.
                    canonical = unchecked[0] if unchecked else None
                    if not canonical:
                        try:
                            canonical = min(paths, key=lambda p: self._mtime_for_path(p))
                        except Exception:
                            canonical = paths[0]
                    targets = checked if checked else [p for p in paths if p != canonical]
                    if not targets:
                        return
                    self._start_operation(Operation("hardlink_consolidate", options={"canonical": canonical, "targets": targets}))

                act_hardlink.triggered.connect(hardlink_group)
                menu.addAction(act_hardlink)

        menu.exec_(self.tree_widget.viewport().mapToGlobal(position))

    def open_containing_folder(self: Any, path):
        if not os.path.exists(path): return
        folder = os.path.dirname(path)
        if platform.system() == 'Windows':
            os.startfile(folder)
        elif platform.system() == 'Darwin':
            subprocess.call(('open', folder))
        else:
            subprocess.call(('xdg-open', folder))

    def copy_to_clipboard(self: Any, text):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def save_scan_results(self: Any):
        """Save current scan results to JSON."""
        if not self.scan_results:
            _mw().QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_files_selected"))
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            strings.tr("action_save_results"),
            "scan_results.json",
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            selected_paths = self.tree_widget.get_checked_files()
        except Exception:
            selected_paths = []
        try:
            payload = dump_results_v3(
                scan_results=self.scan_results,
                folders=list(self.selected_folders or []),
                source="gui",
                selected_paths=selected_paths,
                file_meta=self._current_result_meta,
                existence_map=self._current_result_existence_map,
                selection_reason_map=self._current_selection_reason_map,
                exemption_status_map=self._current_exemption_status_map,
                review_state_map=self._current_review_state_map,
                collection_role_map=self._current_collection_role_map,
                baseline_delta_map=self._current_baseline_delta_map,
            )
            payload_meta = payload.setdefault("meta", {})
            payload_meta["scan_status"] = str(self._last_scan_status or "completed")
            payload_meta["metrics"] = dict(self._last_scan_metrics or {})
            payload_meta["warnings"] = list(self._last_scan_warnings or [])
            payload_meta["groups"] = int(len(self.scan_results or {}))
            payload_meta["files"] = int(sum(len(v or []) for v in (self.scan_results or {}).values()))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            
            self.status_label.setText(strings.tr("msg_results_saved").format(path))
        except Exception as e:
            _mw().QMessageBox.critical(self, strings.tr("app_title"), strings.tr("err_save").format(e))

    def load_scan_results(self: Any):
        """Load scan results from JSON (new and legacy formats)."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            strings.tr("action_load_results"),
            "",
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            bundle = load_results_bundle_any(data)
            self.scan_results = dict(bundle.get("results") or {})
            bundle_delta_map = dict(bundle.get("baseline_delta_map") or {})
            self._current_baseline_delta_map = dict(bundle_delta_map)
            self._last_scan_status = str(bundle.get("scan_status") or "completed")
            self._last_scan_metrics = dict(bundle.get("metrics") or {})
            self._last_scan_warnings = list(bundle.get("warnings") or [])
            selected_paths = list(bundle.get("selected_paths") or [])
            file_meta = dict(bundle.get("file_meta") or {})
            existence_map = dict(bundle.get("existence_map") or {})
            file_state = load_file_state_map(data)
            self._current_selection_reason_map = {
                path: row.get("selection_reason") or ""
                for path, row in file_state.items()
                if row.get("selection_reason")
            }
            self._current_exemption_status_map = {
                path: row.get("exemption_status") or ""
                for path, row in file_state.items()
                if row.get("exemption_status")
            }
            self._current_review_state_map = {
                path: row.get("review_state") or ""
                for path, row in file_state.items()
                if row.get("review_state")
            }
            self._current_collection_role_map = {
                path: row.get("collection_role") or ""
                for path, row in file_state.items()
                if row.get("collection_role")
            }
            file_state_delta_map = {
                path: row.get("baseline_delta") or ""
                for path, row in file_state.items()
                if row.get("baseline_delta")
            }
            if file_state_delta_map:
                self._current_baseline_delta_map = file_state_delta_map
            self._render_results(
                self.scan_results,
                selected_paths=selected_paths,
                file_meta=file_meta,
                existence_map=existence_map,
                selected_count=len(selected_paths),
            )
            self.status_label.setText(strings.tr("msg_results_loaded").format(len(self.scan_results)))
            try:
                self._navigate_to("results")
            except Exception:
                pass
        except Exception as e:
            _mw().QMessageBox.critical(self, strings.tr("app_title"), strings.tr("err_load").format(e))
