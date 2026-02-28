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

logger = logging.getLogger(__name__)


class DuplicateFinderApp(QMainWindow):
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
        
        # ??疫꿸퀡???온???紐꾨뮞??곷뮞 癰궰??
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
        self.preview_controller.preview_ready.connect(self._on_preview_ready, Qt.QueuedConnection)
        self._preview_request_id = 0
        self._current_result_meta = {}
        self._current_baseline_delta_map = {}
        self._last_scan_metrics = {}
        self._last_scan_status = "completed"
        self._last_scan_warnings = []

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

        # Drag & Drop ??뽮쉐??
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

    def _on_folders_changed(self):
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

    def _on_use_trash_toggled(self, checked: bool):
        if not checked:
            return
        try:
            warned = str(self.settings.value("ux/trash_warned", False)).lower() == "true"
        except Exception:
            warned = False

        if not warned:
            try:
                QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_trash_warning"))
            except Exception:
                pass
            self.settings.setValue("ux/trash_warned", True)
        elif hasattr(self, "toast_manager") and self.toast_manager:
            self.toast_manager.warning(strings.tr("msg_trash_warning"), duration=3500)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        added_count = 0
        for f in files:
            if os.path.isdir(f):
                self.add_path_to_list(f)
                added_count += 1
        
        if added_count > 0:
            self.status_label.setText(strings.tr("msg_n_folders_added").format(added_count))
            self._on_folders_changed()
        
        event.accept()

    def _create_separator(self):
        """Create a vertical separator line"""
        from PySide6.QtWidgets import QFrame
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        return sep

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # === MAIN HORIZONTAL LAYOUT: Sidebar | Content ===
        main_h_layout = QHBoxLayout(central_widget)
        main_h_layout.setSpacing(0)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        
        # === SIDEBAR NAVIGATION ===
        self.sidebar = Sidebar(self)
        self.sidebar.page_changed.connect(self._on_page_changed)
        main_h_layout.addWidget(self.sidebar)
        
        # === CONTENT AREA ===
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        main_h_layout.addWidget(content_widget, 1)
        
        # === STACKED WIDGET FOR PAGES ===
        self.page_stack = QStackedWidget()
        content_layout.addWidget(self.page_stack, 1)

        # === Pages (Scan / Results / Tools / Settings) ===
        self.scan_page = build_scan_page(self)
        self.page_stack.addWidget(self.scan_page)

        self.results_page = build_results_page(self)
        self.page_stack.addWidget(self.results_page)

        self.tools_page = build_tools_page(self)
        tools_scroll = QScrollArea()
        tools_scroll.setWidgetResizable(True)
        tools_scroll.setFrameShape(QScrollArea.NoFrame)
        tools_scroll.setWidget(self.tools_page)
        self.page_stack.addWidget(tools_scroll)

        self.settings_page = build_settings_page(self)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QScrollArea.NoFrame)
        settings_scroll.setWidget(self.settings_page)
        self.page_stack.addWidget(settings_scroll)

        # Scheduler controls
        if hasattr(self, "chk_schedule_enabled"):
            self.chk_schedule_enabled.toggled.connect(self._sync_schedule_ui)
        if hasattr(self, "cmb_schedule_frequency"):
            self.cmb_schedule_frequency.currentIndexChanged.connect(self._sync_schedule_ui)

        # === STATUS BAR (Outside stacked widget - always visible) ===
        status_container = QHBoxLayout()
        status_container.setContentsMargins(16, 8, 16, 8)
        status_container.setSpacing(16)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumWidth(200)
        self.progress_bar.setMaximumWidth(400)
        
        self.status_label = QLabel(strings.tr("status_ready"))
        self.status_label.setObjectName("status_label")
        
        status_container.addWidget(self.progress_bar)
        status_container.addWidget(self.status_label, 1)
        content_layout.addLayout(status_container)

    def retranslate_ui(self):
        """Dynamic text update for language switching"""
        self.setWindowTitle(strings.tr("app_title"))
        
        self.btn_add_folder.setText(strings.tr("btn_add_folder"))
        self.btn_add_drive.setText(strings.tr("btn_add_drive"))
        self.btn_clear_folder.setText(strings.tr("btn_clear"))
        self.btn_remove_folder.setText(strings.tr("btn_remove_folder"))
        self.btn_remove_folder.setToolTip(strings.tr("btn_remove_folder"))
        
        # Labels
        if hasattr(self, 'lbl_ext'):
            self.lbl_ext.setText(strings.tr("lbl_ext"))
        if hasattr(self, 'lbl_min_size'):
            self.lbl_min_size.setText(strings.tr("lbl_min_size"))
        if hasattr(self, 'lbl_filter_basic'):
            self.lbl_filter_basic.setText(strings.tr("hdr_filters_basic"))
        if hasattr(self, 'lbl_filter_compare'):
            self.lbl_filter_compare.setText(strings.tr("hdr_filters_compare"))
        if hasattr(self, 'lbl_filter_advanced'):
            self.lbl_filter_advanced.setText(strings.tr("hdr_filters_advanced"))
        
        self.txt_extensions.setPlaceholderText(strings.tr("ph_ext"))
        self.spin_min_size.setSuffix(" KB")
        self.chk_same_name.setText(strings.tr("chk_same_name"))
        self.chk_same_name.setToolTip(strings.tr("tip_same_name"))
        self.chk_name_only.setText(strings.tr("chk_name_only"))
        self.chk_name_only.setToolTip(strings.tr("tip_name_only"))
        self.chk_byte_compare.setText(strings.tr("chk_byte_compare"))
        self.chk_protect_system.setText(strings.tr("chk_protect_system"))
        self.chk_use_trash.setText(strings.tr("chk_use_trash"))
        self.chk_use_trash.setToolTip(strings.tr("tip_use_trash"))
        if hasattr(self, "chk_skip_hidden"):
            self.chk_skip_hidden.setText(strings.tr("chk_skip_hidden"))
            self.chk_skip_hidden.setToolTip(strings.tr("tip_skip_hidden"))
        if hasattr(self, "chk_follow_symlinks"):
            self.chk_follow_symlinks.setText(strings.tr("chk_follow_symlinks"))
            self.chk_follow_symlinks.setToolTip(strings.tr("tip_follow_symlinks"))
        self.chk_similar_image.setText(strings.tr("chk_similar_image"))
        self.chk_similar_image.setToolTip(strings.tr("tip_similar_image"))
        self.lbl_similarity.setText(strings.tr("lbl_similarity_threshold"))
        if hasattr(self, "lbl_filter_strategy"):
            self.lbl_filter_strategy.setText(strings.tr("hdr_filters_strategy"))
        if hasattr(self, "chk_mixed_mode"):
            self.chk_mixed_mode.setText(strings.tr("chk_mixed_mode"))
            self.chk_mixed_mode.setToolTip(strings.tr("tip_mixed_mode"))
        if hasattr(self, "chk_detect_folder_dup"):
            self.chk_detect_folder_dup.setText(strings.tr("chk_detect_folder_dup"))
            self.chk_detect_folder_dup.setToolTip(strings.tr("tip_detect_folder_dup"))
        if hasattr(self, "chk_incremental_rescan"):
            self.chk_incremental_rescan.setText(strings.tr("chk_incremental_rescan"))
            self.chk_incremental_rescan.setToolTip(strings.tr("tip_incremental_rescan"))
        if hasattr(self, "chk_strict_mode"):
            self.chk_strict_mode.setText(strings.tr("chk_strict_mode"))
            self.chk_strict_mode.setToolTip(strings.tr("tip_strict_mode"))
        if hasattr(self, "lbl_strict_max_errors"):
            self.lbl_strict_max_errors.setText(strings.tr("lbl_strict_max_errors"))
        if hasattr(self, "lbl_baseline_session"):
            self.lbl_baseline_session.setText(strings.tr("lbl_baseline_session"))
        if hasattr(self, "cmb_baseline_session"):
            self.refresh_incremental_baselines()
        if hasattr(self, "btn_include_patterns"):
            if self.include_patterns:
                self.btn_include_patterns.setText(
                    f"{strings.tr('btn_include_patterns')} ({len(self.include_patterns)})"
                )
            else:
                self.btn_include_patterns.setText(strings.tr("btn_include_patterns"))
        if hasattr(self, 'btn_exclude_patterns'):
            if self.exclude_patterns:
                self.btn_exclude_patterns.setText(
                    f"{strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})"
                )
            else:
                self.btn_exclude_patterns.setText(strings.tr("btn_exclude_patterns"))
        
        self.btn_start_scan.setText(strings.tr("btn_start_scan"))
        self.btn_stop_scan.setText(strings.tr("scan_stop"))
        if hasattr(self, "btn_go_results"):
            self.btn_go_results.setText(strings.tr("nav_results"))
        
        # New Feature: Filter Placeholder
        if hasattr(self, 'txt_result_filter'):
            self.txt_result_filter.setPlaceholderText("?뵇 " + strings.tr("ph_filter_results"))

        self.tree_widget.setHeaderLabels([strings.tr("col_path"), strings.tr("col_size"), strings.tr("col_mtime"), strings.tr("col_ext")])
        self.lbl_preview_header.setText(strings.tr("lbl_preview"))
        if hasattr(self, 'lbl_results_title'):
            self.lbl_results_title.setText(strings.tr("nav_results"))
        if hasattr(self, "btn_show_options"):
            self.btn_show_options.setText(strings.tr("btn_show_options"))
        if hasattr(self, 'lbl_results_empty'):
            self.lbl_results_empty.setText(strings.tr("msg_no_results"))
        if hasattr(self, "btn_results_empty_add_folder"):
            self.btn_results_empty_add_folder.setText(strings.tr("btn_add_folder"))
        if hasattr(self, "btn_results_empty_start_scan"):
            self.btn_results_empty_start_scan.setText(strings.tr("btn_start_scan"))
        if hasattr(self, 'lbl_results_page_title'):
            self.lbl_results_page_title.setText(strings.tr("nav_results"))
        if hasattr(self, 'lbl_results_hint'):
            self.lbl_results_hint.setText(strings.tr("msg_results_page_hint"))
        if hasattr(self, 'btn_go_scan'):
            self.btn_go_scan.setText(strings.tr("btn_go_scan"))
        if hasattr(self, 'lbl_tools_title'):
            self.lbl_tools_title.setText(strings.tr("nav_tools"))
        if hasattr(self, 'lbl_tools_hint'):
            self.lbl_tools_hint.setText(strings.tr("msg_tools_page_hint"))
        if hasattr(self, "btn_tools_go_scan"):
            self.btn_tools_go_scan.setText(strings.tr("btn_go_scan"))
        if hasattr(self, 'lbl_empty_title'):
            self.lbl_empty_title.setText(strings.tr("action_empty_finder"))
        if hasattr(self, 'lbl_empty_desc'):
            self.lbl_empty_desc.setText(strings.tr("msg_empty_finder_desc"))
        if hasattr(self, 'btn_empty_tools'):
            self.btn_empty_tools.setText(strings.tr("btn_scan_empty"))
        if hasattr(self, 'lbl_settings_title'):
            self.lbl_settings_title.setText(strings.tr("nav_settings"))
        if hasattr(self, 'lbl_settings_hint'):
            self.lbl_settings_hint.setText(strings.tr("msg_settings_page_hint"))
        if hasattr(self, 'lbl_theme_title'):
            self.lbl_theme_title.setText(strings.tr("action_theme"))
        if hasattr(self, 'btn_theme_settings'):
            self.btn_theme_settings.setText(strings.tr("action_theme"))
        if hasattr(self, 'lbl_shortcut_title'):
            self.lbl_shortcut_title.setText(strings.tr("action_shortcut_settings"))
        if hasattr(self, 'btn_shortcuts_settings'):
            self.btn_shortcuts_settings.setText(strings.tr("action_shortcut_settings"))
        if hasattr(self, 'lbl_preset_title'):
            self.lbl_preset_title.setText(strings.tr("action_preset"))
        if hasattr(self, 'btn_preset_settings'):
            self.btn_preset_settings.setText(strings.tr("btn_manage_presets"))
        if hasattr(self, "lbl_cache_title"):
            self.lbl_cache_title.setText(strings.tr("settings_cache_title"))
        if hasattr(self, "lbl_cache_desc"):
            self.lbl_cache_desc.setText(strings.tr("settings_cache_desc"))
        if hasattr(self, "btn_cache_open"):
            self.btn_cache_open.setText(strings.tr("ctx_open_folder"))
        if hasattr(self, "btn_cache_copy"):
            self.btn_cache_copy.setText(strings.tr("ctx_copy_path"))
        if hasattr(self, "lbl_cache_session_keep_latest"):
            self.lbl_cache_session_keep_latest.setText(strings.tr("settings_cache_session_keep_latest"))
        if hasattr(self, "lbl_cache_hash_cleanup_days"):
            self.lbl_cache_hash_cleanup_days.setText(strings.tr("settings_cache_hash_cleanup_days"))
        if hasattr(self, "spin_cache_hash_cleanup_days"):
            self.spin_cache_hash_cleanup_days.setSuffix(strings.tr("term_days_suffix"))
        if hasattr(self, "btn_cache_apply"):
            self.btn_cache_apply.setText(strings.tr("btn_apply"))

        # Tools: Quarantine / Rules / Ops
        if hasattr(self, "lbl_quarantine_title"):
            self.lbl_quarantine_title.setText(strings.tr("tool_quarantine_title"))
        if hasattr(self, "lbl_quarantine_desc"):
            self.lbl_quarantine_desc.setText(strings.tr("tool_quarantine_desc"))
        if hasattr(self, "txt_quarantine_search"):
            self.txt_quarantine_search.setPlaceholderText(strings.tr("ph_quarantine_search"))
        if hasattr(self, "btn_quarantine_refresh"):
            self.btn_quarantine_refresh.setText(strings.tr("btn_refresh"))
        if hasattr(self, "btn_quarantine_restore"):
            self.btn_quarantine_restore.setText(strings.tr("btn_restore_selected"))
        if hasattr(self, "btn_quarantine_purge"):
            self.btn_quarantine_purge.setText(strings.tr("btn_purge_selected"))
        if hasattr(self, "btn_quarantine_purge_all"):
            self.btn_quarantine_purge_all.setText(strings.tr("btn_purge_all"))
        if hasattr(self, "tbl_quarantine"):
            self.tbl_quarantine.setHorizontalHeaderLabels(
                [strings.tr("col_path"), strings.tr("col_size"), strings.tr("col_created"), strings.tr("col_status")]
            )

        if hasattr(self, "lbl_rules_title"):
            self.lbl_rules_title.setText(strings.tr("tool_rules_title"))
        if hasattr(self, "lbl_rules_desc"):
            self.lbl_rules_desc.setText(strings.tr("tool_rules_desc"))
        if hasattr(self, "btn_rules_edit"):
            self.btn_rules_edit.setText(strings.tr("btn_edit_rules"))
        if hasattr(self, "btn_rules_apply"):
            self.btn_rules_apply.setText(strings.tr("btn_apply_rules"))

        if hasattr(self, "lbl_ops_title"):
            self.lbl_ops_title.setText(strings.tr("tool_ops_title"))
        if hasattr(self, "btn_ops_refresh"):
            self.btn_ops_refresh.setText(strings.tr("btn_refresh"))
        if hasattr(self, "btn_ops_view"):
            self.btn_ops_view.setText(strings.tr("btn_view_details"))
        if hasattr(self, "tbl_ops"):
            self.tbl_ops.setHorizontalHeaderLabels(
                [strings.tr("col_id"), strings.tr("col_created"), strings.tr("col_type"), strings.tr("col_status"), strings.tr("col_message")]
            )
        if hasattr(self, "btn_hardlink_checked"):
            self.btn_hardlink_checked.setText(strings.tr("btn_hardlink_checked"))

        # Settings: Quarantine / Hardlink
        if hasattr(self, "lbl_quarantine_settings_title"):
            self.lbl_quarantine_settings_title.setText(strings.tr("settings_quarantine_title"))
        if hasattr(self, "chk_quarantine_enabled"):
            self.chk_quarantine_enabled.setText(strings.tr("settings_quarantine_enabled"))
        if hasattr(self, "lbl_quarantine_days"):
            self.lbl_quarantine_days.setText(strings.tr("settings_quarantine_days"))
        if hasattr(self, "lbl_quarantine_gb"):
            self.lbl_quarantine_gb.setText(strings.tr("settings_quarantine_gb"))
        if hasattr(self, "txt_quarantine_path"):
            self.txt_quarantine_path.setPlaceholderText(strings.tr("ph_quarantine_path"))
        if hasattr(self, "btn_quarantine_pick"):
            self.btn_quarantine_pick.setText(strings.tr("btn_choose_folder"))
        if hasattr(self, "btn_quarantine_apply"):
            self.btn_quarantine_apply.setText(strings.tr("btn_apply"))
        if hasattr(self, "lbl_hardlink_title"):
            self.lbl_hardlink_title.setText(strings.tr("settings_hardlink_title"))
        if hasattr(self, "chk_enable_hardlink"):
            self.chk_enable_hardlink.setText(strings.tr("settings_hardlink_enabled"))

        if hasattr(self, "lbl_schedule_title"):
            self.lbl_schedule_title.setText(strings.tr("settings_schedule_title"))
        if hasattr(self, "chk_schedule_enabled"):
            self.chk_schedule_enabled.setText(strings.tr("settings_schedule_enabled"))
        if hasattr(self, "lbl_schedule_frequency"):
            self.lbl_schedule_frequency.setText(strings.tr("settings_schedule_frequency"))
        if hasattr(self, "lbl_schedule_time"):
            self.lbl_schedule_time.setText(strings.tr("settings_schedule_time"))
        if hasattr(self, "lbl_schedule_weekday"):
            self.lbl_schedule_weekday.setText(strings.tr("settings_schedule_weekday"))
        if hasattr(self, "lbl_schedule_output"):
            self.lbl_schedule_output.setText(strings.tr("settings_schedule_output"))
        if hasattr(self, "chk_schedule_export_json"):
            self.chk_schedule_export_json.setText(strings.tr("settings_schedule_export_json"))
        if hasattr(self, "chk_schedule_export_csv"):
            self.chk_schedule_export_csv.setText(strings.tr("settings_schedule_export_csv"))
        if hasattr(self, "btn_schedule_pick"):
            self.btn_schedule_pick.setText(strings.tr("btn_choose_folder"))
        if hasattr(self, "btn_schedule_apply"):
            self.btn_schedule_apply.setText(strings.tr("btn_apply"))
        if hasattr(self, "cmb_schedule_frequency"):
            cur = self.cmb_schedule_frequency.currentData()
            self.cmb_schedule_frequency.setItemText(0, strings.tr("term_daily"))
            self.cmb_schedule_frequency.setItemText(1, strings.tr("term_weekly"))
            idx = self.cmb_schedule_frequency.findData(cur)
            if idx >= 0:
                self.cmb_schedule_frequency.setCurrentIndex(idx)
        if hasattr(self, "cmb_schedule_weekday"):
            cur = self.cmb_schedule_weekday.currentData()
            self.cmb_schedule_weekday.setItemText(0, strings.tr("term_weekday_mon"))
            self.cmb_schedule_weekday.setItemText(1, strings.tr("term_weekday_tue"))
            self.cmb_schedule_weekday.setItemText(2, strings.tr("term_weekday_wed"))
            self.cmb_schedule_weekday.setItemText(3, strings.tr("term_weekday_thu"))
            self.cmb_schedule_weekday.setItemText(4, strings.tr("term_weekday_fri"))
            self.cmb_schedule_weekday.setItemText(5, strings.tr("term_weekday_sat"))
            self.cmb_schedule_weekday.setItemText(6, strings.tr("term_weekday_sun"))
            idx = self.cmb_schedule_weekday.findData(cur)
            if idx >= 0:
                self.cmb_schedule_weekday.setCurrentIndex(idx)
        self._update_results_summary()
        if hasattr(self, "lbl_filter_count"):
            self.lbl_filter_count.setText("")
        
        if not self.lbl_image_preview.isVisible() and not self.txt_text_preview.isVisible():
            self.lbl_info_preview.setText(strings.tr("msg_select_file"))

        self.btn_select_smart.setText(strings.tr("btn_smart_select"))
        self.btn_select_smart.setToolTip(strings.tr("tip_smart_select"))
        
        # New Feature: Menu Actions
        if hasattr(self, 'action_smart'):
            self.action_smart.setText(strings.tr("btn_smart_select"))
        if hasattr(self, 'action_newest'):
            self.action_newest.setText(strings.tr("action_select_newest"))
            self.action_newest.setToolTip(strings.tr("tip_select_newest"))
        if hasattr(self, 'action_oldest'):
            self.action_oldest.setText(strings.tr("action_select_oldest"))
            self.action_oldest.setToolTip(strings.tr("tip_select_oldest"))
        if hasattr(self, 'action_pattern'):
            self.action_pattern.setText(strings.tr("action_select_pattern"))

        self.btn_export.setText(strings.tr("btn_export"))
        self.btn_delete.setText(strings.tr("btn_delete_selected"))
        
        if self.status_label.text() in ["Ready", "以鍮꾨맖"]:
             self.status_label.setText(strings.tr("status_ready"))
             
        # Toolbar Actions
        if hasattr(self, 'action_undo'):
            self.action_undo.setText(strings.tr("action_undo"))
        if hasattr(self, 'action_redo'):
            self.action_redo.setText(strings.tr("action_redo"))
        if hasattr(self, 'action_expand_all'):
            self.action_expand_all.setText(strings.tr("action_expand_all"))
            self.action_expand_all.setToolTip(strings.tr("action_expand_all"))
        if hasattr(self, 'action_collapse_all'):
            self.action_collapse_all.setText(strings.tr("action_collapse_all"))
            self.action_collapse_all.setToolTip(strings.tr("action_collapse_all"))
        if hasattr(self, 'action_save_results'):
            self.action_save_results.setText(strings.tr("action_save_results"))
        if hasattr(self, 'action_load_results'):
            self.action_load_results.setText(strings.tr("action_load_results"))
        if hasattr(self, 'action_start_scan'):
            self.action_start_scan.setText(strings.tr("action_start_scan"))
        if hasattr(self, 'action_stop_scan'):
            self.action_stop_scan.setText(strings.tr("action_stop_scan"))
        if hasattr(self, 'action_delete_selected'):
            self.action_delete_selected.setText(strings.tr("action_delete"))
        if hasattr(self, 'action_smart_select'):
            self.action_smart_select.setText(strings.tr("action_smart_select"))
        if hasattr(self, 'action_export_csv'):
            self.action_export_csv.setText(strings.tr("action_export"))
        if hasattr(self, 'action_shortcut_settings'):
            self.action_shortcut_settings.setText(strings.tr("action_shortcut_settings"))
        if hasattr(self, 'action_empty_finder'):
            self.action_empty_finder.setText(strings.tr("action_empty_finder"))
        if hasattr(self, 'action_theme'):
            self.action_theme.setText(strings.tr("action_theme"))
        if hasattr(self, 'menu_lang'):
            self.menu_lang.setTitle(strings.tr("menu_lang"))
        if hasattr(self, 'btn_lang'):
            self.btn_lang.setText(strings.tr("menu_lang"))
        if hasattr(self, 'action_lang_ko'):
            self.action_lang_ko.setText(strings.tr("lang_ko"))
        if hasattr(self, 'action_lang_en'):
            self.action_lang_en.setText(strings.tr("lang_en"))
        if hasattr(self, 'btn_preset'):
            self.btn_preset.setText(strings.tr("action_preset"))

        if hasattr(self, 'sidebar'):
            self.sidebar.retranslate()

        if hasattr(self, 'btn_filter_toggle'):
            self._toggle_filter_panel(self.btn_filter_toggle.isChecked())
        if hasattr(self, 'lbl_scan_stage'):
            self._set_scan_stage(self.status_label.text())

        # Re-apply derived labels after translation (counts, button suffixes)
        self._on_folders_changed()

    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Language Menu
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        # Actions
        self.action_undo = QAction(strings.tr("action_undo"), self)
        self.action_undo.setShortcut(QKeySequence.Undo)
        self.action_undo.triggered.connect(self.perform_undo)
        self.action_undo.setEnabled(False)
        toolbar.addAction(self.action_undo)

        self.action_redo = QAction(strings.tr("action_redo"), self)
        self.action_redo.setShortcut(QKeySequence.Redo)
        self.action_redo.triggered.connect(self.perform_redo)
        self.action_redo.setEnabled(False)
        toolbar.addAction(self.action_redo)

        # Hidden actions for keyboard shortcuts (UX: shortcuts should actually work)
        self.action_start_scan = QAction(strings.tr("action_start_scan"), self)
        self.action_start_scan.setShortcut(QKeySequence("Ctrl+Return"))
        self.action_start_scan.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.action_start_scan.triggered.connect(self.start_scan)
        self.addAction(self.action_start_scan)

        self.action_stop_scan = QAction(strings.tr("action_stop_scan"), self)
        self.action_stop_scan.setShortcut(QKeySequence("Escape"))
        self.action_stop_scan.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.action_stop_scan.triggered.connect(self.stop_scan)
        self.addAction(self.action_stop_scan)

        self.action_delete_selected = QAction(strings.tr("action_delete"), self)
        self.action_delete_selected.setShortcut(QKeySequence("Delete"))
        self.action_delete_selected.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.action_delete_selected.triggered.connect(self.delete_selected_files)
        self.addAction(self.action_delete_selected)

        self.action_smart_select = QAction(strings.tr("action_smart_select"), self)
        self.action_smart_select.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self.action_smart_select.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.action_smart_select.triggered.connect(self.select_duplicates_smart)
        self.addAction(self.action_smart_select)

        self.action_export_csv = QAction(strings.tr("action_export"), self)
        self.action_export_csv.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export_csv.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.action_export_csv.triggered.connect(self.export_results)
        self.addAction(self.action_export_csv)

        toolbar.addSeparator()
        
        # Expand/Collapse Actions
        self.action_expand_all = QAction(strings.tr("action_expand_all"), self)
        self.action_expand_all.setToolTip(strings.tr("action_expand_all"))
        self.action_expand_all.triggered.connect(self.tree_widget.expandAll)
        toolbar.addAction(self.action_expand_all)
        
        self.action_collapse_all = QAction(strings.tr("action_collapse_all"), self)
        self.action_collapse_all.setToolTip(strings.tr("action_collapse_all"))
        self.action_collapse_all.triggered.connect(self.tree_widget.collapseAll)
        toolbar.addAction(self.action_collapse_all)
        
        toolbar.addSeparator()
        
        # 野껉퀗???????븍뜄???븍┛
        self.action_save_results = QAction(strings.tr("action_save_results"), self)
        self.action_save_results.setShortcut(QKeySequence.Save)
        self.action_save_results.triggered.connect(self.save_scan_results)
        toolbar.addAction(self.action_save_results)
        
        self.action_load_results = QAction(strings.tr("action_load_results"), self)
        self.action_load_results.setShortcut(QKeySequence.Open)
        self.action_load_results.triggered.connect(self.load_scan_results)
        toolbar.addAction(self.action_load_results)
        
        toolbar.addSeparator()

        self.action_empty_finder = QAction(strings.tr("action_empty_finder"), self)
        self.action_empty_finder.triggered.connect(self.open_empty_finder)
        toolbar.addAction(self.action_empty_finder)

        self.action_theme = QAction(strings.tr("action_theme"), self)
        self.action_theme.setCheckable(True)
        self.action_theme.triggered.connect(self.toggle_theme)
        toolbar.addAction(self.action_theme)
        
        toolbar.addSeparator()
        
        # ?袁ⓥ봺??筌롫뗀??
        self.btn_preset = QToolButton(self)
        self.btn_preset.setText(strings.tr("action_preset"))
        self.btn_preset.setPopupMode(QToolButton.InstantPopup)
        
        self.menu_preset = QMenu(self)
        action_save_preset = QAction(strings.tr("btn_save_preset"), self)
        action_save_preset.triggered.connect(self.open_preset_dialog)
        self.menu_preset.addAction(action_save_preset)
        
        action_manage_presets = QAction(strings.tr("btn_manage_presets"), self)
        action_manage_presets.triggered.connect(self.open_preset_dialog)
        self.menu_preset.addAction(action_manage_presets)
        
        self.btn_preset.setMenu(self.menu_preset)
        toolbar.addWidget(self.btn_preset)
        
        # ??ν뀧????쇱젟
        self.action_shortcut_settings = QAction(strings.tr("action_shortcut_settings"), self)
        self.action_shortcut_settings.triggered.connect(self.open_shortcut_settings)
        toolbar.addAction(self.action_shortcut_settings)
        
        toolbar.addSeparator()
        
        # Language Button with Menu
        self.btn_lang = QToolButton(self)
        self.btn_lang.setText(strings.tr("menu_lang"))
        self.btn_lang.setPopupMode(QToolButton.InstantPopup)
        
        self.menu_lang = QMenu(self)
        
        self.action_lang_ko = QAction(strings.tr("lang_ko"), self)
        self.action_lang_ko.triggered.connect(lambda: self.change_language("ko"))
        self.menu_lang.addAction(self.action_lang_ko)
        
        self.action_lang_en = QAction(strings.tr("lang_en"), self)
        self.action_lang_en.triggered.connect(lambda: self.change_language("en"))
        self.menu_lang.addAction(self.action_lang_en)
        
        self.btn_lang.setMenu(self.menu_lang)
        toolbar.addWidget(self.btn_lang)

    def change_language(self, lang_code):
        strings.set_language(lang_code)
        self.retranslate_ui()
        self.settings.setValue("app/language", lang_code)
        
        # theme might depend on language? Unlikely but good to refresh if needed.

    def open_empty_finder(self):
        if not self.selected_folders:
            QMessageBox.warning(self, strings.tr("msg_title_notice"), strings.tr("msg_add_folder_first"))
            return
        
        dlg = EmptyFolderDialog(self.selected_folders, self)
        dlg.exec()


    def apply_theme(self, theme_name):
        style = ModernTheme.get_stylesheet(theme_name)
        self.setStyleSheet(style)
        self.settings.setValue("app/theme", theme_name)
        
        # Propagate to custom widgets
        self.tree_widget.set_theme_mode(theme_name)
        if hasattr(self, "sidebar"):
            try:
                self.sidebar.apply_theme(theme_name)
            except Exception:
                pass
        if hasattr(self, "toast_manager") and self.toast_manager:
            try:
                self.toast_manager.set_theme_mode(theme_name)
            except Exception:
                pass
        
        # Action state update
        if hasattr(self, 'action_theme'):
             self.action_theme.setChecked(theme_name == "dark")
        if hasattr(self, 'btn_theme_settings'):
             self.btn_theme_settings.setChecked(theme_name == "dark")

    def toggle_theme(self, checked):
        self.apply_theme("dark" if checked else "light")
    
    def _toggle_filter_panel(self, checked):
        """Toggle visibility of the filter panel with animation"""
        self.filter_container.setVisible(checked)
        arrow = "▲" if checked else "▼"
        self.btn_filter_toggle.setText(strings.tr("lbl_filter_options") + " " + arrow)

    def _sync_filter_states(self, *_):
        name_only = self.chk_name_only.isChecked()
        mixed_mode = bool(hasattr(self, "chk_mixed_mode") and self.chk_mixed_mode.isChecked())
        if name_only:
            self.chk_same_name.setChecked(False)
            self.chk_byte_compare.setChecked(False)
            self.chk_similar_image.setChecked(False)
            if hasattr(self, "chk_mixed_mode"):
                self.chk_mixed_mode.setChecked(False)
            if hasattr(self, "chk_detect_folder_dup"):
                self.chk_detect_folder_dup.setChecked(False)

        if mixed_mode:
            self.chk_similar_image.setChecked(True)
            self.chk_name_only.setChecked(False)

        self.chk_same_name.setEnabled(not name_only)
        self.chk_byte_compare.setEnabled(not name_only)
        self.chk_similar_image.setEnabled((not name_only) and (not mixed_mode))
        if hasattr(self, "chk_mixed_mode"):
            self.chk_mixed_mode.setEnabled(not name_only)
        if hasattr(self, "chk_detect_folder_dup"):
            self.chk_detect_folder_dup.setEnabled(not name_only)
        self.spin_similarity.setEnabled(self.chk_similar_image.isChecked() and not name_only)
        if hasattr(self, "chk_strict_mode") and hasattr(self, "spin_strict_max_errors"):
            use_strict = bool(self.chk_strict_mode.isChecked())
            self.spin_strict_max_errors.setEnabled(use_strict)
            if hasattr(self, "lbl_strict_max_errors"):
                self.lbl_strict_max_errors.setEnabled(use_strict)

        if hasattr(self, "chk_incremental_rescan") and hasattr(self, "cmb_baseline_session"):
            use_incremental = self.chk_incremental_rescan.isChecked()
            self.cmb_baseline_session.setEnabled(use_incremental)
            if hasattr(self, "lbl_baseline_session"):
                self.lbl_baseline_session.setEnabled(use_incremental)

    def refresh_incremental_baselines(self):
        if not hasattr(self, "cmb_baseline_session"):
            return
        current = self._get_selected_baseline_session_id()
        self.cmb_baseline_session.blockSignals(True)
        self.cmb_baseline_session.clear()
        self.cmb_baseline_session.addItem(strings.tr("opt_select"), 0)
        try:
            cfg = self._get_current_config()
            hash_cfg = self._get_scan_hash_config(cfg)
            cfg_hash = self.cache_manager.get_config_hash(hash_cfg)
            sessions = self.cache_manager.list_completed_sessions_by_hash(cfg_hash, limit=20)
            for s in sessions:
                sid = int(s.get("id") or 0)
                ts = float(s.get("updated_at") or 0.0)
                dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "-"
                msg = str(s.get("progress_message") or "").strip()
                label = f"#{sid} - {dt}"
                if msg:
                    label = f"{label} - {msg}"
                self.cmb_baseline_session.addItem(label, sid)
        except Exception:
            pass
        target = int(current or 0)
        idx = self.cmb_baseline_session.findData(target) if target else -1
        if idx < 0 and self.cmb_baseline_session.count() > 1:
            idx = 1
        if idx >= 0:
            self.cmb_baseline_session.setCurrentIndex(idx)
        self.cmb_baseline_session.blockSignals(False)

    def _get_selected_baseline_session_id(self):
        if not hasattr(self, "cmb_baseline_session"):
            return None
        try:
            sid = int(self.cmb_baseline_session.currentData() or 0)
            return sid if sid > 0 else None
        except Exception:
            return None

    def _set_scan_stage(self, message):
        if not hasattr(self, "lbl_scan_stage"):
            return
        stage = message or ""
        for sep in (":", "("):
            if sep in stage:
                stage = stage.split(sep, 1)[0]
        stage = stage.strip() or strings.tr("status_ready")
        self.lbl_scan_stage.setText(
            strings.tr("msg_scan_stage").format(stage=stage)
        )

    def _set_scan_stage_code(self, stage_code: str):
        """Set stage badge from a structured stage code (preferred over parsing)."""
        self._current_scan_stage_code = stage_code
        if not hasattr(self, "lbl_scan_stage"):
            return
        code = (stage_code or "").strip()
        stage_map = {
            "collecting": strings.tr("status_collecting_files"),
            "collected": strings.tr("status_collecting_files"),
            "incremental_index": strings.tr("status_incremental_index"),
            "analyzing": strings.tr("status_analyzing"),
            "hashing": strings.tr("status_hashing"),
            "similar_image": strings.tr("status_similar_image_scan"),
            "grouping": strings.tr("status_grouping"),
            "folder_dup": strings.tr("status_folder_dup"),
            "completed": strings.tr("status_done"),
            "error": strings.tr("status_error"),
            "abandoned": strings.tr("status_abandoned"),
        }
        label = stage_map.get(code, code or strings.tr("status_ready"))
        self.lbl_scan_stage.setText(strings.tr("msg_scan_stage").format(stage=label))

    # --- 疫꿸퀡???닌뗭겱: ??뺤뵬????獄?????---

    def add_path_to_list(self, path):
        path = os.path.normpath(path)
        if path not in self.selected_folders:
            self.selected_folders.append(path)
            self.list_folders.addItem(path)
            self._on_folders_changed()

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, strings.tr("btn_add_folder"))
        if folder:
            self.add_path_to_list(folder)

    def add_drive_dialog(self):
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

    def clear_folders(self):
        self.selected_folders = []
        self.list_folders.clear()
        self._on_folders_changed()

    def remove_selected_folder(self):
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

    # --- 湲곕뒫 援ы쁽: ?ㅼ틪 ---
    # --- 湲곕뒫 援ы쁽: ?ㅼ틪 ---
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
            QMessageBox.warning(self, strings.tr("app_title"), strings.tr("err_no_folder"))
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
                QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_incremental_no_baseline"))
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
        dep_error_key = validate_similar_image_dependency(scan_cfg)
        if dep_error_key:
            msg = strings.tr(dep_error_key)
            if self._scheduled_run_context and self._scheduled_job_run_id:
                self._finish_scheduled_run("failed", {}, message_override="similar_dependency_missing")
                return
            QMessageBox.warning(self, strings.tr("app_title"), msg)
            return

        resumable = None
        if not force_new:
            resumable = self.cache_manager.find_resumable_session_by_hash(config_hash)
        session_id = None
        use_cached_files = False

        if resumable:
            session_id = resumable.get("id")
            use_cached_files = resumable.get("stage") in ("collected", "hashing", "completed")
            if not use_cached_files:
                self.cache_manager.clear_scan_files(session_id)

            # Keep session metadata aligned with current settings (even if config_hash matches).
            try:
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

        self.tree_widget.clear()
        self.scan_results = {}
        self._current_result_meta = {}
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

    def stop_scan(self):
        if hasattr(self, 'worker'):
            self.worker.stop()
            self.status_label.setText(strings.tr("status_stopping"))
            self._set_scan_stage(strings.tr("status_stopping"))
            try:
                self.btn_stop_scan.setEnabled(False)
            except Exception:
                pass

    def toggle_ui_state(self, scanning):
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

    @Slot(int, str)
    def update_progress(self, val, msg):
        self.progress_bar.setValue(val)
        self.status_label.setText(msg)
        # Prefer structured stage codes if available; fallback to parsing message.
        if self._current_scan_stage_code:
            self._set_scan_stage_code(self._current_scan_stage_code)
        else:
            self._set_scan_stage(msg)

    @Slot(str)
    def on_scan_stage_changed(self, stage_code: str):
        self._set_scan_stage_code(stage_code)

    @Slot(dict)
    def on_scan_finished(self, results):
        self.scan_results = results
        self._previous_results = None
        self._previous_selected_paths = []
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

    @Slot()
    def on_scan_cancelled(self):
        """Issue #3: Handle scan cancellation - preserve previous results"""
        self._set_scan_stage(strings.tr("status_stopped"))
        self._current_scan_stage_code = None
        self.toggle_ui_state(scanning=False)
        self.progress_bar.setValue(0)
        self.status_label.setText(strings.tr("status_stopped"))
        if getattr(self, "_previous_results", None):
            self.scan_results = self._previous_results
            self._render_results(
                self.scan_results,
                selected_paths=self._previous_selected_paths,
                selected_count=len(self._previous_selected_paths),
            )
        else:
            self._set_results_view(False)
            self._update_results_summary(0)
            self._update_action_buttons_state(selected_count=0)
        self._finish_scheduled_run("cancelled", {})

    @Slot(str)
    def on_scan_failed(self, message):
        self._set_scan_stage(strings.tr("status_stopped"))
        self._current_scan_stage_code = None
        self.toggle_ui_state(scanning=False)
        self.progress_bar.setValue(0)
        err_msg = strings.tr("err_scan_failed").format(message)
        self.status_label.setText(err_msg)
        if getattr(self, "_previous_results", None):
            self.scan_results = self._previous_results
            self._render_results(
                self.scan_results,
                selected_paths=self._previous_selected_paths,
                selected_count=len(self._previous_selected_paths),
            )
        else:
            self._set_results_view(False)
            self._update_results_summary(0)
            self._update_action_buttons_state(selected_count=0)
        self._finish_scheduled_run("failed", {})
        QMessageBox.critical(self, strings.tr("app_title"), err_msg)

    def populate_tree(self, results):
        self._render_results(results, selected_paths=[])


    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024: return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def open_file(self, item, column):
        path = item.data(0, Qt.UserRole)
        if path and os.path.exists(path):
            if platform.system() == 'Windows':
                os.startfile(path)
            elif platform.system() == 'Darwin':
                subprocess.call(('open', path))
            else:
                subprocess.call(('xdg-open', path))

    def export_results(self):
        if not self.scan_results:
            QMessageBox.warning(self, strings.tr("app_title"), strings.tr("msg_no_results"))
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
            )
            QMessageBox.information(self, strings.tr("status_done"), strings.tr("status_done") + f":\n{path}")
        except Exception as e:
            QMessageBox.critical(self, strings.tr("app_title"), strings.tr("err_save").format(e))

    # --- 疫꿸퀡???닌뗭겱: ?醫뤾문 獄?????(Undo/Redo ??釉? ---
    def _group_entries_with_items(self, group):
        entries = []
        for j in range(group.childCount()):
            item = group.child(j)
            path = item.data(0, Qt.UserRole)
            if not path:
                continue
            path = str(path)
            mtime = 0.0
            try:
                mtime = float(item.data(2, Qt.UserRole) or 0.0)
            except Exception:
                pass
            if not mtime:
                try:
                    mtime = float((self._current_result_meta.get(path) or (0, 0.0))[1] or 0.0)
                except Exception:
                    mtime = 0.0
            entries.append((ResultEntry(path=path, mtime=mtime), item))
        return entries

    def _apply_keep_set_to_group(self, group, keep_set: set[str]):
        for _entry, item in self._group_entries_with_items(group):
            p = item.data(0, Qt.UserRole)
            if not p:
                continue
            item.setCheckState(0, Qt.Unchecked if str(p) in keep_set else Qt.Checked)

    def _mtime_for_path(self, path: str) -> float:
        try:
            meta = self._current_result_meta.get(str(path))
            if meta and len(meta) >= 2:
                return float(meta[1] or 0.0)
        except Exception:
            pass
        return 0.0

    def select_duplicates_smart(self):
        root = self.tree_widget.invisibleRootItem()
        self.tree_widget.begin_bulk_check_update()
        try:
            for i in range(root.childCount()):
                group = root.child(i)
                entries = [e for e, _ in self._group_entries_with_items(group)]
                keep_set, _ = self.results_controller.build_keep_delete(entries, strategy="smart")
                self._apply_keep_set_to_group(group, keep_set)
        finally:
            self.tree_widget.end_bulk_check_update()

    def select_duplicates_newest(self):
        """Keep Oldest, Select Newest (Date based)"""
        root = self.tree_widget.invisibleRootItem()
        self.tree_widget.begin_bulk_check_update()
        try:
            for i in range(root.childCount()):
                group = root.child(i)
                entries = [e for e, _ in self._group_entries_with_items(group)]
                keep_set, _ = self.results_controller.build_keep_delete(entries, strategy="oldest")
                self._apply_keep_set_to_group(group, keep_set)
        finally:
            self.tree_widget.end_bulk_check_update()

    def select_duplicates_oldest(self):
        """Keep Newest, Select Oldest (Date based)"""
        root = self.tree_widget.invisibleRootItem()
        self.tree_widget.begin_bulk_check_update()
        try:
            for i in range(root.childCount()):
                group = root.child(i)
                entries = [e for e, _ in self._group_entries_with_items(group)]
                keep_set, _ = self.results_controller.build_keep_delete(entries, strategy="newest")
                self._apply_keep_set_to_group(group, keep_set)
        finally:
            self.tree_widget.end_bulk_check_update()

    def select_duplicates_by_pattern(self):
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
                    path = item.data(0, Qt.UserRole) or ""
                    path = path.lower()
                    if pattern in path:
                        item.setCheckState(0, Qt.Checked)
                        count += 1
        finally:
            self.tree_widget.end_bulk_check_update()
        
        self.status_label.setText(
            strings.tr("msg_selected_pattern").format(count=count, pattern=text)
        )

    def on_result_filter_text_changed(self, text):
        self._pending_filter_text = str(text or "")
        self._result_filter_timer.start(120)

    def _apply_result_filter(self):
        self.filter_results_tree(self._pending_filter_text)

    def filter_results_tree(self, text):
        """Filter the result tree by filename/path."""
        visible_files, total_files = self.tree_widget.apply_filter(text)
        if hasattr(self, "lbl_filter_count"):
            if total_files == 0:
                self.lbl_filter_count.setText("")
            else:
                self.lbl_filter_count.setText(
                    strings.tr("msg_filter_count").format(visible=visible_files, total=total_files)
                )
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
        selected_count: int = None,
    ):
        selected = list(selected_paths or [])
        self._current_result_meta = dict(file_meta or {})
        self.tree_widget.populate(
            results,
            selected_paths=selected,
            file_meta=self._current_result_meta,
            existence_map=existence_map,
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

    def delete_selected_files(self):
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
                if item.checkState(0) == Qt.Checked:
                    targets.append(item.data(0, Qt.UserRole))
                    group_sel += 1
                    try:
                        group_bytes += int(item.data(1, Qt.UserRole) or 0)
                    except Exception:
                        pass
                    if not item.isHidden():
                        visible_checked += 1
            if group_sel > 0:
                group_rows.append((group.text(0), group_sel, group_bytes))

        if not targets:
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_files_selected"))
            return

        # ???뵬 ?醫됲닊 筌ｋ똾寃?
        locked_files = self.file_lock_checker.get_locked_files(targets)
        if locked_files:
            locked_list = "\n".join(locked_files[:5])
            if len(locked_files) > 5:
                locked_list += f"\n... and {len(locked_files) - 5} more"
            QMessageBox.warning(
                self, strings.tr("app_title"),
                f"{strings.tr('msg_file_locked')}\n\n{locked_list}"
            )
            # ?醫됰┸ ???뵬 ??뽰뇚
            targets = [t for t in targets if t not in locked_files]
            if not targets:
                return

        # ??????????類ㅼ뵥
        use_trash = self.chk_use_trash.isChecked()

        # Use persistent quarantine for undoable deletes if enabled.
        quarantine_enabled = str(self.settings.value("quarantine/enabled", True)).lower() == "true"
        if use_trash:
            op_type = "delete_trash"
        else:
            op_type = "delete_quarantine" if quarantine_enabled else "delete_trash"
            if not quarantine_enabled:
                QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_quarantine_disabled_fallback"))

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

    def _show_delete_dry_run(self, group_rows, *, total_selected: int, visible_checked: int, filter_active: bool):
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

            QMessageBox.information(
                self,
                strings.tr("msg_delete_dry_run_title"),
                "\n".join(lines),
            )
        except Exception:
            pass

    def perform_undo(self):
        self._start_operation(Operation("undo"))

    def perform_redo(self):
        self._start_operation(Operation("redo"))
    
    def _remove_paths_from_results(self, deleted_paths):
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

    def _prune_missing_results(self):
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

    def _prune_missing_results_after_restore(self):
        if not self.current_session_id or not self.scan_results:
            return
        if not self._prune_missing_results():
            return
        selected_paths = [p for p in self._saved_selected_paths if os.path.exists(p)]
        self._render_results(self.scan_results, selected_paths=selected_paths, selected_count=len(selected_paths))
        self.cache_manager.save_scan_results(self.current_session_id, self.scan_results)
        self.cache_manager.save_selected_paths(self.current_session_id, selected_paths)

    def update_undo_redo_buttons(self):
        self.action_undo.setEnabled(bool(self.history_manager.undo_stack))
        self.action_redo.setEnabled(bool(self.history_manager.redo_stack))

    # --- 疫꿸퀡???닌뗭겱: 沃섎챶?곮퉪?용┛ ---
    def update_preview(self, current, previous):
        if not current:
            return

        path = current.data(0, Qt.UserRole)
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

    def _on_preview_ready(self, payload):
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
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
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
            font.setStyleHint(QFont.Monospace)
            font.setPointSize(10)
            self.txt_text_preview.setFont(font)
            self.txt_text_preview.show()
            self.lbl_image_preview.hide()
            self.lbl_info_preview.hide()
            return

        self._set_preview_info(path, size=size, mtime=mtime)
        self.show_preview_info(strings.tr("msg_preview_unavailable"), keep_info=True)

    def show_preview_info(self, msg, keep_info=False):
        self.lbl_image_preview.hide()
        self.txt_text_preview.hide()
        self.lbl_info_preview.setText(msg)
        self.lbl_info_preview.show()
        if keep_info:
            self.preview_info.show()
        else:
            self.preview_info.hide()

    def _set_preview_info(self, path, is_folder=False, size=None, mtime=None):
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

    # --- 疫꿸퀡???닌뗭겱: ??쇱젟 ????嚥≪뮆諭?---
    def save_settings(self):
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
        self.settings.setValue("folders", self.selected_folders)
        
        # ??ν뀧??????
        if self.custom_shortcuts:
            self.settings.setValue("app/shortcuts", json.dumps(self.custom_shortcuts))
        
        # ???쉘 ????(??筌뤴뫖以?????館鍮????곸읈 揶쏅????類ㅻ뼄??筌왖??)
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
            if hasattr(self, "chk_schedule_export_json"):
                self.settings.setValue("schedule/output_json", bool(self.chk_schedule_export_json.isChecked()))
            if hasattr(self, "chk_schedule_export_csv"):
                self.settings.setValue("schedule/output_csv", bool(self.chk_schedule_export_csv.isChecked()))
        except Exception:
            pass

    def load_settings(self):
        geo = self.settings.value("app/geometry")
        if geo: self.restoreGeometry(geo)
        
        state = self.settings.value("app/splitter")
        if state: self.splitter.restoreState(state)
        
        self.txt_extensions.setText(self.settings.value("filter/extensions", ""))
        
        val = self.settings.value("filter/min_size", 0)
        self.spin_min_size.setValue(int(val) if val else 0)
        
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
            try:
                strict_max = int(self.settings.value("filter/strict_max_errors", 0) or 0)
            except Exception:
                strict_max = 0
            self.spin_strict_max_errors.setValue(max(0, strict_max))
        similarity = self.settings.value("filter/similarity_threshold", 0.9)
        try:
            self.spin_similarity.setValue(float(similarity))
        except (TypeError, ValueError):
            self.spin_similarity.setValue(0.9)
        self.refresh_incremental_baselines()
        if hasattr(self, "cmb_baseline_session"):
            try:
                sid = int(self.settings.value("filter/baseline_session_id", 0) or 0)
            except Exception:
                sid = 0
            if sid > 0:
                idx = self.cmb_baseline_session.findData(sid)
                if idx >= 0:
                    self.cmb_baseline_session.setCurrentIndex(idx)
        self._sync_filter_states()
        
        folders = self.settings.value("folders", [])
        # ?귐딅뮞?硫? ?袁⑤빍????μ뵬 ?얜챷???以????貫由??野껋럩??첎? ??됰선 ????筌ｋ똾寃?
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
        
        # ??ν뀧??嚥≪뮆諭?
        shortcuts_json = self.settings.value("app/shortcuts", "")
        if shortcuts_json:
            try:
                self.custom_shortcuts = json.loads(shortcuts_json)
                self._apply_shortcuts(self.custom_shortcuts)
            except:
                pass
        
        # ??뽰뇚 ???쉘 嚥≪뮆諭?
        patterns_json = self.settings.value("filter/exclude_patterns", "")
        if patterns_json:
            try:
                self.exclude_patterns = json.loads(patterns_json)
                if self.exclude_patterns:
                    self.btn_exclude_patterns.setText(
                        f"{strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})"
                    )
            except:
                self.exclude_patterns = []

        # ??釉????쉘 嚥≪뮆諭?
        include_json = self.settings.value("filter/include_patterns", "")
        if include_json:
            try:
                self.include_patterns = json.loads(include_json)
                if hasattr(self, "btn_include_patterns") and self.include_patterns:
                    self.btn_include_patterns.setText(
                        f"{strings.tr('btn_include_patterns')} ({len(self.include_patterns)})"
                    )
            except Exception:
                self.include_patterns = []

        # Selection rules load
        try:
            rules_json = self.settings.value("rules/selection_json", "[]")
            self.selection_rules_json = json.loads(rules_json) if rules_json else []
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
                self.spin_quarantine_days.setValue(int(q_days) if q_days else 30)
            if hasattr(self, "spin_quarantine_gb"):
                try:
                    gb = max(1, int(int(q_bytes) / (1024 * 1024 * 1024)))
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
            keep_latest = int(self.settings.value("cache/session_keep_latest", 20) or 20)
        except Exception:
            keep_latest = 20
        try:
            hash_cleanup_days = int(self.settings.value("cache/hash_cleanup_days", 30) or 30)
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
                wd = int(self.settings.value("schedule/weekday", 0) or 0)
                idx = self.cmb_schedule_weekday.findData(wd)
                self.cmb_schedule_weekday.setCurrentIndex(idx if idx >= 0 else 0)
            if hasattr(self, "txt_schedule_time"):
                self.txt_schedule_time.setText(str(self.settings.value("schedule/time_hhmm", "03:00") or "03:00"))
            if hasattr(self, "txt_schedule_output"):
                self.txt_schedule_output.setText(str(self.settings.value("schedule/output_dir", "") or ""))
            if hasattr(self, "chk_schedule_export_json"):
                self.chk_schedule_export_json.setChecked(str(self.settings.value("schedule/output_json", True)).lower() == "true")
            if hasattr(self, "chk_schedule_export_csv"):
                self.chk_schedule_export_csv.setChecked(str(self.settings.value("schedule/output_csv", True)).lower() == "true")
            self._sync_schedule_ui()
            self._persist_schedule_job()
        except Exception:
            pass

    def _restore_cached_session(self):
        try:
            keep_latest = int(self.settings.value("cache/session_keep_latest", 20) or 20)
        except Exception:
            keep_latest = 20
        try:
            hash_cleanup_days = int(self.settings.value("cache/hash_cleanup_days", 30) or 30)
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

        self.current_session_id = session.get("id")

        if session.get("status") in ("completed", "partial"):
            results = self.cache_manager.load_scan_results(self.current_session_id)
            if results:
                selected_paths = self.cache_manager.load_selected_paths(self.current_session_id)
                self.scan_results = results
                self._current_baseline_delta_map = {}
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
                self.status_label.setText(session.get("progress_message"))
            try:
                self._set_scan_stage_code(str(session.get("stage") or ""))
            except Exception:
                pass
            if session.get("status") in ("running", "paused"):
                self._prompt_resume_session(session)

    def _prompt_resume_session(self, session: dict = None):
        session = session or {}
        box = QMessageBox(self)
        box.setWindowTitle(strings.tr("app_title"))
        box.setIcon(QMessageBox.Question)
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
        btn_resume = box.addButton(strings.tr("btn_resume"), QMessageBox.AcceptRole)
        btn_new = box.addButton(strings.tr("btn_new_scan"), QMessageBox.DestructiveRole)
        btn_later = box.addButton(strings.tr("btn_later"), QMessageBox.RejectRole)
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

    def _normalize_extension_tokens(self, value):
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

    def _normalize_path_list(self, values):
        out = set()
        for path in values or []:
            p = str(path or "").strip()
            if not p:
                continue
            p = os.path.normcase(os.path.normpath(os.path.abspath(p)))
            out.add(p)
        return sorted(out)

    def _normalize_pattern_list(self, values):
        out = set()
        for token in values or []:
            p = str(token or "").strip()
            if not p:
                continue
            out.add(p)
        return sorted(out)

    def _get_scan_hash_config(self, config: dict) -> dict:
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

    def on_checked_files_changed(self, paths):
        """Backward-compatible full-list handler."""
        new_set = set(paths or [])
        added = sorted(new_set - self._saved_selected_paths)
        removed = sorted(self._saved_selected_paths - new_set)
        self.on_checked_files_delta(added, removed, len(new_set), full_snapshot=new_set)

    def on_checked_files_delta(self, added, removed, selected_count: int, full_snapshot=None):
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

    def _flush_selected_paths(self):
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

    def _set_results_view(self, has_results: bool):
        if not hasattr(self, "results_stack"):
            return
        self.results_stack.setCurrentIndex(1 if has_results else 0)

    def _update_results_summary(self, selected_count: int = None):
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

    def _update_action_buttons_state(self, selected_count: int = None):
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

    def show_context_menu(self, position):
        item = self.tree_widget.itemAt(position)
        if not item: return
        
        path = item.data(0, Qt.UserRole)
        menu = QMenu()

        # File item context (path is stored on leaf items).
        if path:
            path = str(path)
            action_open = QAction(self.style().standardIcon(QStyle.SP_FileIcon), strings.tr("ctx_open"), self)
            action_open.setEnabled(os.path.exists(path) and os.path.isfile(path))
            action_open.triggered.connect(lambda: self.open_file(item, 0))
            menu.addAction(action_open)

            folder = os.path.dirname(path)
            action_folder = QAction(self.style().standardIcon(QStyle.SP_DirIcon), strings.tr("ctx_open_folder"), self)
            action_folder.setEnabled(bool(folder) and os.path.isdir(folder))
            action_folder.triggered.connect(lambda: self.open_containing_folder(path))
            menu.addAction(action_folder)

            menu.addSeparator()

            action_copy = QAction(strings.tr("ctx_copy_path"), self)
            action_copy.triggered.connect(lambda: self.copy_to_clipboard(path))
            menu.addAction(action_copy)

        else:
            # Group item context
            if item.childCount() <= 0:
                return
            key = item.data(0, Qt.UserRole + 1)

            act_check_all = QAction(strings.tr("ctx_group_check_all"), self)
            act_check_all.triggered.connect(lambda: self.tree_widget.set_group_checked(item, True))
            menu.addAction(act_check_all)

            act_uncheck_all = QAction(strings.tr("ctx_group_uncheck_all"), self)
            act_uncheck_all.triggered.connect(lambda: self.tree_widget.set_group_checked(item, False))
            menu.addAction(act_uncheck_all)

            if self.selection_rules:
                act_apply_rules = QAction(strings.tr("ctx_group_apply_rules"), self)

                def apply_rules():
                    paths = self.tree_widget.get_group_paths(item)
                    keep_set, _delete_set = self.results_controller.build_keep_delete_by_rules(paths, self.selection_rules)
                    self.tree_widget.begin_bulk_check_update()
                    try:
                        for j in range(item.childCount()):
                            child = item.child(j)
                            p = child.data(0, Qt.UserRole)
                            if not p:
                                continue
                            child.setCheckState(0, Qt.Unchecked if p in keep_set else Qt.Checked)
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
                        p = child.data(0, Qt.UserRole)
                        if not p:
                            continue
                        if child.checkState(0) == Qt.Checked:
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

    def open_containing_folder(self, path):
        if not os.path.exists(path): return
        folder = os.path.dirname(path)
        if platform.system() == 'Windows':
            os.startfile(folder)
        elif platform.system() == 'Darwin':
            subprocess.call(('open', folder))
        else:
            subprocess.call(('xdg-open', folder))

    def copy_to_clipboard(self, text):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def open_cache_db_folder(self):
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

    def copy_cache_db_path(self):
        """Copy cache DB path to clipboard."""
        try:
            db_path = str(getattr(self.cache_manager, "db_path", "") or "")
        except Exception:
            db_path = ""
        if db_path:
            self.copy_to_clipboard(db_path)

    # === ??疫꿸퀡??筌롫뗄苑??뺣굶 ===
    
    def save_scan_results(self):
        """Save current scan results to JSON."""
        if not self.scan_results:
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_files_selected"))
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
            payload = dump_results_v2(
                scan_results=self.scan_results,
                folders=list(self.selected_folders or []),
                source="gui",
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
            QMessageBox.critical(self, strings.tr("app_title"), strings.tr("err_save").format(e))

    def load_scan_results(self):
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
            self.scan_results = load_results_any(data)
            self._current_baseline_delta_map = {}
            meta = data.get("meta") if isinstance(data, dict) else {}
            if not isinstance(meta, dict):
                meta = {}
            self._last_scan_status = str(meta.get("scan_status") or "completed")
            self._last_scan_metrics = dict(meta.get("metrics") or {})
            self._last_scan_warnings = list(meta.get("warnings") or [])
            
            self._render_results(self.scan_results, selected_paths=[], selected_count=0)
            self.status_label.setText(strings.tr("msg_results_loaded").format(len(self.scan_results)))
            try:
                self._navigate_to("results")
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, strings.tr("app_title"), strings.tr("err_load").format(e))

    def open_preset_dialog(self):
        """?袁ⓥ봺???온????쇱뵠??곗쨮域???용┛"""
        current_config = self._get_current_config()
        dlg = PresetDialog(self.preset_manager, current_config, self)
        if dlg.exec() and dlg.selected_config:
            self._apply_config(dlg.selected_config)
    
    def open_exclude_patterns_dialog(self):
        """??뽰뇚 ???쉘 ??쇱젟 ??쇱뵠??곗쨮域???용┛"""
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
            # ??뽰뇚 ???쉘 ????뽯뻻
            if self.exclude_patterns:
                self.btn_exclude_patterns.setText(
                    f"{strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})"
                )
            else:
                self.btn_exclude_patterns.setText(strings.tr("btn_exclude_patterns"))

    def open_include_patterns_dialog(self):
        """??釉????쉘 ??쇱젟 ??쇱뵠??곗쨮域???용┛"""
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
    
    def open_shortcut_settings(self):
        """??ν뀧????쇱젟 ??쇱뵠??곗쨮域???용┛"""
        dlg = ShortcutSettingsDialog(self.custom_shortcuts, self)
        if dlg.exec():
            self.custom_shortcuts = dlg.get_shortcuts()
            self._apply_shortcuts(self.custom_shortcuts)
    
    def _get_current_config(self) -> dict:
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
            'strict_mode': self.chk_strict_mode.isChecked() if hasattr(self, 'chk_strict_mode') else False,
            'strict_max_errors': self.spin_strict_max_errors.value() if hasattr(self, 'spin_strict_max_errors') else 0,
        }
    
    def _apply_config(self, config: dict):
        """?類ㅻ??댿봺 ??쇱젟??UI???怨몄뒠"""
        # ????
        if 'folders' in config:
            self.selected_folders = config['folders']
            self.list_folders.clear()
            for f in self.selected_folders:
                self.list_folders.addItem(f)
            self._on_folders_changed()
        
        # ?袁り숲
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
        
        # ??뽰뇚 ???쉘
        if 'exclude_patterns' in config:
            self.exclude_patterns = config['exclude_patterns']
            if self.exclude_patterns:
                self.btn_exclude_patterns.setText(
                    f"{strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})"
                )
            else:
                self.btn_exclude_patterns.setText(strings.tr("btn_exclude_patterns"))

        # ??釉????쉘
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
    
    def _apply_shortcuts(self, shortcuts: dict):
        """?뚣끉??? ??ν뀧??? ??る???怨몄뒠"""
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

    # === Quarantine / Rules / Operations ===

    def _sync_advanced_visibility(self, *_):
        """Show/hide advanced actions based on settings."""
        try:
            enabled = bool(getattr(self, "chk_enable_hardlink", None) and self.chk_enable_hardlink.isChecked())
        except Exception:
            enabled = False
        if hasattr(self, "btn_hardlink_checked"):
            self.btn_hardlink_checked.setVisible(enabled)

    def _apply_quarantine_retention(self):
        """Best-effort retention policy application."""
        try:
            if hasattr(self, "chk_quarantine_enabled") and not self.chk_quarantine_enabled.isChecked():
                return
            days = int(self.settings.value("quarantine/max_days", 30))
            max_bytes = int(self.settings.value("quarantine/max_bytes", 10 * 1024 * 1024 * 1024))
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

    def choose_quarantine_folder(self):
        path = QFileDialog.getExistingDirectory(self, strings.tr("btn_choose_folder"), "")
        if not path:
            return
        self.txt_quarantine_path.setText(path)

    def apply_quarantine_settings(self):
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
            QMessageBox.warning(self, strings.tr("app_title"), str(e))

    def choose_schedule_output_folder(self):
        path = QFileDialog.getExistingDirectory(self, strings.tr("btn_choose_folder"), "")
        if path and hasattr(self, "txt_schedule_output"):
            self.txt_schedule_output.setText(path)

    @staticmethod
    def _validate_schedule_time_hhmm(value: str) -> bool:
        raw = str(value or "").strip()
        return bool(re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", raw))

    def apply_cache_settings(self):
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
            QMessageBox.warning(self, strings.tr("app_title"), str(e))

    def _sync_schedule_ui(self):
        enabled = bool(hasattr(self, "chk_schedule_enabled") and self.chk_schedule_enabled.isChecked())
        weekly = bool(hasattr(self, "cmb_schedule_frequency") and str(self.cmb_schedule_frequency.currentData() or "daily") == "weekly")
        if hasattr(self, "cmb_schedule_weekday"):
            self.cmb_schedule_weekday.setEnabled(enabled and weekly)
        if hasattr(self, "lbl_schedule_weekday"):
            self.lbl_schedule_weekday.setEnabled(enabled and weekly)
        for wname in ("txt_schedule_time", "txt_schedule_output", "chk_schedule_export_json", "chk_schedule_export_csv", "btn_schedule_pick"):
            if hasattr(self, wname):
                getattr(self, wname).setEnabled(enabled)

    def _build_schedule_config(self) -> ScheduleConfig:
        return self.scheduler_controller.build_config(
            enabled=bool(hasattr(self, "chk_schedule_enabled") and self.chk_schedule_enabled.isChecked()),
            schedule_type=str(self.cmb_schedule_frequency.currentData() if hasattr(self, "cmb_schedule_frequency") else "daily"),
            weekday=int(self.cmb_schedule_weekday.currentData() if hasattr(self, "cmb_schedule_weekday") else 0),
            time_hhmm=str(self.txt_schedule_time.text() if hasattr(self, "txt_schedule_time") else "03:00").strip() or "03:00",
        )

    def _build_schedule_config_from_context(self) -> ScheduleConfig:
        ctx = dict(self._scheduled_run_context or {})
        return self.scheduler_controller.build_config(
            enabled=True,
            schedule_type=str(ctx.get("schedule_type") or "daily"),
            weekday=int(ctx.get("weekday") or 0),
            time_hhmm=str(ctx.get("time_hhmm") or "03:00").strip() or "03:00",
        )

    def _persist_schedule_job(self):
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

    def apply_schedule_settings(self):
        try:
            time_hhmm = str(self.txt_schedule_time.text() if hasattr(self, "txt_schedule_time") else "").strip()
            if not self._validate_schedule_time_hhmm(time_hhmm):
                msg = strings.tr("err_schedule_time_hhmm").format(value=time_hhmm or "")
                QMessageBox.warning(self, strings.tr("app_title"), msg)
                self.status_label.setText(msg)
                return
            self.save_settings()
            self._sync_schedule_ui()
            self._persist_schedule_job()
            if hasattr(self, "toast_manager") and self.toast_manager:
                self.toast_manager.info(strings.tr("msg_settings_applied"), duration=2200)
        except Exception as e:
            QMessageBox.warning(self, strings.tr("app_title"), str(e))

    def _scheduler_tick(self):
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

    def _scheduled_export_results(self, results: dict):
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
                payload = dump_results_v2(
                    scan_results=results or {},
                    folders=list((ctx.get("snapshot_folders") or []) or []),
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

    def _finish_scheduled_run(self, status: str, results: dict, message_override: str = ""):
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

    def open_selection_rules_dialog(self):
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

    def refresh_quarantine_list(self):
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
            i0.setData(Qt.UserRole, item_id)
            self.tbl_quarantine.setItem(r, 0, i0)

            i1 = QTableWidgetItem(self.format_size(int(it.get("size") or 0)))
            self.tbl_quarantine.setItem(r, 1, i1)

            i2 = QTableWidgetItem(dt)
            self.tbl_quarantine.setItem(r, 2, i2)

            i3 = QTableWidgetItem(it.get("status") or "")
            self.tbl_quarantine.setItem(r, 3, i3)

    def _selected_quarantine_item_ids(self) -> list:
        ids = []
        try:
            rows = {i.row() for i in self.tbl_quarantine.selectedIndexes()}
            for r in sorted(rows):
                it = self.tbl_quarantine.item(r, 0)
                if not it:
                    continue
                item_id = it.data(Qt.UserRole)
                if item_id:
                    ids.append(int(item_id))
        except Exception:
            pass
        return ids

    def restore_selected_quarantine(self):
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

    def purge_selected_quarantine(self):
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
        res = QMessageBox.warning(
            self,
            strings.tr("confirm_delete_title"),
            strings.tr("confirm_purge_items").format(len(item_ids)),
            QMessageBox.Yes | QMessageBox.No,
        )
        if res != QMessageBox.Yes:
            return
        self._start_operation(Operation("purge", options={"item_ids": item_ids}))

    def purge_all_quarantine(self):
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
        res = QMessageBox.warning(
            self,
            strings.tr("confirm_delete_title"),
            strings.tr("confirm_purge_all").format(len(item_ids)),
            QMessageBox.Yes | QMessageBox.No,
        )
        if res != QMessageBox.Yes:
            return
        self._start_operation(Operation("purge", options={"item_ids": item_ids}))

    def refresh_operations_list(self):
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
            i0.setData(Qt.UserRole, op)
            self.tbl_ops.setItem(r, 0, i0)
            self.tbl_ops.setItem(r, 1, QTableWidgetItem(dt))
            self.tbl_ops.setItem(r, 2, QTableWidgetItem(str(op.get("op_type") or "")))
            self.tbl_ops.setItem(r, 3, QTableWidgetItem(str(op.get("status") or "")))
            self.tbl_ops.setItem(r, 4, QTableWidgetItem(str(op.get("message") or "")))

    def _selected_operation_row(self) -> dict:
        try:
            row = self.tbl_ops.currentRow()
            if row < 0:
                return {}
            it = self.tbl_ops.item(row, 0)
            if not it:
                return {}
            data = it.data(Qt.UserRole)
            return data or {}
        except Exception:
            return {}

    def view_selected_operation(self):
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

    def _undo_hardlink_from_operation(self, op: dict, dlg: OperationLogDialog):
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
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_items"))
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

    def select_duplicates_by_rules(self):
        if not self.scan_results:
            return
        rules = self.selection_rules or []
        if not rules:
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_rules"))
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
                    p = child.data(0, Qt.UserRole)
                    if not p:
                        continue
                    child.setCheckState(0, Qt.Unchecked if p in keep_set else Qt.Checked)
        finally:
            self.tree_widget.end_bulk_check_update()

    def _is_group_key_hardlink_eligible(self, key) -> bool:
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

    def hardlink_consolidate_checked(self):
        # Build per-group operations based on checked files (targets) and unchecked (canonical).
        try:
            enabled = bool(self.chk_enable_hardlink.isChecked())
        except Exception:
            enabled = False
        if not enabled:
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_hardlink_disabled"))
            return

        root = self.tree_widget.invisibleRootItem()
        ops = []
        issues = []
        total_targets = 0
        for i in range(root.childCount()):
            group = root.child(i)
            key = group.data(0, Qt.UserRole + 1)
            if not self._is_group_key_hardlink_eligible(key):
                continue

            checked = []
            unchecked = []
            for j in range(group.childCount()):
                child = group.child(j)
                p = child.data(0, Qt.UserRole)
                if not p:
                    continue
                if child.checkState(0) == Qt.Checked:
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
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_items"))
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

    def _enqueue_operations(self, ops: list):
        self.operation_flow_controller.enqueue_operations(self, ops)

    def _start_next_operation(self):
        self.operation_flow_controller.start_next_operation(self)

    def _start_operation(self, op: Operation, allow_queue_continue: bool = False):
        self.operation_flow_controller.start_operation(self, op, allow_queue_continue=allow_queue_continue)

    def _cancel_operation(self):
        self.operation_flow_controller.cancel_operation(self)

    def _on_op_progress(self, val: int, msg: str):
        self.operation_flow_controller.on_progress(self, val, msg)

    def _on_op_finished(self, result, allow_queue_continue: bool):
        self.operation_flow_controller.on_finished(self, result, allow_queue_continue)
    
    def _on_page_changed(self, page_name: str):
        self.navigation_controller.on_page_changed(self, page_name)

    def _navigate_to(self, page_name: str):
        self.navigation_controller.navigate_to(self, page_name)


