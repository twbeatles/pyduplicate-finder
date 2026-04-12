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
from typing import Any, TYPE_CHECKING, cast

from src.core.history import HistoryManager
from src.core.cache_manager import CacheManager
from src.core.preset_manager import PresetManager, get_default_config
from src.core.file_lock_checker import FileLockChecker
from src.core.quarantine_manager import QuarantineManager
from src.core.preflight import PreflightAnalyzer
from src.core.selection_rules import parse_rules
from src.core.operation_queue import Operation
from src.core.scan_engine import ScanConfig, validate_similar_image_dependency
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



class MainWindowScanFlowMixin(DuplicateFinderTypingContract):
    def _on_folders_changed(self: Any):
        """Central place to update UI state that depends on selected folders."""
        count = len(self.selected_folders or [])

        if hasattr(self, "lbl_folder_count"):
            self.lbl_folder_count.setText(strings.tr("lbl_search_target").format(count))

        if hasattr(self, "lbl_tools_target"):
            self.lbl_tools_target.setText(strings.tr("lbl_search_target").format(count))

        has_folders = count > 0

        # Tools page: show a clearer hint + CTA when folders aren't selected yet.
        if hasattr(self, "lbl_tools_hint"):
            self.lbl_tools_hint.setText(
                strings.tr("msg_tools_page_hint") if has_folders else strings.tr("msg_tools_no_folders")
            )
        if hasattr(self, "btn_tools_go_scan"):
            self.btn_tools_go_scan.setVisible(not has_folders)
        if hasattr(self, "lbl_tools_target"):
            self.lbl_tools_target.setVisible(has_folders)

        is_scanning = bool(getattr(self, "btn_stop_scan", None) and self.btn_stop_scan.isEnabled())

        # Scan button should reflect real availability.
        if hasattr(self, "btn_start_scan"):
            self.btn_start_scan.setEnabled((not is_scanning) and has_folders)
            self.btn_start_scan.setToolTip("" if has_folders else strings.tr("msg_add_folder_first"))

        # Results empty-state CTAs
        if hasattr(self, "btn_results_empty_start_scan"):
            self.btn_results_empty_start_scan.setEnabled((not is_scanning) and has_folders)
            self.btn_results_empty_start_scan.setToolTip("" if has_folders else strings.tr("msg_add_folder_first"))
        if hasattr(self, "btn_results_empty_add_folder"):
            self.btn_results_empty_add_folder.setEnabled(not is_scanning)

        # Tools depend on folders.
        if hasattr(self, "btn_empty_tools"):
            self.btn_empty_tools.setEnabled(has_folders)
            self.btn_empty_tools.setToolTip("" if has_folders else strings.tr("msg_tools_no_locations"))
        if hasattr(self, "action_empty_finder"):
            self.action_empty_finder.setEnabled(has_folders)
            self.action_empty_finder.setToolTip("" if has_folders else strings.tr("msg_tools_no_locations"))

        # Keep action buttons consistent with current results/selection.
        try:
            self._update_action_buttons_state()
        except Exception:
            pass

    def add_path_to_list(self: Any, path):
        path = os.path.normpath(path)
        if path not in self.selected_folders:
            self.selected_folders.append(path)
            self.list_folders.addItem(path)
            self._on_folders_changed()

    def add_folder(self: Any):
        folder = QFileDialog.getExistingDirectory(self, strings.tr("btn_add_folder"))
        if folder:
            self.add_path_to_list(folder)

    def add_drive_dialog(self: Any):
        # Windows: List drives
        if platform.system() == "Windows":
            drives = []
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drives.append(f"{letter}:\\")
                bitmask >>= 1
            
            menu = QMenu(self)
            for d in drives:
                action = QAction(d, self)
                action.triggered.connect(lambda checked, drv=d: self.add_path_to_list(drv))
                menu.addAction(action)
            menu.exec(QCursor.pos())
        else:
            # Linux/Mac: Just open root selector or common mounts
            self.add_folder()

    def clear_folders(self: Any):
        self.selected_folders = []
        self.list_folders.clear()
        self._on_folders_changed()

    def remove_selected_folder(self: Any):
        """Remove the currently selected folder from the list"""
        current_row = self.list_folders.currentRow()
        if current_row >= 0:
            self.list_folders.takeItem(current_row)
            if current_row < len(self.selected_folders):
                del self.selected_folders[current_row]
            self._on_folders_changed()
        else:
            # Issue #12: Show feedback when no folder is selected
            self.status_label.setText(strings.tr("lbl_no_selection"))

    def start_scan(
        self,
        force_new=False,
        config_override: dict | None = None,
        folders_override: list[str] | None = None,
        scheduled_context: dict | None = None,
    ):
        if scheduled_context is not None:
            self._scheduled_run_context = dict(scheduled_context or {})

        current_config = self._get_current_config()
        if isinstance(config_override, dict):
            current_config.update(dict(config_override))
        if folders_override is not None:
            current_config["folders"] = list(folders_override or [])

        raw_folders = list(current_config.get("folders") or self.selected_folders or [])
        effective_folders = []
        seen = set()
        for p in raw_folders:
            if not p:
                continue
            abs_path = os.path.abspath(str(p))
            key = os.path.normcase(os.path.normpath(abs_path))
            if key in seen:
                continue
            seen.add(key)
            effective_folders.append(abs_path)
        current_config["folders"] = list(effective_folders)

        if not effective_folders:
            if self._scheduled_run_context and self._scheduled_job_run_id:
                logger.warning("Scheduled scan skipped: no valid folders at start_scan")
                self._finish_scheduled_run("skipped", {}, message_override="no_valid_folders")
                return
            _mw().QMessageBox.warning(cast(Any, self), strings.tr("app_title"), strings.tr("err_no_folder"))
            return

        raw_ext = str(current_config.get("extensions") or "").strip()
        extensions = [x.strip() for x in raw_ext.split(',') if x.strip()] if raw_ext else None
        min_size = max(0, int(current_config.get("min_size_kb") or 0))

        hash_config = self._get_scan_hash_config(current_config)
        config_hash = self.cache_manager.get_config_hash(hash_config)

        incremental_rescan = bool(current_config.get("incremental_rescan"))
        if incremental_rescan and not isinstance(config_override, dict):
            self.refresh_incremental_baselines()
            current_config["baseline_session_id"] = (
                self._get_selected_baseline_session_id() or current_config.get("baseline_session_id") or 0
            )
        baseline_session_id = int(current_config.get("baseline_session_id") or 0)
        if incremental_rescan and baseline_session_id <= 0:
            try:
                latest_completed = self.cache_manager.get_latest_completed_session_by_hash(config_hash)
                baseline_session_id = int((latest_completed or {}).get("id") or 0)
                current_config["baseline_session_id"] = baseline_session_id
            except Exception:
                logger.warning("Failed to resolve baseline session for incremental scan", exc_info=True)
                baseline_session_id = 0
        if incremental_rescan and baseline_session_id <= 0:
            if self._scheduled_run_context:
                logger.info("Scheduled scan: disabling incremental mode because baseline session is unavailable")
            else:
                _mw().QMessageBox.information(cast(Any, self), strings.tr("app_title"), strings.tr("msg_incremental_no_baseline"))
            incremental_rescan = False
            current_config["incremental_rescan"] = False
            current_config["baseline_session_id"] = 0

        scan_cfg = ScanConfig(
            folders=list(effective_folders or []),
            extensions=list(extensions or []),
            min_size_kb=int(min_size or 0),
            same_name=bool(current_config.get("same_name")),
            name_only=bool(current_config.get("name_only")),
            byte_compare=bool(current_config.get("byte_compare")),
            protect_system=bool(current_config.get("protect_system", True)),
            skip_hidden=bool(current_config.get("skip_hidden", False)),
            follow_symlinks=bool(current_config.get("follow_symlinks", False)),
            include_patterns=list(current_config.get("include_patterns") or []),
            exclude_patterns=list(current_config.get("exclude_patterns") or []),
            use_similar_image=bool(current_config.get("use_similar_image")),
            use_mixed_mode=bool(current_config.get("use_mixed_mode", False)),
            detect_duplicate_folders=bool(current_config.get("detect_duplicate_folders", False)),
            incremental_rescan=bool(incremental_rescan),
            baseline_session_id=int(baseline_session_id) if baseline_session_id > 0 else None,
            similarity_threshold=float(current_config.get("similarity_threshold") or 0.9),
            strict_mode=bool(current_config.get("strict_mode", False)),
            strict_max_errors=int(current_config.get("strict_max_errors") or 0),
        )
        dep_error_key = _mw().validate_similar_image_dependency(scan_cfg)
        if dep_error_key:
            msg = strings.tr(dep_error_key)
            if self._scheduled_run_context and self._scheduled_job_run_id:
                self._finish_scheduled_run("failed", {}, message_override="similar_dependency_missing")
                return
            _mw().QMessageBox.warning(cast(Any, self), strings.tr("app_title"), msg)
            return

        resumable = None
        if not force_new:
            resumable = self.cache_manager.find_resumable_session_by_hash(config_hash)
        session_id = None
        use_cached_files = False

        if resumable:
            session_id = self._to_int(resumable.get("id"), 0) or None
            use_cached_files = resumable.get("stage") in ("collected", "hashing", "completed")
            if not use_cached_files and session_id is not None:
                self.cache_manager.clear_scan_files(session_id)

            # Keep session metadata aligned with current settings (even if config_hash matches).
            try:
                if session_id is not None:
                    self.cache_manager.update_scan_session(
                        session_id,
                        config_json=json.dumps(current_config, ensure_ascii=False, sort_keys=True, default=str),
                        config_hash=config_hash,
                    )
            except Exception:
                logger.warning("Failed to update resumable session metadata", exc_info=True)
        else:
            session_id = self.cache_manager.create_scan_session(current_config, config_hash=config_hash)
            self.cache_manager.clear_selected_paths(session_id)

        if not session_id:
            use_cached_files = False
            session_id = None

        self.current_session_id = session_id
        if self._scheduled_run_context is not None:
            self._scheduled_run_context["executed_config_hash"] = config_hash
            self._scheduled_run_context["executed_folders"] = list(effective_folders)
        if self._scheduled_run_context and self._scheduled_job_run_id:
            try:
                self.cache_manager.update_scan_job_run_session(
                    self._scheduled_job_run_id,
                    session_id=self.current_session_id or 0,
                )
            except Exception:
                logger.warning("Failed to sync scheduled run session_id", exc_info=True)
        self._pending_selected_paths = []
        self._pending_selected_add.clear()
        self._pending_selected_remove.clear()
        self._saved_selected_paths = set()

        self._previous_results = self.scan_results
        self._previous_selected_paths = self.tree_widget.get_checked_files()
        self._previous_result_meta = dict(self._current_result_meta or {})
        self._previous_result_existence_map = dict(self._current_result_existence_map or {})
        self._previous_baseline_delta_map = dict(self._current_baseline_delta_map or {})

        self.tree_widget.clear()
        self.scan_results = {}
        self._current_result_meta = {}
        self._current_result_existence_map = {}
        self._current_baseline_delta_map = {}
        self._set_results_view(False)
        self._update_results_summary(0)
        self.toggle_ui_state(scanning=True)
        self._set_scan_stage_code("collecting")
        self.worker = self.scan_controller.build_worker(
            config=scan_cfg,
            session_id=session_id,
            use_cached_files=use_cached_files,
        )
        self.scan_controller.wire_signals(
            self.worker,
            on_progress=self.update_progress,
            on_stage=self.on_scan_stage_changed,
            on_finished=self.on_scan_finished,
            on_cancelled=self.on_scan_cancelled,
            on_failed=self.on_scan_failed,
        )
        self.worker.start()

    def stop_scan(self: Any):
        if hasattr(self, 'worker'):
            self.worker.stop()
            self.status_label.setText(strings.tr("status_stopping"))
            self._set_scan_stage(strings.tr("status_stopping"))
            try:
                self.btn_stop_scan.setEnabled(False)
            except Exception:
                pass

    def toggle_ui_state(self: Any, scanning):
        # Start scan requires at least one folder.
        self.btn_start_scan.setEnabled((not scanning) and bool(self.selected_folders))
        self.btn_stop_scan.setEnabled(scanning)
        self.btn_delete.setEnabled(not scanning)
        self.btn_select_smart.setEnabled(not scanning)
        self.btn_export.setEnabled(not scanning)
        if hasattr(self, "btn_results_empty_start_scan"):
            self.btn_results_empty_start_scan.setEnabled((not scanning) and bool(self.selected_folders))
        if hasattr(self, "btn_results_empty_add_folder"):
            self.btn_results_empty_add_folder.setEnabled(not scanning)
        # Issue #22: Disable folder buttons during scan
        self.btn_add_folder.setEnabled(not scanning)
        self.btn_add_drive.setEnabled(not scanning)
        self.btn_clear_folder.setEnabled(not scanning)
        self.btn_remove_folder.setEnabled(not scanning)
        self.btn_empty_tools.setEnabled((not scanning) and bool(self.selected_folders))
        if hasattr(self, "action_empty_finder"):
            self.action_empty_finder.setEnabled((not scanning) and bool(self.selected_folders))
        self._update_action_buttons_state()

    def update_progress(self: Any, val, msg):
        self.progress_bar.setValue(val)
        self.status_label.setText(msg)
        # Prefer structured stage codes if available; fallback to parsing message.
        if self._current_scan_stage_code:
            self._set_scan_stage_code(self._current_scan_stage_code)
        else:
            self._set_scan_stage(msg)

    def on_scan_stage_changed(self: Any, stage_code: str):
        self._set_scan_stage_code(stage_code)

    def on_scan_finished(self: Any, results):
        self.scan_results = results
        self._previous_results = None
        self._previous_selected_paths = []
        self._previous_result_meta = {}
        self._previous_result_existence_map = {}
        self._previous_baseline_delta_map = {}
        scan_status = str(getattr(self.worker, "latest_scan_status", "completed") or "completed")
        self._last_scan_status = scan_status
        self._last_scan_metrics = dict(getattr(self.worker, "latest_scan_metrics", {}) or {})
        self._last_scan_warnings = list(getattr(self.worker, "latest_scan_warnings", []) or [])
        self._set_scan_stage_code("completed")
        self.toggle_ui_state(scanning=False)
        self.progress_bar.setValue(100)
        base_msg = strings.tr("msg_scan_complete").format(len(results))
        if scan_status == "partial":
            base_msg = strings.tr("msg_scan_complete_partial").format(len(results))
        delta_msg = ""
        try:
            stats = dict(getattr(self.worker, "incremental_stats", {}) or {})
            if stats and int(stats.get("base_session_id") or 0) > 0:
                delta_msg = strings.tr("msg_incremental_delta").format(
                    added=int(stats.get("new") or 0),
                    changed=int(stats.get("changed") or 0),
                    missing=int(stats.get("missing") or 0),
                )
        except Exception:
            delta_msg = ""
        metric_msg = ""
        try:
            errs = int(self._last_scan_metrics.get("errors_total", 0) or 0)
            if errs > 0:
                metric_msg = strings.tr("msg_scan_error_summary").format(errors=errs)
        except Exception:
            metric_msg = ""
        parts = [base_msg]
        if delta_msg:
            parts.append(delta_msg)
        if metric_msg:
            parts.append(metric_msg)
        self.status_label.setText(" / ".join(parts))
        self._set_scan_stage_code("completed")
        file_meta = {}
        try:
            file_meta = dict(getattr(self.worker, "latest_file_meta", {}) or {})
        except Exception:
            file_meta = {}
        try:
            self._current_baseline_delta_map = dict(getattr(self.worker, "latest_baseline_delta_map", {}) or {})
        except Exception:
            self._current_baseline_delta_map = {}
        existence_map = {p: True for p in file_meta.keys()} if file_meta else None
        self._current_result_existence_map = dict(existence_map or {})
        self._render_results(results, selected_paths=[], file_meta=file_meta, existence_map=existence_map, selected_count=0)
        # UX: bring user to focused results page after scan completes.
        try:
            self._navigate_to("results")
        except Exception:
            pass
        if self.current_session_id:
            self.cache_manager.save_scan_results(self.current_session_id, results)
            self.cache_manager.clear_selected_paths(self.current_session_id)

        # Scheduler post-actions (auto export + job run bookkeeping).
        self._finish_scheduled_run(scan_status, results)
        if scan_status == "partial" and hasattr(self, "toast_manager") and self.toast_manager:
            self.toast_manager.warning(strings.tr("msg_scan_partial_warning"), duration=4000)

    def on_scan_cancelled(self: Any):
        """Issue #3: Handle scan cancellation - preserve previous results"""
        self._set_scan_stage(strings.tr("status_stopped"))
        self._current_scan_stage_code = None
        self.toggle_ui_state(scanning=False)
        self.progress_bar.setValue(0)
        self.status_label.setText(strings.tr("status_stopped"))
        if getattr(self, "_previous_results", None):
            self.scan_results = self._previous_results
            self._current_baseline_delta_map = dict(self._previous_baseline_delta_map or {})
            self._render_results(
                self.scan_results,
                selected_paths=self._previous_selected_paths,
                file_meta=self._previous_result_meta,
                existence_map=self._previous_result_existence_map,
                selected_count=len(self._previous_selected_paths),
            )
        else:
            self._set_results_view(False)
            self._update_results_summary(0)
            self._update_action_buttons_state(selected_count=0)
        self._finish_scheduled_run("cancelled", {})

    def on_scan_failed(self: Any, message):
        self._set_scan_stage(strings.tr("status_stopped"))
        self._current_scan_stage_code = None
        self.toggle_ui_state(scanning=False)
        self.progress_bar.setValue(0)
        err_msg = strings.tr("err_scan_failed").format(message)
        self.status_label.setText(err_msg)
        if getattr(self, "_previous_results", None):
            self.scan_results = self._previous_results
            self._current_baseline_delta_map = dict(self._previous_baseline_delta_map or {})
            self._render_results(
                self.scan_results,
                selected_paths=self._previous_selected_paths,
                file_meta=self._previous_result_meta,
                existence_map=self._previous_result_existence_map,
                selected_count=len(self._previous_selected_paths),
            )
        else:
            self._set_results_view(False)
            self._update_results_summary(0)
            self._update_action_buttons_state(selected_count=0)
        self._finish_scheduled_run("failed", {})
        _mw().QMessageBox.critical(self, strings.tr("app_title"), err_msg)

    def _normalize_extension_tokens(self: Any, value):
        if value is None:
            return []
        if isinstance(value, str):
            raw = [x.strip() for x in value.split(",")]
        elif isinstance(value, (list, tuple, set)):
            raw = [str(x or "").strip() for x in value]
        else:
            raw = [str(value).strip()]
        out = set()
        for token in raw:
            if not token:
                continue
            token = token.lower().lstrip(".")
            if token:
                out.add(token)
        return sorted(out)

    def _normalize_path_list(self: Any, values):
        out = set()
        for path in values or []:
            p = str(path or "").strip()
            if not p:
                continue
            p = os.path.normcase(os.path.normpath(os.path.abspath(p)))
            out.add(p)
        return sorted(out)

    def _normalize_pattern_list(self: Any, values):
        out = set()
        for token in values or []:
            p = str(token or "").strip()
            if not p:
                continue
            out.add(p)
        return sorted(out)

    def _get_scan_hash_config(self: Any, config: dict) -> dict:
        hash_config = dict(config or {})
        hash_config.pop("use_trash", None)
        hash_config.pop("baseline_session_id", None)
        hash_config.pop("incremental_rescan", None)

        hash_config["folders"] = self._normalize_path_list(hash_config.get("folders") or [])
        hash_config["extensions"] = self._normalize_extension_tokens(hash_config.get("extensions"))
        hash_config["include_patterns"] = self._normalize_pattern_list(hash_config.get("include_patterns") or [])
        hash_config["exclude_patterns"] = self._normalize_pattern_list(hash_config.get("exclude_patterns") or [])

        if not hash_config.get("use_similar_image"):
            hash_config.pop("similarity_threshold", None)
            hash_config.pop("use_mixed_mode", None)
        if hash_config.get("name_only"):
            hash_config.pop("detect_duplicate_folders", None)
            hash_config.pop("use_mixed_mode", None)
        return hash_config
