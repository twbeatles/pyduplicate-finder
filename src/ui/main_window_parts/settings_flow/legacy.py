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



class MainWindowSettingsFlowMixin(DuplicateFinderTypingContract):
    def save_settings(self: Any):
        self.settings.setValue("app/geometry", self.saveGeometry())
        self.settings.setValue("app/splitter", self.splitter.saveState())
        self.settings.setValue("filter/extensions", self.txt_extensions.text())
        self.settings.setValue("filter/min_size", self.spin_min_size.value())
        self.settings.setValue("filter/protect_system", self.chk_protect_system.isChecked())
        self.settings.setValue("filter/byte_compare", self.chk_byte_compare.isChecked())
        self.settings.setValue("filter/same_name", self.chk_same_name.isChecked())
        self.settings.setValue("filter/name_only", self.chk_name_only.isChecked())
        if hasattr(self, "chk_skip_hidden"):
            self.settings.setValue("filter/skip_hidden", self.chk_skip_hidden.isChecked())
        if hasattr(self, "chk_follow_symlinks"):
            self.settings.setValue("filter/follow_symlinks", self.chk_follow_symlinks.isChecked())
        self.settings.setValue("filter/use_trash", self.chk_use_trash.isChecked())
        self.settings.setValue("filter/use_similar_image", self.chk_similar_image.isChecked())
        if hasattr(self, "chk_mixed_mode"):
            self.settings.setValue("filter/use_mixed_mode", self.chk_mixed_mode.isChecked())
        if hasattr(self, "chk_detect_folder_dup"):
            self.settings.setValue("filter/detect_duplicate_folders", self.chk_detect_folder_dup.isChecked())
        if hasattr(self, "chk_incremental_rescan"):
            self.settings.setValue("filter/incremental_rescan", self.chk_incremental_rescan.isChecked())
        if hasattr(self, "cmb_baseline_session"):
            self.settings.setValue("filter/baseline_session_id", int(self._get_selected_baseline_session_id() or 0))
        if hasattr(self, "chk_strict_mode"):
            self.settings.setValue("filter/strict_mode", self.chk_strict_mode.isChecked())
        if hasattr(self, "spin_strict_max_errors"):
            self.settings.setValue("filter/strict_max_errors", int(self.spin_strict_max_errors.value()))
        self.settings.setValue("filter/similarity_threshold", self.spin_similarity.value())
        if hasattr(self, "chk_similar_document"):
            self.settings.setValue("filter/use_similar_document", self.chk_similar_document.isChecked())
        if hasattr(self, "spin_document_similarity"):
            self.settings.setValue("filter/document_similarity_threshold", self.spin_document_similarity.value())
        if hasattr(self, "cmb_selection_policy"):
            self.settings.setValue("filter/selection_policy", str(self.cmb_selection_policy.currentData() or "smart"))
        if hasattr(self, "cmb_compare_mode"):
            self.settings.setValue("filter/compare_mode", str(self.cmb_compare_mode.currentData() or "none"))
        if hasattr(self, "chk_apply_exemptions"):
            self.settings.setValue("filter/apply_exemptions", self.chk_apply_exemptions.isChecked())
        if hasattr(self, "chk_post_cleanup_empty_dirs"):
            self.settings.setValue("filter/post_cleanup_empty_dirs", self.chk_post_cleanup_empty_dirs.isChecked())
        if hasattr(self, "chk_watch_mode"):
            self.settings.setValue("filter/watch_mode", self.chk_watch_mode.isChecked())
        self.settings.setValue("folders", self.selected_folders)
        
        # Save shortcut settings
        if self.custom_shortcuts:
            self.settings.setValue("app/shortcuts", json.dumps(self.custom_shortcuts))
        
        # Save pattern settings (persist empty arrays as well)
        try:
            self.settings.setValue("filter/exclude_patterns", json.dumps(self.exclude_patterns or []))
            self.settings.setValue("filter/include_patterns", json.dumps(self.include_patterns or []))
        except Exception:
            pass

        # Selection rules
        try:
            self.settings.setValue("rules/selection_json", json.dumps(self.selection_rules_json or []))
        except Exception:
            pass

        # Quarantine / advanced settings
        try:
            if hasattr(self, "chk_quarantine_enabled"):
                self.settings.setValue("quarantine/enabled", bool(self.chk_quarantine_enabled.isChecked()))
            if hasattr(self, "spin_quarantine_days"):
                self.settings.setValue("quarantine/max_days", int(self.spin_quarantine_days.value()))
            if hasattr(self, "spin_quarantine_gb"):
                gb = int(self.spin_quarantine_gb.value())
                self.settings.setValue("quarantine/max_bytes", int(gb) * 1024 * 1024 * 1024)
            if hasattr(self, "txt_quarantine_path"):
                self.settings.setValue("quarantine/path_override", str(self.txt_quarantine_path.text() or "").strip())
            if hasattr(self, "chk_enable_hardlink"):
                self.settings.setValue("ops/enable_hardlink", bool(self.chk_enable_hardlink.isChecked()))
        except Exception:
            pass

        # Cache policy settings
        try:
            if hasattr(self, "spin_cache_session_keep_latest"):
                self.settings.setValue(
                    "cache/session_keep_latest",
                    int(self.spin_cache_session_keep_latest.value()),
                )
            if hasattr(self, "spin_cache_hash_cleanup_days"):
                self.settings.setValue(
                    "cache/hash_cleanup_days",
                    int(self.spin_cache_hash_cleanup_days.value()),
                )
        except Exception:
            pass

        # Scheduler settings
        try:
            if hasattr(self, "chk_schedule_enabled"):
                self.settings.setValue("schedule/enabled", bool(self.chk_schedule_enabled.isChecked()))
            if hasattr(self, "cmb_schedule_frequency"):
                self.settings.setValue("schedule/type", str(self.cmb_schedule_frequency.currentData() or "daily"))
            if hasattr(self, "cmb_schedule_weekday"):
                self.settings.setValue("schedule/weekday", int(self.cmb_schedule_weekday.currentData() or 0))
            if hasattr(self, "txt_schedule_time"):
                time_hhmm = str(self.txt_schedule_time.text() or "03:00").strip() or "03:00"
                if self._validate_schedule_time_hhmm(time_hhmm):
                    self.settings.setValue("schedule/time_hhmm", time_hhmm)
                else:
                    logger.warning("Skip saving invalid schedule time: %s", time_hhmm)
            if hasattr(self, "txt_schedule_output"):
                self.settings.setValue("schedule/output_dir", str(self.txt_schedule_output.text() or "").strip())
            if hasattr(self, "txt_schedule_job_name"):
                self.settings.setValue("schedule/job_name", str(self.txt_schedule_job_name.text() or "").strip() or "default")
            if hasattr(self, "chk_schedule_export_json"):
                self.settings.setValue("schedule/output_json", bool(self.chk_schedule_export_json.isChecked()))
            if hasattr(self, "chk_schedule_export_csv"):
                self.settings.setValue("schedule/output_csv", bool(self.chk_schedule_export_csv.isChecked()))
        except Exception:
            pass

        try:
            self.settings.sync()
        except Exception:
            pass

    def load_settings(self: Any):
        geo = self.settings.value("app/geometry")
        if geo: self.restoreGeometry(geo)
        
        state = self.settings.value("app/splitter")
        if state: self.splitter.restoreState(state)
        
        self.txt_extensions.setText(self.settings.value("filter/extensions", ""))
        
        val = self.settings.value("filter/min_size", 0)
        self.spin_min_size.setValue(self._to_int(val, 0) if val else 0)
        
        self.chk_protect_system.setChecked(str(self.settings.value("filter/protect_system", True)).lower() == 'true')
        self.chk_byte_compare.setChecked(str(self.settings.value("filter/byte_compare", False)).lower() == 'true')
        self.chk_same_name.setChecked(str(self.settings.value("filter/same_name", False)).lower() == 'true')
        self.chk_name_only.setChecked(str(self.settings.value("filter/name_only", False)).lower() == 'true')
        if hasattr(self, "chk_skip_hidden"):
            self.chk_skip_hidden.setChecked(str(self.settings.value("filter/skip_hidden", False)).lower() == 'true')
        if hasattr(self, "chk_follow_symlinks"):
            self.chk_follow_symlinks.setChecked(str(self.settings.value("filter/follow_symlinks", False)).lower() == 'true')
        self.chk_use_trash.setChecked(str(self.settings.value("filter/use_trash", False)).lower() == 'true')
        self.chk_similar_image.setChecked(str(self.settings.value("filter/use_similar_image", False)).lower() == 'true')
        if hasattr(self, "chk_mixed_mode"):
            self.chk_mixed_mode.setChecked(str(self.settings.value("filter/use_mixed_mode", False)).lower() == 'true')
        if hasattr(self, "chk_detect_folder_dup"):
            self.chk_detect_folder_dup.setChecked(str(self.settings.value("filter/detect_duplicate_folders", False)).lower() == 'true')
        if hasattr(self, "chk_incremental_rescan"):
            self.chk_incremental_rescan.setChecked(str(self.settings.value("filter/incremental_rescan", False)).lower() == 'true')
        if hasattr(self, "chk_strict_mode"):
            self.chk_strict_mode.setChecked(str(self.settings.value("filter/strict_mode", False)).lower() == 'true')
        if hasattr(self, "spin_strict_max_errors"):
            strict_max = self._to_int(self.settings.value("filter/strict_max_errors", 0), 0)
            self.spin_strict_max_errors.setValue(max(0, strict_max))
        similarity = self.settings.value("filter/similarity_threshold", 0.9)
        self.spin_similarity.setValue(self._to_float(similarity, 0.9))
        if hasattr(self, "chk_similar_document"):
            self.chk_similar_document.setChecked(str(self.settings.value("filter/use_similar_document", False)).lower() == 'true')
        if hasattr(self, "spin_document_similarity"):
            doc_similarity = self.settings.value("filter/document_similarity_threshold", 0.9)
            self.spin_document_similarity.setValue(self._to_float(doc_similarity, 0.9))
        if hasattr(self, "cmb_selection_policy"):
            selection_policy = str(self.settings.value("filter/selection_policy", "smart") or "smart")
            idx = self.cmb_selection_policy.findData(selection_policy)
            self.cmb_selection_policy.setCurrentIndex(idx if idx >= 0 else 0)
        if hasattr(self, "cmb_compare_mode"):
            compare_mode = str(self.settings.value("filter/compare_mode", "none") or "none")
            idx = self.cmb_compare_mode.findData(compare_mode)
            self.cmb_compare_mode.setCurrentIndex(idx if idx >= 0 else 0)
        if hasattr(self, "chk_apply_exemptions"):
            self.chk_apply_exemptions.setChecked(str(self.settings.value("filter/apply_exemptions", True)).lower() == 'true')
        if hasattr(self, "chk_post_cleanup_empty_dirs"):
            self.chk_post_cleanup_empty_dirs.setChecked(str(self.settings.value("filter/post_cleanup_empty_dirs", False)).lower() == 'true')
        if hasattr(self, "chk_watch_mode"):
            self.chk_watch_mode.setChecked(str(self.settings.value("filter/watch_mode", False)).lower() == 'true')
        self.refresh_incremental_baselines()
        if hasattr(self, "cmb_baseline_session"):
            sid = self._to_int(self.settings.value("filter/baseline_session_id", 0), 0)
            if sid > 0:
                idx = self.cmb_baseline_session.findData(sid)
                if idx >= 0:
                    self.cmb_baseline_session.setCurrentIndex(idx)
        self._sync_filter_states()
        
        folders = self.settings.value("folders", [])
        # Normalize saved folders value (string -> list)
        if isinstance(folders, str): folders = [folders]
        elif not isinstance(folders, list): folders = []
        
        self.selected_folders = [f for f in folders if os.path.exists(f)]
        
        # Populate ListWidget
        self.list_folders.clear()
        for f in self.selected_folders:
            self.list_folders.addItem(f)
        self._on_folders_changed()
        self.refresh_incremental_baselines()

        # Restore Theme
        theme = self.settings.value("app/theme", "light")
        self.action_theme.setChecked(theme == "dark")
        
        # Issue #14: Restore Language setting
        lang = self.settings.value("app/language", "ko")
        strings.set_language(lang)
        
        # Load shortcuts
        shortcuts_json = self.settings.value("app/shortcuts", "")
        if shortcuts_json:
            try:
                loaded_shortcuts = self._json_loads(shortcuts_json, {})
                self.custom_shortcuts = loaded_shortcuts if isinstance(loaded_shortcuts, dict) else {}
                self._apply_shortcuts(self.custom_shortcuts)
            except:
                pass
        
        # Load exclude patterns
        patterns_json = self.settings.value("filter/exclude_patterns", "")
        if patterns_json:
            try:
                loaded_patterns = self._json_loads(patterns_json, [])
                self.exclude_patterns = loaded_patterns if isinstance(loaded_patterns, list) else []
                if self.exclude_patterns:
                    self.btn_exclude_patterns.setText(
                        f"{strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})"
                    )
            except:
                self.exclude_patterns = []

        # Load include patterns
        include_json = self.settings.value("filter/include_patterns", "")
        if include_json:
            try:
                loaded_include = self._json_loads(include_json, [])
                self.include_patterns = loaded_include if isinstance(loaded_include, list) else []
                if hasattr(self, "btn_include_patterns") and self.include_patterns:
                    self.btn_include_patterns.setText(
                        f"{strings.tr('btn_include_patterns')} ({len(self.include_patterns)})"
                    )
            except Exception:
                self.include_patterns = []

        # Selection rules load
        try:
            rules_json = self.settings.value("rules/selection_json", "[]")
            loaded_rules = self._json_loads(rules_json, [])
            self.selection_rules_json = loaded_rules if isinstance(loaded_rules, list) else []
        except Exception:
            self.selection_rules_json = []
        try:
            self.selection_rules = parse_rules(self.selection_rules_json)
        except Exception:
            self.selection_rules = []

        # Quarantine / advanced settings load
        try:
            q_enabled = str(self.settings.value("quarantine/enabled", True)).lower() == "true"
            q_days = self.settings.value("quarantine/max_days", 30)
            q_bytes = self.settings.value("quarantine/max_bytes", 10 * 1024 * 1024 * 1024)
            q_path = str(self.settings.value("quarantine/path_override", "") or "").strip()

            if hasattr(self, "chk_quarantine_enabled"):
                self.chk_quarantine_enabled.setChecked(bool(q_enabled))
            if hasattr(self, "spin_quarantine_days"):
                self.spin_quarantine_days.setValue(self._to_int(q_days, 30) if q_days else 30)
            if hasattr(self, "spin_quarantine_gb"):
                try:
                    q_bytes_int = self._to_int(q_bytes, 10 * 1024 * 1024 * 1024)
                    gb = max(1, int(q_bytes_int / (1024 * 1024 * 1024)))
                except Exception:
                    gb = 10
                self.spin_quarantine_gb.setValue(gb)
            if hasattr(self, "txt_quarantine_path"):
                self.txt_quarantine_path.setText(q_path)
            if q_path:
                self.quarantine_manager._quarantine_dir = q_path

            hl_enabled = str(self.settings.value("ops/enable_hardlink", False)).lower() == "true"
            if hasattr(self, "chk_enable_hardlink"):
                self.chk_enable_hardlink.setChecked(bool(hl_enabled))

            self._sync_advanced_visibility()

            # Apply retention at startup (best-effort).
            try:
                self._apply_quarantine_retention()
            except Exception:
                pass
        except Exception:
            pass

        # Cache policy settings load
        try:
            keep_latest = self._to_int(self.settings.value("cache/session_keep_latest", 20), 20)
        except Exception:
            keep_latest = 20
        try:
            hash_cleanup_days = self._to_int(self.settings.value("cache/hash_cleanup_days", 30), 30)
        except Exception:
            hash_cleanup_days = 30
        if hasattr(self, "spin_cache_session_keep_latest"):
            self.spin_cache_session_keep_latest.setValue(max(1, min(500, int(keep_latest))))
        if hasattr(self, "spin_cache_hash_cleanup_days"):
            self.spin_cache_hash_cleanup_days.setValue(max(1, min(3650, int(hash_cleanup_days))))

        # Scheduler settings load
        try:
            if hasattr(self, "chk_schedule_enabled"):
                self.chk_schedule_enabled.setChecked(str(self.settings.value("schedule/enabled", False)).lower() == "true")
            if hasattr(self, "cmb_schedule_frequency"):
                st = str(self.settings.value("schedule/type", "daily") or "daily")
                idx = self.cmb_schedule_frequency.findData(st)
                self.cmb_schedule_frequency.setCurrentIndex(idx if idx >= 0 else 0)
            if hasattr(self, "cmb_schedule_weekday"):
                wd = self._to_int(self.settings.value("schedule/weekday", 0), 0)
                idx = self.cmb_schedule_weekday.findData(wd)
                self.cmb_schedule_weekday.setCurrentIndex(idx if idx >= 0 else 0)
            if hasattr(self, "txt_schedule_time"):
                self.txt_schedule_time.setText(str(self.settings.value("schedule/time_hhmm", "03:00") or "03:00"))
            if hasattr(self, "txt_schedule_output"):
                self.txt_schedule_output.setText(str(self.settings.value("schedule/output_dir", "") or ""))
            if hasattr(self, "txt_schedule_job_name"):
                self.txt_schedule_job_name.setText(str(self.settings.value("schedule/job_name", "default") or "default"))
            if hasattr(self, "chk_schedule_export_json"):
                self.chk_schedule_export_json.setChecked(str(self.settings.value("schedule/output_json", True)).lower() == "true")
            if hasattr(self, "chk_schedule_export_csv"):
                self.chk_schedule_export_csv.setChecked(str(self.settings.value("schedule/output_csv", True)).lower() == "true")
            self._sync_schedule_ui()
            self.refresh_schedule_jobs_view()
            if not (self.cache_manager.list_scan_jobs() or []):
                self._persist_schedule_job()
        except Exception:
            pass

    def _restore_cached_session(self: Any):
        try:
            keep_latest = self._to_int(self.settings.value("cache/session_keep_latest", 20), 20)
        except Exception:
            keep_latest = 20
        try:
            hash_cleanup_days = self._to_int(self.settings.value("cache/hash_cleanup_days", 30), 30)
        except Exception:
            hash_cleanup_days = 30
        self.cache_manager.cleanup_old_sessions(keep_latest=max(1, int(keep_latest)))
        try:
            self.cache_manager.cleanup_old_entries(days_old=max(1, int(hash_cleanup_days)))
        except Exception:
            logger.warning("Failed to cleanup old file hash cache entries", exc_info=True)
        session = self.cache_manager.get_latest_session()
        if not session:
            return

        config = None
        try:
            config = json.loads(session.get("config_json", ""))
        except Exception:
            config = None

        if config:
            self._apply_config(config)

        self.current_session_id = self._to_int(session.get("id"), 0) or None

        if session.get("status") in ("completed", "partial") and self.current_session_id is not None:
            results = self.cache_manager.load_scan_results(self.current_session_id)
            if results:
                selected_paths = self.cache_manager.load_selected_paths(self.current_session_id)
                self.scan_results = results
                self._current_baseline_delta_map = {}
                self._current_selection_reason_map = {}
                self._current_exemption_status_map = {}
                self._current_review_state_map = {}
                self._current_collection_role_map = {}
                self._render_results(results, selected_paths=list(selected_paths), selected_count=len(selected_paths))
                self.status_label.setText(strings.tr("msg_results_loaded").format(len(results)))
                # Restore UX: bring the user to the focused results page when data is available.
                try:
                    self._navigate_to("results")
                except Exception:
                    pass
                QTimer.singleShot(0, self._prune_missing_results_after_restore)
        else:
            if session.get("progress_message"):
                self.status_label.setText(str(session.get("progress_message") or ""))
            try:
                self._set_scan_stage_code(str(session.get("stage") or ""))
            except Exception:
                pass
            if session.get("status") in ("running", "paused"):
                self._prompt_resume_session(session)

    def _prompt_resume_session(self: Any, session: dict | None = None):
        session = session or {}
        box = _mw().QMessageBox(self)
        box.setWindowTitle(strings.tr("app_title"))
        box.setIcon(_mw().QMessageBox.Icon.Question)
        box.setText(strings.tr("msg_resume_scan"))

        # Provide details to reduce uncertainty (stage / last update / last message).
        try:
            stage_code = str(session.get("stage") or "")
            stage_map = {
                "collecting": strings.tr("status_collecting_files"),
                "collected": strings.tr("status_collecting_files"),
                "hashing": strings.tr("status_hashing"),
                "similar_image": strings.tr("status_similar_image_scan"),
                "grouping": strings.tr("status_grouping"),
                "analyzing": strings.tr("status_analyzing"),
                "completed": strings.tr("status_done"),
                "error": strings.tr("status_error"),
                "abandoned": strings.tr("status_abandoned"),
            }
            stage_label = stage_map.get(stage_code, stage_code or strings.tr("status_ready"))

            updated_at = session.get("updated_at")
            if updated_at:
                dt = datetime.fromtimestamp(float(updated_at)).strftime("%Y-%m-%d %H:%M")
            else:
                dt = "-"

            msg = str(session.get("progress_message") or "").strip()
            prog = session.get("progress")
            if isinstance(prog, int) and prog:
                msg = f"{msg}\n{prog}%" if msg else f"{prog}%"
            if not msg:
                msg = "-"

            box.setInformativeText(
                strings.tr("msg_resume_scan_details").format(stage=stage_label, time=dt, message=msg)
            )
        except Exception:
            pass
        btn_resume = box.addButton(strings.tr("btn_resume"), _mw().QMessageBox.ButtonRole.AcceptRole)
        btn_new = box.addButton(strings.tr("btn_new_scan"), _mw().QMessageBox.ButtonRole.DestructiveRole)
        btn_later = box.addButton(strings.tr("btn_later"), _mw().QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_resume)
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_resume:
            QTimer.singleShot(0, self.start_scan)
        elif clicked == btn_new:
            if self.current_session_id:
                self.cache_manager.update_scan_session(
                    self.current_session_id,
                    status="abandoned",
                    stage="abandoned"
                )
                self.current_session_id = None
            QTimer.singleShot(0, lambda: self.start_scan(force_new=True))

    def open_preset_dialog(self: Any):
        """Open the preset management dialog."""
        current_config = self._get_current_config()
        dlg = PresetDialog(self.preset_manager, current_config, self)
        if dlg.exec() and dlg.selected_config:
            self._apply_config(dlg.selected_config)

    def open_exclude_patterns_dialog(self: Any):
        """Open the exclude-pattern settings dialog."""
        dlg = ExcludePatternsDialog(
            self.exclude_patterns,
            self,
            title=strings.tr("dlg_exclude_title"),
            desc=strings.tr("lbl_exclude_desc"),
            placeholder=strings.tr("ph_exclude_pattern"),
            common_patterns=ExcludePatternsDialog.COMMON_PATTERNS,
        )
        if dlg.exec():
            self.exclude_patterns = dlg.get_patterns()
            # Reflect exclude-pattern button state
            if self.exclude_patterns:
                self.btn_exclude_patterns.setText(
                    f"{strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})"
                )
            else:
                self.btn_exclude_patterns.setText(strings.tr("btn_exclude_patterns"))

    def open_include_patterns_dialog(self: Any):
        """Open the include-pattern settings dialog."""
        dlg = ExcludePatternsDialog(
            self.include_patterns,
            self,
            title=strings.tr("dlg_include_title"),
            desc=strings.tr("lbl_include_desc"),
            placeholder=strings.tr("ph_include_pattern"),
            common_patterns=ExcludePatternsDialog.COMMON_INCLUDE_PATTERNS,
        )
        if dlg.exec():
            self.include_patterns = dlg.get_patterns()
            if hasattr(self, "btn_include_patterns"):
                if self.include_patterns:
                    self.btn_include_patterns.setText(
                        f"{strings.tr('btn_include_patterns')} ({len(self.include_patterns)})"
                    )
                else:
                    self.btn_include_patterns.setText(strings.tr("btn_include_patterns"))

    def open_shortcut_settings(self: Any):
        """Open the shortcut settings dialog."""
        dlg = ShortcutSettingsDialog(self.custom_shortcuts, self)
        if dlg.exec():
            self.custom_shortcuts = dlg.get_shortcuts()
            self._apply_shortcuts(self.custom_shortcuts)

    def _get_current_config(self: Any) -> dict:
        """Return current scan settings from UI controls."""
        return {
            'folders': self.selected_folders.copy(),
            'extensions': self.txt_extensions.text(),
            'min_size_kb': self.spin_min_size.value(),
            'protect_system': self.chk_protect_system.isChecked(),
            'byte_compare': self.chk_byte_compare.isChecked(),
            'same_name': self.chk_same_name.isChecked(),
            'name_only': self.chk_name_only.isChecked(),
            'skip_hidden': self.chk_skip_hidden.isChecked() if hasattr(self, 'chk_skip_hidden') else False,
            'follow_symlinks': self.chk_follow_symlinks.isChecked() if hasattr(self, 'chk_follow_symlinks') else False,
            'include_patterns': self.include_patterns.copy(),
            'exclude_patterns': self.exclude_patterns.copy(),
            'use_trash': self.chk_use_trash.isChecked(),
            'use_similar_image': self.chk_similar_image.isChecked(),
            'use_mixed_mode': self.chk_mixed_mode.isChecked() if hasattr(self, 'chk_mixed_mode') else False,
            'detect_duplicate_folders': self.chk_detect_folder_dup.isChecked() if hasattr(self, 'chk_detect_folder_dup') else False,
            'incremental_rescan': self.chk_incremental_rescan.isChecked() if hasattr(self, 'chk_incremental_rescan') else False,
            'baseline_session_id': self._get_selected_baseline_session_id() or 0,
            'similarity_threshold': self.spin_similarity.value(),
            'selection_policy': str(self.cmb_selection_policy.currentData() or 'smart') if hasattr(self, 'cmb_selection_policy') else 'smart',
            'compare_mode': str(self.cmb_compare_mode.currentData() or 'none') if hasattr(self, 'cmb_compare_mode') else 'none',
            'folder_roles': {},
            'use_similar_document': self.chk_similar_document.isChecked() if hasattr(self, 'chk_similar_document') else False,
            'document_similarity_threshold': self.spin_document_similarity.value() if hasattr(self, 'spin_document_similarity') else 0.9,
            'watch_mode': self.chk_watch_mode.isChecked() if hasattr(self, 'chk_watch_mode') else False,
            'apply_exemptions': self.chk_apply_exemptions.isChecked() if hasattr(self, 'chk_apply_exemptions') else True,
            'post_cleanup_empty_dirs': self.chk_post_cleanup_empty_dirs.isChecked() if hasattr(self, 'chk_post_cleanup_empty_dirs') else False,
            'strict_mode': self.chk_strict_mode.isChecked() if hasattr(self, 'chk_strict_mode') else False,
            'strict_max_errors': self.spin_strict_max_errors.value() if hasattr(self, 'spin_strict_max_errors') else 0,
        }

    def _apply_config(self: Any, config: dict):
        """Apply a configuration dictionary to the current UI."""
        # Folders
        if 'folders' in config:
            self.selected_folders = config['folders']
            self.list_folders.clear()
            for f in self.selected_folders:
                self.list_folders.addItem(f)
            self._on_folders_changed()
        
        # Basic filters
        if 'extensions' in config:
            self.txt_extensions.setText(config['extensions'])
        if 'min_size_kb' in config:
            self.spin_min_size.setValue(config['min_size_kb'])
        
        # 筌ｋ똾寃뺠쳸類ㅻ뮞
        if 'protect_system' in config:
            self.chk_protect_system.setChecked(config['protect_system'])
        if 'byte_compare' in config:
            self.chk_byte_compare.setChecked(config['byte_compare'])
        if 'same_name' in config:
            self.chk_same_name.setChecked(config['same_name'])
        if 'name_only' in config:
            self.chk_name_only.setChecked(config['name_only'])
        if 'skip_hidden' in config and hasattr(self, 'chk_skip_hidden'):
            self.chk_skip_hidden.setChecked(bool(config['skip_hidden']))
        if 'follow_symlinks' in config and hasattr(self, 'chk_follow_symlinks'):
            self.chk_follow_symlinks.setChecked(bool(config['follow_symlinks']))
        if 'use_trash' in config:
            self.chk_use_trash.setChecked(config['use_trash'])
        if 'use_similar_image' in config:
            self.chk_similar_image.setChecked(config['use_similar_image'])
        if 'use_mixed_mode' in config and hasattr(self, 'chk_mixed_mode'):
            self.chk_mixed_mode.setChecked(bool(config['use_mixed_mode']))
        if 'detect_duplicate_folders' in config and hasattr(self, 'chk_detect_folder_dup'):
            self.chk_detect_folder_dup.setChecked(bool(config['detect_duplicate_folders']))
        if 'incremental_rescan' in config and hasattr(self, 'chk_incremental_rescan'):
            self.chk_incremental_rescan.setChecked(bool(config['incremental_rescan']))
        if 'strict_mode' in config and hasattr(self, 'chk_strict_mode'):
            self.chk_strict_mode.setChecked(bool(config['strict_mode']))
        if 'strict_max_errors' in config and hasattr(self, 'spin_strict_max_errors'):
            try:
                self.spin_strict_max_errors.setValue(max(0, int(config['strict_max_errors'])))
            except Exception:
                self.spin_strict_max_errors.setValue(0)
        if 'similarity_threshold' in config:
            self.spin_similarity.setValue(config['similarity_threshold'])
        if 'use_similar_document' in config and hasattr(self, 'chk_similar_document'):
            self.chk_similar_document.setChecked(bool(config['use_similar_document']))
        if 'document_similarity_threshold' in config and hasattr(self, 'spin_document_similarity'):
            self.spin_document_similarity.setValue(float(config['document_similarity_threshold'] or 0.9))
        if 'selection_policy' in config and hasattr(self, 'cmb_selection_policy'):
            idx = self.cmb_selection_policy.findData(str(config.get('selection_policy') or 'smart'))
            self.cmb_selection_policy.setCurrentIndex(idx if idx >= 0 else 0)
        if 'compare_mode' in config and hasattr(self, 'cmb_compare_mode'):
            idx = self.cmb_compare_mode.findData(str(config.get('compare_mode') or 'none'))
            self.cmb_compare_mode.setCurrentIndex(idx if idx >= 0 else 0)
        if 'apply_exemptions' in config and hasattr(self, 'chk_apply_exemptions'):
            self.chk_apply_exemptions.setChecked(bool(config['apply_exemptions']))
        if 'post_cleanup_empty_dirs' in config and hasattr(self, 'chk_post_cleanup_empty_dirs'):
            self.chk_post_cleanup_empty_dirs.setChecked(bool(config['post_cleanup_empty_dirs']))
        if 'watch_mode' in config and hasattr(self, 'chk_watch_mode'):
            self.chk_watch_mode.setChecked(bool(config['watch_mode']))
        
        # Exclude patterns
        if 'exclude_patterns' in config:
            self.exclude_patterns = config['exclude_patterns']
            if self.exclude_patterns:
                self.btn_exclude_patterns.setText(
                    f"{strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})"
                )
            else:
                self.btn_exclude_patterns.setText(strings.tr("btn_exclude_patterns"))

        # Include patterns
        if 'include_patterns' in config:
            self.include_patterns = config['include_patterns']
            if hasattr(self, 'btn_include_patterns'):
                if self.include_patterns:
                    self.btn_include_patterns.setText(
                        f"{strings.tr('btn_include_patterns')} ({len(self.include_patterns)})"
                    )
                else:
                    self.btn_include_patterns.setText(strings.tr("btn_include_patterns"))

        self.refresh_incremental_baselines()
        if 'baseline_session_id' in config and hasattr(self, 'cmb_baseline_session'):
            try:
                sid = int(config.get('baseline_session_id') or 0)
            except Exception:
                sid = 0
            if sid > 0:
                idx = self.cmb_baseline_session.findData(sid)
                if idx >= 0:
                    self.cmb_baseline_session.setCurrentIndex(idx)
        self._sync_filter_states()

    def _apply_shortcuts(self: Any, shortcuts: dict):
        """Apply saved custom shortcuts to actions."""
        shortcut_map = {
            'start_scan': self.action_start_scan,
            'stop_scan': self.action_stop_scan,
            'undo': self.action_undo,
            'redo': self.action_redo,
            'delete_selected': self.action_delete_selected,
            'smart_select': self.action_smart_select,
            'export_csv': self.action_export_csv,
            'expand_all': self.action_expand_all,
            'collapse_all': self.action_collapse_all,
            'save_results': self.action_save_results,
            'load_results': self.action_load_results,
            'empty_finder': self.action_empty_finder,
            'toggle_theme': self.action_theme,
        }
        
        for action_id, shortcut in shortcuts.items():
            if action_id in shortcut_map and shortcut:
                shortcut_map[action_id].setShortcut(QKeySequence(shortcut))

    def _sync_advanced_visibility(self: Any, *_):
        """Show/hide advanced actions based on settings."""
        try:
            enabled = bool(getattr(self, "chk_enable_hardlink", None) and self.chk_enable_hardlink.isChecked())
        except Exception:
            enabled = False
        if hasattr(self, "btn_hardlink_checked"):
            self.btn_hardlink_checked.setVisible(enabled)

    def open_cache_db_folder(self: Any):
        """Open the folder containing the cache DB."""
        try:
            db_path = str(getattr(self.cache_manager, "db_path", "") or "")
        except Exception:
            db_path = ""
        folder = os.path.dirname(db_path) if db_path else ""
        if not folder:
            return
        try:
            if platform.system() == "Windows":
                os.startfile(folder)
            elif platform.system() == "Darwin":
                subprocess.call(("open", folder))
            else:
                subprocess.call(("xdg-open", folder))
        except Exception:
            pass

    def copy_cache_db_path(self: Any):
        """Copy cache DB path to clipboard."""
        try:
            db_path = str(getattr(self.cache_manager, "db_path", "") or "")
        except Exception:
            db_path = ""
        if db_path:
            self.copy_to_clipboard(db_path)

    def apply_cache_settings(self: Any):
        try:
            keep_latest = int(self.spin_cache_session_keep_latest.value()) if hasattr(self, "spin_cache_session_keep_latest") else 20
            hash_cleanup_days = int(self.spin_cache_hash_cleanup_days.value()) if hasattr(self, "spin_cache_hash_cleanup_days") else 30
            keep_latest = max(1, min(500, keep_latest))
            hash_cleanup_days = max(1, min(3650, hash_cleanup_days))

            self.settings.setValue("cache/session_keep_latest", keep_latest)
            self.settings.setValue("cache/hash_cleanup_days", hash_cleanup_days)

            self.cache_manager.cleanup_old_sessions(keep_latest=keep_latest)
            self.cache_manager.cleanup_old_entries(days_old=hash_cleanup_days)

            if hasattr(self, "toast_manager") and self.toast_manager:
                self.toast_manager.info(strings.tr("msg_settings_applied"), duration=2200)
        except Exception as e:
            _mw().QMessageBox.warning(self, strings.tr("app_title"), str(e))
