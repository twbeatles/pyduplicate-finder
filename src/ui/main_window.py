from __future__ import annotations

import os
import json
import logging
from typing import Any

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtWidgets import QMainWindow, QMessageBox

from src.core.cache_manager import CacheManager
from src.core.file_lock_checker import FileLockChecker
from src.core.history import HistoryManager
from src.core.preset_manager import PresetManager
from src.core.preflight import PreflightAnalyzer
from src.core.quarantine_manager import QuarantineManager
from src.core.scan_engine import validate_similar_image_dependency
from src.ui.components.toast import ToastManager
from src.ui.controllers.navigation_controller import NavigationController
from src.ui.controllers.operation_flow_controller import OperationFlowController
from src.ui.controllers.ops_controller import OpsController
from src.ui.controllers.preview_controller import PreviewController
from src.ui.controllers.results_controller import ResultsController
from src.ui.controllers.scan_controller import ScanController
from src.ui.controllers.scheduler_controller import SchedulerController
from src.ui.main_window_parts.scan_flow import MainWindowScanFlowMixin
from src.ui.main_window_parts.results_flow import MainWindowResultsFlowMixin
from src.ui.main_window_parts.settings_flow import MainWindowSettingsFlowMixin
from src.ui.main_window_parts.schedule_flow import MainWindowScheduleFlowMixin
from src.ui.main_window_parts.tools_flow import MainWindowToolsFlowMixin
from src.ui.main_window_parts.typing_contract import DuplicateFinderTypingContract
from src.ui.main_window_parts.ui_shell import MainWindowUiShellMixin
from src.utils.i18n import strings

logger = logging.getLogger(__name__)


class DuplicateFinderApp(
    MainWindowUiShellMixin,
    MainWindowScanFlowMixin,
    MainWindowResultsFlowMixin,
    MainWindowSettingsFlowMixin,
    MainWindowScheduleFlowMixin,
    MainWindowToolsFlowMixin,
    QMainWindow,
):
    @staticmethod
    def _to_int(value: object, default: int = 0) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, (str, bytes, bytearray)):
            try:
                return int(value)
            except Exception:
                return int(default)
        return int(default)

    @staticmethod
    def _to_float(value: object, default: float = 0.0) -> float:
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, (str, bytes, bytearray)):
            try:
                return float(value)
            except Exception:
                return float(default)
        return float(default)

    @staticmethod
    def _json_loads(value: object, default: Any) -> Any:
        if isinstance(value, (str, bytes, bytearray)):
            try:
                return json.loads(value)
            except Exception:
                return default
        return default

    def __init__(self):
        super().__init__()
        self.setWindowTitle(strings.tr("app_title"))
        self.resize(1200, 850)
        self.selected_folders = []
        self.scan_results = {}
        self.cache_manager = CacheManager()
        self.quarantine_manager = QuarantineManager(self.cache_manager)
        self.history_manager = HistoryManager(cache_manager=self.cache_manager, quarantine_manager=self.quarantine_manager)
        self.current_session_id = None
        self._pending_selected_paths = []
        self._pending_selected_add = set()
        self._pending_selected_remove = set()
        self._saved_selected_paths = set()
        self._selection_save_timer = QTimer(self)
        self._selection_save_timer.setSingleShot(True)
        self._selection_save_timer.timeout.connect(self._flush_selected_paths)
        self._result_filter_timer = QTimer(self)
        self._result_filter_timer.setSingleShot(True)
        self._result_filter_timer.timeout.connect(self._apply_result_filter)
        self._pending_filter_text = ""

        # Initialize preset and lock-check related managers
        self.preset_manager = PresetManager()
        self.file_lock_checker = FileLockChecker()
        self.exclude_patterns = []
        self.include_patterns = []
        self.custom_shortcuts = {}

        # Quarantine / operations / rules
        self.preflight_analyzer = PreflightAnalyzer(lock_checker=self.file_lock_checker)
        self.selection_rules_json = []
        self.selection_rules = []
        self.scan_controller = ScanController()
        self.ops_controller = OpsController()
        self.scheduler_controller = SchedulerController()
        self.operation_flow_controller = OperationFlowController()
        self.navigation_controller = NavigationController()
        self.results_controller = ResultsController()
        self.preview_controller = PreviewController(self)
        self.preview_controller.preview_ready.connect(self._on_preview_ready, Qt.ConnectionType.QueuedConnection)
        self._preview_request_id = 0
        self._current_result_meta = {}
        self._current_result_existence_map = {}
        self._current_baseline_delta_map = {}
        self._last_scan_metrics = {}
        self._last_scan_status = "completed"
        self._last_scan_warnings = []
        self._previous_results = None
        self._previous_selected_paths = []
        self._previous_result_meta = {}
        self._previous_result_existence_map = {}
        self._previous_baseline_delta_map = {}

        self._op_worker = None
        self._op_progress = None
        self._op_queue = []
        self._scheduler_timer = QTimer(self)
        self._scheduler_timer.setInterval(60_000)
        self._scheduler_timer.timeout.connect(self._scheduler_tick)
        self._scheduled_run_context = None
        self._scheduled_job_run_id = 0

        self.init_ui()
        self.create_toolbar()

        # Toast Manager for notifications
        self.toast_manager = ToastManager(self)

        # Settings
        self.settings = QSettings("MySoft", "PyDuplicateFinderPro")
        self.load_settings()

        # Apply initial theme (defaults to light if not set)
        current_theme = self.settings.value("app/theme", "light")
        self.apply_theme(current_theme)

        # Apply initial language
        current_lang = self.settings.value("app/language", "ko")
        strings.set_language(current_lang)
        self.retranslate_ui()

        # Restore cached scan session/results if present
        self._restore_cached_session()
        # Populate maintenance data on startup (best-effort).
        try:
            self.refresh_quarantine_list()
            self.refresh_operations_list()
        except Exception:
            pass

        self._current_scan_stage_code = None

        # Enable drag and drop
        self.setAcceptDrops(True)

        # UX: warn once when enabling system trash (Undo not available)
        self.chk_use_trash.toggled.connect(self._on_use_trash_toggled)

        # Initial folder-dependent UI state
        self._on_folders_changed()
        self._scheduler_timer.start()

    def closeEvent(self, event):
        self.save_settings()
        self._flush_selected_paths()
        try:
            if hasattr(self, "preview_controller") and self.preview_controller:
                self.preview_controller.close()
        except Exception:
            pass
        try:
            if hasattr(self.history_manager, "cleanup"):
                self.history_manager.cleanup()
        except Exception:
            pass
        self.cache_manager.close_all()
        event.accept()
