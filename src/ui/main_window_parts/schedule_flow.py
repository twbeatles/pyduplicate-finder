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



class MainWindowScheduleFlowMixin(DuplicateFinderTypingContract):
    def choose_schedule_output_folder(self: Any):
        path = QFileDialog.getExistingDirectory(self, strings.tr("btn_choose_folder"), "")
        if path and hasattr(self, "txt_schedule_output"):
            self.txt_schedule_output.setText(path)

    @staticmethod
    def _validate_schedule_time_hhmm(value: str) -> bool:
        raw = str(value or "").strip()
        return bool(re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", raw))

    def _sync_schedule_ui(self: Any):
        enabled = bool(hasattr(self, "chk_schedule_enabled") and self.chk_schedule_enabled.isChecked())
        weekly = bool(hasattr(self, "cmb_schedule_frequency") and str(self.cmb_schedule_frequency.currentData() or "daily") == "weekly")
        if hasattr(self, "cmb_schedule_weekday"):
            self.cmb_schedule_weekday.setEnabled(enabled and weekly)
        if hasattr(self, "lbl_schedule_weekday"):
            self.lbl_schedule_weekday.setEnabled(enabled and weekly)
        for wname in ("txt_schedule_time", "txt_schedule_output", "chk_schedule_export_json", "chk_schedule_export_csv", "btn_schedule_pick"):
            if hasattr(self, wname):
                getattr(self, wname).setEnabled(enabled)

    def _build_schedule_config(self: Any) -> ScheduleConfig:
        return self.scheduler_controller.build_config(
            enabled=bool(hasattr(self, "chk_schedule_enabled") and self.chk_schedule_enabled.isChecked()),
            schedule_type=str(self.cmb_schedule_frequency.currentData() if hasattr(self, "cmb_schedule_frequency") else "daily"),
            weekday=int(self.cmb_schedule_weekday.currentData() if hasattr(self, "cmb_schedule_weekday") else 0),
            time_hhmm=str(self.txt_schedule_time.text() if hasattr(self, "txt_schedule_time") else "03:00").strip() or "03:00",
        )

    def _build_schedule_config_from_context(self: Any) -> ScheduleConfig:
        ctx = dict(self._scheduled_run_context or {})
        return self.scheduler_controller.build_config(
            enabled=True,
            schedule_type=str(ctx.get("schedule_type") or "daily"),
            weekday=self._to_int(ctx.get("weekday"), 0),
            time_hhmm=str(ctx.get("time_hhmm") or "03:00").strip() or "03:00",
        )

    def _persist_schedule_job(self: Any):
        cfg = self._build_schedule_config()
        if not self._validate_schedule_time_hhmm(cfg.time_hhmm):
            raise ValueError(strings.tr("err_schedule_time_hhmm").format(value=cfg.time_hhmm))
        scan_cfg = self._get_current_config()
        try:
            self.scheduler_controller.persist_job(
                cache_manager=self.cache_manager,
                cfg=cfg,
                scan_config=scan_cfg,
                output_dir=str(self.txt_schedule_output.text() if hasattr(self, "txt_schedule_output") else "").strip(),
                output_json=bool(self.chk_schedule_export_json.isChecked() if hasattr(self, "chk_schedule_export_json") else True),
                output_csv=bool(self.chk_schedule_export_csv.isChecked() if hasattr(self, "chk_schedule_export_csv") else True),
            )
        except Exception:
            logger.exception("Failed to persist scheduled scan job")
            raise

    def apply_schedule_settings(self: Any):
        try:
            time_hhmm = str(self.txt_schedule_time.text() if hasattr(self, "txt_schedule_time") else "").strip()
            if not self._validate_schedule_time_hhmm(time_hhmm):
                msg = strings.tr("err_schedule_time_hhmm").format(value=time_hhmm or "")
                _mw().QMessageBox.warning(self, strings.tr("app_title"), msg)
                self.status_label.setText(msg)
                return
            self.save_settings()
            self._sync_schedule_ui()
            self._persist_schedule_job()
            if hasattr(self, "toast_manager") and self.toast_manager:
                self.toast_manager.info(strings.tr("msg_settings_applied"), duration=2200)
        except Exception as e:
            _mw().QMessageBox.warning(self, strings.tr("app_title"), str(e))

    def _scheduler_tick(self: Any):
        if self._scheduled_run_context:
            return
        is_scanning = bool(getattr(self, "btn_stop_scan", None) and self.btn_stop_scan.isEnabled())
        job, cfg = self.scheduler_controller.get_due_job(
            cache_manager=self.cache_manager,
            is_scanning=is_scanning,
        )
        if not job or not cfg:
            return

        snapshot_cfg = self.scheduler_controller.parse_scan_config(job)
        valid_folders, missing_folders = self.scheduler_controller.resolve_snapshot_folders(snapshot_cfg)
        if not valid_folders:
            self.scheduler_controller.record_skip_no_valid_folders(
                cache_manager=self.cache_manager,
                cfg=cfg,
            )
            return

        snapshot_cfg["folders"] = list(valid_folders)
        self._scheduled_run_context = self.scheduler_controller.build_run_context(
            job,
            cfg=cfg,
            scan_config=snapshot_cfg,
            valid_folders=valid_folders,
            missing_folders=missing_folders,
        ).as_dict()
        self._scheduled_job_run_id = self.scheduler_controller.create_job_run(
            cache_manager=self.cache_manager,
            session_id=self.current_session_id or 0,
        )
        self.start_scan(
            force_new=False,
            config_override=snapshot_cfg,
            folders_override=list(valid_folders),
            scheduled_context=dict(self._scheduled_run_context or {}),
        )

    def _scheduled_export_results(self: Any, results: dict):
        ctx = dict(self._scheduled_run_context or {})
        out_dir = str(ctx.get("output_dir") or "").strip()
        if not out_dir:
            return ("", "")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception:
            logger.warning("Scheduled export output dir is not writable: %s", out_dir, exc_info=True)
            return ("", "")

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_json = ""
        out_csv = ""
        try:
            if bool(ctx.get("output_json")):
                out_json = os.path.join(out_dir, f"scan_{stamp}.json")
                snapshot_folders = ctx.get("snapshot_folders")
                folders_payload = list(snapshot_folders) if isinstance(snapshot_folders, (list, tuple, set)) else []
                payload = dump_results_v2(
                    scan_results=results or {},
                    folders=folders_payload,
                    source="gui",
                )
                payload_meta = payload.setdefault("meta", {})
                payload_meta["scan_status"] = str(self._last_scan_status or "completed")
                payload_meta["metrics"] = dict(self._last_scan_metrics or {})
                payload_meta["warnings"] = list(self._last_scan_warnings or [])
                payload_meta["groups"] = int(len(results or {}))
                payload_meta["files"] = int(sum(len(v or []) for v in (results or {}).values()))
                with open(out_json, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.warning("Scheduled JSON export failed", exc_info=True)
            out_json = ""
        try:
            if bool(ctx.get("output_csv")):
                out_csv = os.path.join(out_dir, f"scan_{stamp}.csv")
                from src.ui.exporting import export_scan_results_csv

                export_scan_results_csv(
                    scan_results=results or {},
                    out_path=out_csv,
                    selected_paths=[],
                    file_meta=self._current_result_meta,
                    baseline_delta_map=self._current_baseline_delta_map,
                )
        except Exception:
            logger.warning("Scheduled CSV export failed", exc_info=True)
            out_csv = ""
        return (out_json, out_csv)

    def _finish_scheduled_run(self: Any, status: str, results: dict, message_override: str = ""):
        if not self._scheduled_run_context:
            return
        cfg = self._build_schedule_config_from_context()
        out_json = ""
        out_csv = ""
        if status in ("completed", "partial"):
            out_json, out_csv = self._scheduled_export_results(results or {})
        groups = len(results or {})
        files = sum(len(v or []) for v in (results or {}).values()) if results else 0
        message = str(message_override or status)
        try:
            self.scheduler_controller.finalize_run(
                cache_manager=self.cache_manager,
                run_id=self._scheduled_job_run_id,
                cfg=cfg,
                status=status,
                message=message,
                groups_count=groups,
                files_count=files,
                output_json_path=out_json,
                output_csv_path=out_csv,
            )
        except Exception:
            logger.exception("Failed to finish scheduled run bookkeeping")
        self._scheduled_job_run_id = 0
        self._scheduled_run_context = None
