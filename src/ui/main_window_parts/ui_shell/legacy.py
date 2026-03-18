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



class MainWindowUiShellMixin(DuplicateFinderTypingContract):
    def _on_use_trash_toggled(self: Any, checked: bool):
        if not checked:
            return
        try:
            warned = str(self.settings.value("ux/trash_warned", False)).lower() == "true"
        except Exception:
            warned = False

        if not warned:
            try:
                _mw().QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_trash_warning"))
            except Exception:
                pass
            self.settings.setValue("ux/trash_warned", True)
        elif hasattr(self, "toast_manager") and self.toast_manager:
            self.toast_manager.warning(strings.tr("msg_trash_warning"), duration=3500)

    def dragEnterEvent(self: Any, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self: Any, event):
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

    def _create_separator(self: Any):
        """Create a vertical separator line"""
        from PySide6.QtWidgets import QFrame
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    def init_ui(self: Any):
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
        tools_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tools_scroll.setWidget(self.tools_page)
        self.page_stack.addWidget(tools_scroll)

        self.settings_page = build_settings_page(self)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
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

    def retranslate_ui(self: Any):
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
            self.txt_result_filter.setPlaceholderText(strings.tr("ph_filter_results"))

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
        
        if self.status_label.text() in ["Ready", strings.tr("status_ready")]:
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

    def create_toolbar(self: Any):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Language Menu
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        # Actions
        self.action_undo = QAction(strings.tr("action_undo"), self)
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.action_undo.triggered.connect(self.perform_undo)
        self.action_undo.setEnabled(False)
        toolbar.addAction(self.action_undo)

        self.action_redo = QAction(strings.tr("action_redo"), self)
        self.action_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.action_redo.triggered.connect(self.perform_redo)
        self.action_redo.setEnabled(False)
        toolbar.addAction(self.action_redo)

        # Hidden actions for keyboard shortcuts (UX: shortcuts should actually work)
        self.action_start_scan = QAction(strings.tr("action_start_scan"), self)
        self.action_start_scan.setShortcut(QKeySequence("Ctrl+Return"))
        self.action_start_scan.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.action_start_scan.triggered.connect(self.start_scan)
        self.addAction(self.action_start_scan)

        self.action_stop_scan = QAction(strings.tr("action_stop_scan"), self)
        self.action_stop_scan.setShortcut(QKeySequence("Escape"))
        self.action_stop_scan.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.action_stop_scan.triggered.connect(self.stop_scan)
        self.addAction(self.action_stop_scan)

        self.action_delete_selected = QAction(strings.tr("action_delete"), self)
        self.action_delete_selected.setShortcut(QKeySequence("Delete"))
        self.action_delete_selected.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.action_delete_selected.triggered.connect(self.delete_selected_files)
        self.addAction(self.action_delete_selected)

        self.action_smart_select = QAction(strings.tr("action_smart_select"), self)
        self.action_smart_select.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self.action_smart_select.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.action_smart_select.triggered.connect(self.select_duplicates_smart)
        self.addAction(self.action_smart_select)

        self.action_export_csv = QAction(strings.tr("action_export"), self)
        self.action_export_csv.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export_csv.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
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
        
        # Save results
        self.action_save_results = QAction(strings.tr("action_save_results"), self)
        self.action_save_results.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save_results.triggered.connect(self.save_scan_results)
        toolbar.addAction(self.action_save_results)
        
        self.action_load_results = QAction(strings.tr("action_load_results"), self)
        self.action_load_results.setShortcut(QKeySequence.StandardKey.Open)
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
        
        # Preset menu
        self.btn_preset = QToolButton(self)
        self.btn_preset.setText(strings.tr("action_preset"))
        self.btn_preset.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        
        self.menu_preset = QMenu(self)
        action_save_preset = QAction(strings.tr("btn_save_preset"), self)
        action_save_preset.triggered.connect(self.open_preset_dialog)
        self.menu_preset.addAction(action_save_preset)
        
        action_manage_presets = QAction(strings.tr("btn_manage_presets"), self)
        action_manage_presets.triggered.connect(self.open_preset_dialog)
        self.menu_preset.addAction(action_manage_presets)
        
        self.btn_preset.setMenu(self.menu_preset)
        toolbar.addWidget(self.btn_preset)
        
        # Shortcut settings
        self.action_shortcut_settings = QAction(strings.tr("action_shortcut_settings"), self)
        self.action_shortcut_settings.triggered.connect(self.open_shortcut_settings)
        toolbar.addAction(self.action_shortcut_settings)
        
        toolbar.addSeparator()
        
        # Language Button with Menu
        self.btn_lang = QToolButton(self)
        self.btn_lang.setText(strings.tr("menu_lang"))
        self.btn_lang.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        
        self.menu_lang = QMenu(self)
        
        self.action_lang_ko = QAction(strings.tr("lang_ko"), self)
        self.action_lang_ko.triggered.connect(lambda: self.change_language("ko"))
        self.menu_lang.addAction(self.action_lang_ko)
        
        self.action_lang_en = QAction(strings.tr("lang_en"), self)
        self.action_lang_en.triggered.connect(lambda: self.change_language("en"))
        self.menu_lang.addAction(self.action_lang_en)
        
        self.btn_lang.setMenu(self.menu_lang)
        toolbar.addWidget(self.btn_lang)

    def change_language(self: Any, lang_code):
        strings.set_language(lang_code)
        self.retranslate_ui()
        self.settings.setValue("app/language", lang_code)

    def open_empty_finder(self: Any):
        if not self.selected_folders:
            _mw().QMessageBox.warning(self, strings.tr("msg_title_notice"), strings.tr("msg_add_folder_first"))
            return
        
        dlg = EmptyFolderDialog(self.selected_folders, self)
        dlg.exec()

    def apply_theme(self: Any, theme_name):
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

    def toggle_theme(self: Any, checked):
        self.apply_theme("dark" if checked else "light")

    def _toggle_filter_panel(self: Any, checked):
        """Toggle visibility of the filter panel with animation"""
        self.filter_container.setVisible(checked)
        arrow = "▲" if checked else "▼"
        self.btn_filter_toggle.setText(strings.tr("lbl_filter_options") + " " + arrow)

    def _sync_filter_states(self: Any, *_):
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

    def refresh_incremental_baselines(self: Any):
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

    def _get_selected_baseline_session_id(self: Any):
        if not hasattr(self, "cmb_baseline_session"):
            return None
        try:
            sid = int(self.cmb_baseline_session.currentData() or 0)
            return sid if sid > 0 else None
        except Exception:
            return None

    def _set_scan_stage(self: Any, message):
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

    def _set_scan_stage_code(self: Any, stage_code: str):
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

    def _on_page_changed(self: Any, page_name: str):
        self.navigation_controller.on_page_changed(self, page_name)

    def _navigate_to(self: Any, page_name: str):
        self.navigation_controller.navigate_to(self, page_name)
