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
from src.core.result_schema import dump_results_v3
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
        for wname in (
            "txt_schedule_time",
            "txt_schedule_output",
            "chk_schedule_export_json",
            "chk_schedule_export_csv",
            "btn_schedule_pick",
            "txt_schedule_job_name",
            "btn_schedule_new",
            "btn_schedule_run_now",
            "btn_schedule_refresh",
            "btn_schedule_delete",
            "tbl_schedule_jobs",
            "tbl_schedule_runs",
        ):
            if hasattr(self, wname):
                getattr(self, wname).setEnabled(enabled)

    def _current_schedule_job_name(self: Any) -> str:
        raw = ""
        if hasattr(self, "txt_schedule_job_name"):
            raw = str(self.txt_schedule_job_name.text() or "").strip()
        return raw or "default"

    def _selected_schedule_job(self: Any) -> dict:
        if not hasattr(self, "tbl_schedule_jobs"):
            return {}
        try:
            row = self.tbl_schedule_jobs.currentRow()
            if row < 0:
                return {}
            item = self.tbl_schedule_jobs.item(row, 0)
            if not item:
                return {}
            return dict(item.data(Qt.ItemDataRole.UserRole) or {})
        except Exception:
            return {}

    def prepare_new_schedule_job(self: Any):
        if hasattr(self, "tbl_schedule_jobs"):
            try:
                self.tbl_schedule_jobs.clearSelection()
            except Exception:
                pass
        if hasattr(self, "txt_schedule_job_name"):
            self.txt_schedule_job_name.setText(datetime.now().strftime("job_%Y%m%d_%H%M%S"))

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

    def _load_schedule_job_into_form(self: Any, job: dict):
        if not job:
            return
        if hasattr(self, "txt_schedule_job_name"):
            self.txt_schedule_job_name.setText(str(job.get("name") or "default"))
        if hasattr(self, "chk_schedule_enabled"):
            self.chk_schedule_enabled.setChecked(bool(job.get("enabled")))
        if hasattr(self, "cmb_schedule_frequency"):
            idx = self.cmb_schedule_frequency.findData(str(job.get("schedule_type") or "daily"))
            self.cmb_schedule_frequency.setCurrentIndex(idx if idx >= 0 else 0)
        if hasattr(self, "cmb_schedule_weekday"):
            idx = self.cmb_schedule_weekday.findData(int(job.get("weekday") or 0))
            self.cmb_schedule_weekday.setCurrentIndex(idx if idx >= 0 else 0)
        if hasattr(self, "txt_schedule_time"):
            self.txt_schedule_time.setText(str(job.get("time_hhmm") or "03:00"))
        if hasattr(self, "txt_schedule_output"):
            self.txt_schedule_output.setText(str(job.get("output_dir") or ""))
        if hasattr(self, "chk_schedule_export_json"):
            self.chk_schedule_export_json.setChecked(bool(job.get("output_json", True)))
        if hasattr(self, "chk_schedule_export_csv"):
            self.chk_schedule_export_csv.setChecked(bool(job.get("output_csv", True)))
        self._sync_schedule_ui()
        try:
            cfg = self.scheduler_controller.parse_scan_config(job)
            if cfg:
                self._apply_config(cfg)
        except Exception:
            logger.warning("Failed to apply schedule job scan config", exc_info=True)

    def _refresh_schedule_runs_view(self: Any, job_name: str = ""):
        if not hasattr(self, "tbl_schedule_runs"):
            return
        runs = self.cache_manager.list_scan_job_runs(job_name or None, limit=20)
        self.tbl_schedule_runs.setRowCount(len(runs))
        for row_idx, run in enumerate(runs):
            started = float(run.get("started_at") or 0.0)
            dt = datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M") if started else "-"
            self.tbl_schedule_runs.setItem(row_idx, 0, QTableWidgetItem(dt))
            self.tbl_schedule_runs.setItem(row_idx, 1, QTableWidgetItem(str(run.get("status") or "")))
            self.tbl_schedule_runs.setItem(row_idx, 2, QTableWidgetItem(str(int(run.get("groups_count") or 0))))
            self.tbl_schedule_runs.setItem(row_idx, 3, QTableWidgetItem(str(int(run.get("files_count") or 0))))
            self.tbl_schedule_runs.setItem(row_idx, 4, QTableWidgetItem(str(run.get("message") or "")))

    def refresh_schedule_jobs_view(self: Any):
        if not hasattr(self, "tbl_schedule_jobs"):
            return
        current_name = self._current_schedule_job_name()
        jobs = self.cache_manager.list_scan_jobs()
        self.tbl_schedule_jobs.setRowCount(len(jobs))
        selected_row = -1
        for row_idx, job in enumerate(jobs):
            next_run = float(job.get("next_run_at") or 0.0)
            next_label = datetime.fromtimestamp(next_run).strftime("%Y-%m-%d %H:%M") if next_run else "-"
            status = str(job.get("last_status") or ("enabled" if job.get("enabled") else "disabled"))
            name_item = QTableWidgetItem(str(job.get("name") or "default"))
            name_item.setData(Qt.ItemDataRole.UserRole, dict(job))
            self.tbl_schedule_jobs.setItem(row_idx, 0, name_item)
            self.tbl_schedule_jobs.setItem(row_idx, 1, QTableWidgetItem(status))
            self.tbl_schedule_jobs.setItem(row_idx, 2, QTableWidgetItem(str(job.get("schedule_type") or "daily")))
            self.tbl_schedule_jobs.setItem(row_idx, 3, QTableWidgetItem(str(job.get("time_hhmm") or "03:00")))
            self.tbl_schedule_jobs.setItem(row_idx, 4, QTableWidgetItem(next_label))
            if str(job.get("name") or "") == current_name:
                selected_row = row_idx

        if selected_row >= 0:
            self.tbl_schedule_jobs.selectRow(selected_row)
            self._refresh_schedule_runs_view(current_name)
        elif jobs:
            self.tbl_schedule_jobs.selectRow(0)
            self._refresh_schedule_runs_view(str(jobs[0].get("name") or "default"))
        else:
            self._refresh_schedule_runs_view("")

    def on_schedule_job_selection_changed(self: Any):
        job = self._selected_schedule_job()
        if not job:
            return
        self._load_schedule_job_into_form(job)
        self._refresh_schedule_runs_view(str(job.get("name") or "default"))

    def _persist_schedule_job(self: Any):
        cfg = self._build_schedule_config()
        if not self._validate_schedule_time_hhmm(cfg.time_hhmm):
            raise ValueError(strings.tr("err_schedule_time_hhmm").format(value=cfg.time_hhmm))
        scan_cfg = self._get_current_config()
        job_name = self._current_schedule_job_name()
        try:
            self.scheduler_controller.persist_job(
                cache_manager=self.cache_manager,
                cfg=cfg,
                scan_config=scan_cfg,
                output_dir=str(self.txt_schedule_output.text() if hasattr(self, "txt_schedule_output") else "").strip(),
                output_json=bool(self.chk_schedule_export_json.isChecked() if hasattr(self, "chk_schedule_export_json") else True),
                output_csv=bool(self.chk_schedule_export_csv.isChecked() if hasattr(self, "chk_schedule_export_csv") else True),
                job_name=job_name,
            )
            self.refresh_schedule_jobs_view()
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

    def delete_selected_schedule_job(self: Any):
        job = self._selected_schedule_job()
        if not job:
            return
        job_name = str(job.get("name") or "default")
        self.cache_manager.delete_scan_job(job_name)
        if hasattr(self, "txt_schedule_job_name") and self._current_schedule_job_name() == job_name:
            self.txt_schedule_job_name.setText("default")
        self.refresh_schedule_jobs_view()

    def _start_scheduled_job(self: Any, job: dict, cfg: ScheduleConfig):
        snapshot_cfg = self.scheduler_controller.parse_scan_config(job)
        valid_folders, missing_folders = self.scheduler_controller.resolve_snapshot_folders(snapshot_cfg)
        job_name = str(job.get("name") or "default")
        if not valid_folders:
            try:
                self.scheduler_controller.record_skip_no_valid_folders(
                    cache_manager=self.cache_manager,
                    cfg=cfg,
                    job_name=job_name,
                )
            except TypeError:
                # Preserve compatibility with older controller/test doubles that
                # do not accept the newer job_name keyword yet.
                self.scheduler_controller.record_skip_no_valid_folders(
                    cache_manager=self.cache_manager,
                    cfg=cfg,
                )
            self.refresh_schedule_jobs_view()
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
            job_name=job_name,
        )
        self.start_scan(
            force_new=False,
            config_override=snapshot_cfg,
            folders_override=list(valid_folders),
            scheduled_context=dict(self._scheduled_run_context or {}),
        )

    def run_selected_schedule_job_now(self: Any):
        if self._scheduled_run_context:
            return
        if bool(getattr(self, "btn_stop_scan", None) and self.btn_stop_scan.isEnabled()):
            return
        job = self._selected_schedule_job()
        if not job:
            job = self.cache_manager.get_scan_job(self._current_schedule_job_name()) or {}
        if not job:
            return
        cfg = self.scheduler_controller.build_config(
            enabled=True,
            schedule_type=str(job.get("schedule_type") or "daily"),
            weekday=int(job.get("weekday") or 0),
            time_hhmm=str(job.get("time_hhmm") or "03:00"),
        )
        self._start_scheduled_job(job, cfg)

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
        self._start_scheduled_job(job, cfg)

    def _scheduled_export_results(self: Any, results: dict):
        ctx = dict(self._scheduled_run_context or {})
        out_dir = str(ctx.get("output_dir") or "").strip()
        requested_exports = []
        if bool(ctx.get("output_json")):
            requested_exports.append("json")
        if bool(ctx.get("output_csv")):
            requested_exports.append("csv")
        if not out_dir:
            return ("", "", [])
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception:
            logger.warning("Scheduled export output dir is not writable: %s", out_dir, exc_info=True)
            return ("", "", requested_exports)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_json = ""
        out_csv = ""
        failed_exports: list[str] = []
        try:
            if bool(ctx.get("output_json")):
                out_json = os.path.join(out_dir, f"scan_{stamp}.json")
                snapshot_folders = ctx.get("snapshot_folders")
                folders_payload = list(snapshot_folders) if isinstance(snapshot_folders, (list, tuple, set)) else []
                payload = dump_results_v3(
                    scan_results=results or {},
                    folders=folders_payload,
                    source="gui",
                    selected_paths=[],
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
                payload_meta["groups"] = int(len(results or {}))
                payload_meta["files"] = int(sum(len(v or []) for v in (results or {}).values()))
                with open(out_json, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.warning("Scheduled JSON export failed", exc_info=True)
            out_json = ""
            failed_exports.append("json")
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
                    selection_reason_map=self._current_selection_reason_map,
                    exemption_status_map=self._current_exemption_status_map,
                    review_state_map=self._current_review_state_map,
                    collection_role_map=self._current_collection_role_map,
                )
        except Exception:
            logger.warning("Scheduled CSV export failed", exc_info=True)
            out_csv = ""
            failed_exports.append("csv")
        return (out_json, out_csv, failed_exports)

    def _finish_scheduled_run(self: Any, status: str, results: dict, message_override: str = ""):
        if not self._scheduled_run_context:
            return
        cfg = self._build_schedule_config_from_context()
        out_json = ""
        out_csv = ""
        failed_exports: list[str] = []
        if status in ("completed", "partial"):
            out_json, out_csv, failed_exports = self._scheduled_export_results(results or {})
        final_status = str(status or "completed")
        if failed_exports and final_status == "completed":
            final_status = "partial"
        groups = len(results or {})
        files = sum(len(v or []) for v in (results or {}).values()) if results else 0
        base_message = str(message_override or final_status)
        message_parts = [base_message]
        missing_count = len(list((self._scheduled_run_context or {}).get("missing_folders") or []))
        if missing_count > 0:
            message_parts.append(f"missing_folders:{missing_count}")
        if failed_exports:
            export_value = ",".join(sorted(dict.fromkeys(failed_exports)))
            message_parts.append(f"export_failed:{export_value}")
        message = ";".join(message_parts)
        try:
            self.scheduler_controller.finalize_run(
                cache_manager=self.cache_manager,
                run_id=self._scheduled_job_run_id,
                cfg=cfg,
                status=final_status,
                message=message,
                groups_count=groups,
                files_count=files,
                output_json_path=out_json,
                output_csv_path=out_csv,
                job_name=str((self._scheduled_run_context or {}).get("job_name") or "default"),
            )
        except Exception:
            logger.exception("Failed to finish scheduled run bookkeeping")
        self._scheduled_job_run_id = 0
        self._scheduled_run_context = None
        self.refresh_schedule_jobs_view()
