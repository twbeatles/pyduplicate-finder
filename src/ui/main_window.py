from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel, QProgressBar, QCheckBox, QMessageBox, QGroupBox, QTreeWidget, QTreeWidgetItem, QToolBar, QSpinBox, QLineEdit, QMenu, QSplitter, QTextEdit, QScrollArea, QStyle, QProgressDialog, QToolButton, QSizePolicy, QListWidget, QDoubleSpinBox, QInputDialog, QStackedWidget, QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt, Slot, QSize, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence, QIcon, QPixmap, QFont, QCursor

import os
import sys
import platform
import subprocess
import string
import ctypes
import json
from datetime import datetime

from src.core.scanner import ScanWorker
from src.core.history import HistoryManager
from src.core.cache_manager import CacheManager
from src.core.file_ops import FileOperationWorker
from src.core.preset_manager import PresetManager, get_default_config
from src.core.file_lock_checker import FileLockChecker
from src.core.quarantine_manager import QuarantineManager
from src.core.preflight import PreflightAnalyzer
from src.core.selection_rules import parse_rules, decide_keep_delete_for_group
from src.core.operation_queue import OperationWorker, Operation
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
        self._selection_save_timer = QTimer(self)
        self._selection_save_timer.setSingleShot(True)
        self._selection_save_timer.timeout.connect(self._flush_selected_paths)
        
        # 새 기능 관련 인스턴스 변수
        self.preset_manager = PresetManager()
        self.file_lock_checker = FileLockChecker()
        self.exclude_patterns = []
        self.custom_shortcuts = {}

        # Quarantine / operations / rules
        self.preflight_analyzer = PreflightAnalyzer(lock_checker=self.file_lock_checker)
        self.selection_rules_json = []
        self.selection_rules = []

        self._op_worker = None
        self._op_progress = None
        self._op_queue = []
        
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

        # Drag & Drop 활성화
        self.setAcceptDrops(True)

        # UX: warn once when enabling system trash (Undo not available)
        self.chk_use_trash.toggled.connect(self._on_use_trash_toggled)

        # Initial folder-dependent UI state
        self._on_folders_changed()

    def closeEvent(self, event):
        self.save_settings()
        self._flush_selected_paths()
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
        self.chk_similar_image.setText(strings.tr("chk_similar_image"))
        self.chk_similar_image.setToolTip(strings.tr("tip_similar_image"))
        self.lbl_similarity.setText(strings.tr("lbl_similarity_threshold"))
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
            self.txt_result_filter.setPlaceholderText("🔍 " + strings.tr("ph_filter_results"))

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
        
        if self.status_label.text() in ["Ready", "준비됨"]:
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
        
        # 결과 저장/불러오기
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
        
        # 프리셋 메뉴
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
        
        # 단축키 설정
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
        arrow = "▼" if checked else "▶"
        self.btn_filter_toggle.setText(strings.tr("lbl_filter_options") + " " + arrow)

    def _sync_filter_states(self, *_):
        name_only = self.chk_name_only.isChecked()
        if name_only:
            self.chk_same_name.setChecked(False)
            self.chk_byte_compare.setChecked(False)
            self.chk_similar_image.setChecked(False)

        self.chk_same_name.setEnabled(not name_only)
        self.chk_byte_compare.setEnabled(not name_only)
        self.chk_similar_image.setEnabled(not name_only)
        self.spin_similarity.setEnabled(self.chk_similar_image.isChecked() and not name_only)

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
            "analyzing": strings.tr("status_analyzing"),
            "hashing": strings.tr("status_hashing"),
            "similar_image": strings.tr("status_similar_image_scan"),
            "grouping": strings.tr("status_grouping"),
            "completed": strings.tr("status_done"),
            "error": "Error",
            "abandoned": "Abandoned",
        }
        label = stage_map.get(code, code or strings.tr("status_ready"))
        self.lbl_scan_stage.setText(strings.tr("msg_scan_stage").format(stage=label))

    # --- 기능 구현: 드라이브 및 폴더 ---

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

    # --- 기능 구현: 스캔 ---
    # --- 기능 구현: 스캔 ---
    def start_scan(self, force_new=False):
        if not self.selected_folders:
            QMessageBox.warning(self, strings.tr("app_title"), strings.tr("err_no_folder"))
            return

        raw_ext = self.txt_extensions.text()
        extensions = [x.strip() for x in raw_ext.split(',')] if raw_ext.strip() else None
        min_size = self.spin_min_size.value()

        current_config = self._get_current_config()
        hash_config = self._get_scan_hash_config(current_config)
        config_hash = self.cache_manager.get_config_hash(hash_config)
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

            # Keep session metadata aligned with current UI settings (even if config_hash matches).
            try:
                self.cache_manager.update_scan_session(
                    session_id,
                    config_json=json.dumps(current_config, ensure_ascii=False, sort_keys=True, default=str),
                    config_hash=config_hash,
                )
            except Exception:
                pass
        else:
            session_id = self.cache_manager.create_scan_session(current_config, config_hash=config_hash)
            self.cache_manager.clear_selected_paths(session_id)

        if not session_id:
            use_cached_files = False
            session_id = None

        self.current_session_id = session_id
        self._pending_selected_paths = []

        self._previous_results = self.scan_results
        self._previous_selected_paths = self.tree_widget.get_checked_files()

        self.tree_widget.clear()
        self.scan_results = {}
        self._set_results_view(False)
        self._update_results_summary(0)
        self.toggle_ui_state(scanning=True)
        self._set_scan_stage_code("collecting")
        
        self.worker = ScanWorker(
            self.selected_folders, 
            check_name=self.chk_same_name.isChecked(),
            min_size_kb=min_size,
            extensions=extensions,
            protect_system=self.chk_protect_system.isChecked(),
            byte_compare=self.chk_byte_compare.isChecked(),
            exclude_patterns=self.exclude_patterns,
            name_only=self.chk_name_only.isChecked(),
            use_similar_image=self.chk_similar_image.isChecked(),
            similarity_threshold=self.spin_similarity.value(),
            session_id=session_id,
            use_cached_files=use_cached_files
        )
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.stage_updated.connect(self.on_scan_stage_changed)
        self.worker.scan_finished.connect(self.on_scan_finished)
        self.worker.scan_cancelled.connect(self.on_scan_cancelled)  # Issue #3
        self.worker.scan_failed.connect(self.on_scan_failed)
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
        self._set_scan_stage_code("completed")
        self.toggle_ui_state(scanning=False)
        self.progress_bar.setValue(100)
        self.status_label.setText(strings.tr("msg_scan_complete").format(len(results)))
        self._set_scan_stage_code("completed")
        self.tree_widget.populate(results)
        self.filter_results_tree(self.txt_result_filter.text())
        self._set_results_view(bool(results))
        self._update_results_summary(0)
        self._update_action_buttons_state(selected_count=0)
        # UX: bring user to focused results page after scan completes.
        try:
            self._navigate_to("results")
        except Exception:
            pass
        if self.current_session_id:
            self.cache_manager.save_scan_results(self.current_session_id, results)
            self.cache_manager.save_selected_paths(self.current_session_id, [])

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
            self.tree_widget.populate(self.scan_results, selected_paths=self._previous_selected_paths)
            self.filter_results_tree(self.txt_result_filter.text())
            self._set_results_view(True)
            self._update_results_summary(len(self._previous_selected_paths))
            self._update_action_buttons_state(selected_count=len(self._previous_selected_paths))
        else:
            self._set_results_view(False)
            self._update_results_summary(0)
            self._update_action_buttons_state(selected_count=0)

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
            self.tree_widget.populate(self.scan_results, selected_paths=self._previous_selected_paths)
            self.filter_results_tree(self.txt_result_filter.text())
            self._set_results_view(True)
            self._update_results_summary(len(self._previous_selected_paths))
            self._update_action_buttons_state(selected_count=len(self._previous_selected_paths))
        else:
            self._set_results_view(False)
            self._update_results_summary(0)
            self._update_action_buttons_state(selected_count=0)
        QMessageBox.critical(self, strings.tr("app_title"), err_msg)

    def populate_tree(self, results):
        self.tree_widget.populate(results)


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

            export_scan_results_csv(scan_results=self.scan_results, out_path=path, selected_paths=selected)
            QMessageBox.information(self, strings.tr("status_done"), strings.tr("status_done") + f":\n{path}")
        except Exception as e:
            QMessageBox.critical(self, strings.tr("app_title"), strings.tr("err_save").format(e))

    # --- 기능 구현: 선택 및 삭제 (Undo/Redo 포함) ---
    def select_duplicates_smart(self):
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            files = []
            for j in range(group.childCount()):
                item = group.child(j)
                path = item.data(0, Qt.UserRole)
                try: mtime = os.path.getmtime(path)
                except: mtime = 0
                files.append((path, mtime, item))
            
            # 스마트 선택 로직 개선 (점수 기반)
            def calculate_score(entry):
                path, mtime, _ = entry
                score = 0
                lower_path = path.lower()
                
                # 1. 삭제 우선순위가 높은 패턴 (높은 점수 = 삭제 대상)
                if any(x in lower_path for x in ['/temp/', '\\temp\\', '\\appdata\\local\\temp\\', '/cache/', '\\cache\\', '.tmp']):
                    score += 1000
                
                # 2. 복사본 패턴
                if 'copy' in lower_path or ' - 복사본' in lower_path or ' - copy' in lower_path or '(1)' in lower_path:
                    score += 500
                    
                # 3. 파일명 길이 (보통 원본이 짧음)
                score += len(os.path.basename(path)) * 0.1
                
                # 4. 최신 파일이 보통 복사본일 확률이 높음 (또는 원본 보존 정책에 따라 다름)
                # 여기서는 "오래된 것이 원본"이라는 가정 하에, 최신 파일 점수를 높임
                score += mtime * 0.0000001
                
                return score

            # 점수가 낮은 순(원본 가능성 높음)으로 정렬
            files.sort(key=calculate_score)
            
            # 첫 번째(가장 원본 같은) 파일만 체크 해제, 나머지는 삭제(체크)
            for idx, (_, _, item) in enumerate(files):
                item.setCheckState(0, Qt.Unchecked if idx == 0 else Qt.Checked)

    def select_duplicates_newest(self):
        """Keep Oldest, Select Newest (Date based)"""
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            files = []
            for j in range(group.childCount()):
                item = group.child(j)
                path = item.data(0, Qt.UserRole)
                try: mtime = os.path.getmtime(path)
                except: mtime = 0
                files.append((mtime, item))
            
            # Sort by Modified Time (Ascending: Oldest first)
            files.sort(key=lambda x: x[0])
            # Keep first (Oldest), Check others (Newer)
            for idx, (_, item) in enumerate(files):
                item.setCheckState(0, Qt.Unchecked if idx == 0 else Qt.Checked)

    def select_duplicates_oldest(self):
        """Keep Newest, Select Oldest (Date based)"""
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            files = []
            for j in range(group.childCount()):
                item = group.child(j)
                path = item.data(0, Qt.UserRole)
                try: mtime = os.path.getmtime(path)
                except: mtime = 0
                files.append((mtime, item))
            
            # Sort by Modified Time (Descending: Newest first)
            files.sort(key=lambda x: x[0], reverse=True)
            # Keep first (Newest), Check others (Older)
            for idx, (_, item) in enumerate(files):
                item.setCheckState(0, Qt.Unchecked if idx == 0 else Qt.Checked)

    def select_duplicates_by_pattern(self):
        """Select files matching a text pattern"""
        text, ok = QInputDialog.getText(self, strings.tr("ctx_select_pattern_title"), 
                                      strings.tr("ctx_select_pattern_msg"))
        if not ok or not text: return
        
        pattern = text.lower()
        root = self.tree_widget.invisibleRootItem()
        
        count = 0
        for i in range(root.childCount()):
            group = root.child(i)
            # Don't uncheck everything, just check matches. 
            # Or should we uncheck everything first? Usually "Select" adds to selection or replaces. 
            # Smart Select replaces. Let's make this additive or independent.
            # Let's check ONLY matches.
            
            for j in range(group.childCount()):
                item = group.child(j)
                path = item.data(0, Qt.UserRole) or ""
                path = path.lower()
                
                if pattern in path:
                    item.setCheckState(0, Qt.Checked)
                    count += 1
        
        self.status_label.setText(
            strings.tr("msg_selected_pattern").format(count=count, pattern=text)
        )

    def filter_results_tree(self, text):
        """Filter the result tree by filename/path"""
        text = text.lower()
        root = self.tree_widget.invisibleRootItem()

        total_files = 0
        visible_files = 0
        for i in range(root.childCount()):
            group = root.child(i)
            group_visible = False
            
            for j in range(group.childCount()):
                item = group.child(j)
                path = item.data(0, Qt.UserRole) or ""
                path = path.lower()
                total_files += 1
                
                # Simple containment check
                if not text or text in path:
                    item.setHidden(False)
                    group_visible = True
                    visible_files += 1
                else:
                    item.setHidden(True)
            
            # Hide group if no children visible
            group.setHidden(not group_visible)

        if hasattr(self, "lbl_filter_count"):
            if total_files == 0:
                self.lbl_filter_count.setText("")
            else:
                self.lbl_filter_count.setText(
                    strings.tr("msg_filter_count").format(
                        visible=visible_files, total=total_files
                    )
                )

        # Keep action meta ("filter active") and button states in sync.
        try:
            self._update_action_buttons_state()
        except Exception:
            pass

    def delete_selected_files(self):
        targets = []
        # Store items to remove from UI *after* operation success
        # But for async, we need a way to link targets back to UI items.
        # Simplest: Reload the tree or just delete UI items if success.
        # Better: Store targets and wait for signal.
        
        self.pending_delete_items = [] # temporary storage
        filter_active = bool(self.txt_result_filter.text().strip())
        visible_checked = 0

        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            for j in range(group.childCount()):
                item = group.child(j)
                if item.checkState(0) == Qt.Checked:
                    targets.append(item.data(0, Qt.UserRole))
                    self.pending_delete_items.append(item)
                    if not item.isHidden():
                        visible_checked += 1

        if not targets:
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_files_selected"))
            return

        # 파일 잠금 체크
        locked_files = self.file_lock_checker.get_locked_files(targets)
        if locked_files:
            locked_list = "\n".join(locked_files[:5])
            if len(locked_files) > 5:
                locked_list += f"\n... and {len(locked_files) - 5} more"
            QMessageBox.warning(
                self, strings.tr("app_title"),
                f"{strings.tr('msg_file_locked')}\n\n{locked_list}"
            )
            # 잠긴 파일 제외
            targets = [t for t in targets if t not in locked_files]
            self.pending_delete_items = [item for item in self.pending_delete_items 
                                         if item.data(0, Qt.UserRole) not in locked_files]
            if not targets:
                return

        # 휴지통 옵션 확인
        use_trash = self.chk_use_trash.isChecked()

        # Use persistent quarantine for undoable deletes if enabled.
        quarantine_enabled = str(self.settings.value("quarantine/enabled", True)).lower() == "true"
        if use_trash:
            op_type = "delete_trash"
        else:
            op_type = "delete_quarantine" if quarantine_enabled else "delete_trash"
            if not quarantine_enabled:
                QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_quarantine_disabled_fallback"))

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

    def perform_undo(self):
        self._start_operation(Operation("undo"))

    def perform_redo(self):
        self._start_operation(Operation("redo"))

    def start_file_operation(self, op_type, data=None, use_trash=False):
        # Disable UI
        self.toggle_ui_state(scanning=True) # Re-use scanning state (disables interactions)
        
        # Show Progress Dialog
        cancel_text = strings.tr("btn_cancel") if op_type == "delete" else None
        self.file_op_dialog = QProgressDialog(strings.tr("status_analyzing"), cancel_text, 0, 0, self)
        self.file_op_dialog.setWindowTitle(strings.tr("app_title"))
        self.file_op_dialog.setWindowModality(Qt.WindowModal)
        self.file_op_dialog.setMinimumDuration(0)
        if op_type != "delete":
            self.file_op_dialog.setCancelButton(None) # Keep undo/redo non-cancellable for safety
        self.file_op_dialog.show()

        self.file_worker = FileOperationWorker(self.history_manager, op_type, data, use_trash=use_trash)
        self.file_worker.progress_updated.connect(lambda val, msg: self.file_op_dialog.setLabelText(msg))
        self.file_worker.operation_finished.connect(lambda s, m: self.on_file_op_finished(op_type, s, m))
        if op_type == "delete":
            # Best-effort cancel: stops between file operations.
            self.file_op_dialog.canceled.connect(self.file_worker.stop)
        self.file_worker.start()

    def on_file_op_finished(self, op_type, success, message):
        self.file_op_dialog.close()
        self.toggle_ui_state(scanning=False)
        self.status_label.setText(message)
        
        if op_type == 'delete':
            # Update UI/results based on actual filesystem state (supports partial success/cancel).
            if hasattr(self, 'pending_delete_items'):
                deleted_paths = set()
                parents = {}
                for item in list(self.pending_delete_items):
                    path = item.data(0, Qt.UserRole)
                    if path and not os.path.exists(path):
                        deleted_paths.add(path)
                        parent = item.parent()
                        if parent:
                            parents[id(parent)] = parent
                            parent.removeChild(item)

                for parent in parents.values():
                    if parent.childCount() < 2:
                        self.tree_widget.invisibleRootItem().removeChild(parent)

                self._remove_paths_from_results(deleted_paths)
                self.pending_delete_items = []
                if self.current_session_id:
                    self.cache_manager.save_scan_results(self.current_session_id, self.scan_results)
                    self.cache_manager.save_selected_paths(
                        self.current_session_id,
                        self.tree_widget.get_checked_files()
                    )

        if success:
            if op_type == 'undo':
                # Issue #23: Recommend rescan after undo since restored files may not be in scan_results
                if self.scan_results:
                    self.tree_widget.populate(self.scan_results)
                    self._set_results_view(True)
                    self._update_results_summary()
                # Inform user that rescan may be needed for accurate results
                undo_msg = message + "\n\n" + strings.tr("msg_rescan_recommended")
                QMessageBox.information(self, strings.tr("app_title"), undo_msg)
                
            elif op_type == 'redo':
                # For redo, just inform user - tree already reflects state
                QMessageBox.information(self, strings.tr("app_title"), message)
            
            self.update_undo_redo_buttons()
        else:
             QMessageBox.warning(self, strings.tr("app_title"), message)
             if op_type == 'delete':
                 self.pending_delete_items = []
    
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

    def update_undo_redo_buttons(self):
        self.action_undo.setEnabled(bool(self.history_manager.undo_stack))
        self.action_redo.setEnabled(bool(self.history_manager.redo_stack))

    # --- 기능 구현: 미리보기 ---
    def update_preview(self, current, previous):
        if not current: return
        
        path = current.data(0, Qt.UserRole)
        # 그룹 아이템인 경우 path가 없을 수 있음
        if not path or not os.path.exists(path):
            self.show_preview_info(strings.tr("msg_select_file"))
            return

        if os.path.isdir(path):
            self._set_preview_info(path, is_folder=True)
            self.show_preview_info(strings.tr("msg_preview_folder_hint"), keep_info=True)
            return

        _, ext = os.path.splitext(path)
        ext = ext.lower()

        try:
            # 1. 이미지
            if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.ico']:
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    self._set_preview_info(path)
                    scaled = pixmap.scaled(self.lbl_image_preview.size().boundedTo(QSize(400, 400)), 
                                         Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.lbl_image_preview.setPixmap(scaled)
                    self.lbl_image_preview.show()
                    self.txt_text_preview.hide()
                    self.lbl_info_preview.hide()
                    return
            
            # 2. 텍스트 및 코드
            elif ext in ['.txt', '.py', '.c', '.cpp', '.h', '.java', '.md', '.json', '.xml', 
                         '.html', '.css', '.js', '.log', '.bat', '.sh', '.ini', '.yaml', '.yml', '.csv']:
                try:
                    # Avoid loading huge files into the UI.
                    file_size = None
                    try:
                        file_size = os.path.getsize(path)
                    except Exception:
                        file_size = None

                    # Read more than 4KB for better usability, but cap for safety.
                    max_chars = 200_000  # ~200KB (chars) best-effort
                    read_all = bool(file_size is not None and file_size <= 1_000_000 and ext == ".json")

                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read() if read_all else f.read(max_chars)
                    
                    # JSON Pretty Print
                    if ext == '.json' and read_all:
                        try:
                            parsed = json.loads(content)
                            content = json.dumps(parsed, indent=4, ensure_ascii=False)
                        except: pass
                        
                    self._set_preview_info(path)
                    self.txt_text_preview.setPlainText(content)
                    font = QFont("Consolas")
                    font.setStyleHint(QFont.Monospace)
                    font.setPointSize(10)
                    self.txt_text_preview.setFont(font)
                    self.txt_text_preview.show()
                    self.lbl_image_preview.hide()
                    self.lbl_info_preview.hide()
                    return
                except:
                    pass

        except Exception as e:
            pass

        # 3. 그 외
        self._set_preview_info(path)
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

    def _set_preview_info(self, path, is_folder=False):
        name = os.path.basename(path) or path
        self.lbl_preview_name.setText(name)
        self.lbl_preview_path.setText(path)

        if is_folder:
            self.lbl_preview_meta.setText(strings.tr("msg_preview_meta_folder"))
            self.preview_info.show()
            return

        size_str = strings.tr("msg_preview_meta_unknown")
        mtime_str = strings.tr("msg_preview_meta_unknown")
        try:
            size_str = self.format_size(os.path.getsize(path))
        except Exception:
            pass
        try:
            mtime = os.path.getmtime(path)
            mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        except Exception:
            pass

        self.lbl_preview_meta.setText(
            strings.tr("msg_preview_meta").format(size=size_str, mtime=mtime_str)
        )
        self.preview_info.show()

    # --- 기능 구현: 설정 저장/로드 ---
    def save_settings(self):
        self.settings.setValue("app/geometry", self.saveGeometry())
        self.settings.setValue("app/splitter", self.splitter.saveState())
        self.settings.setValue("filter/extensions", self.txt_extensions.text())
        self.settings.setValue("filter/min_size", self.spin_min_size.value())
        self.settings.setValue("filter/protect_system", self.chk_protect_system.isChecked())
        self.settings.setValue("filter/byte_compare", self.chk_byte_compare.isChecked())
        self.settings.setValue("filter/same_name", self.chk_same_name.isChecked())
        self.settings.setValue("filter/name_only", self.chk_name_only.isChecked())
        self.settings.setValue("filter/use_trash", self.chk_use_trash.isChecked())
        self.settings.setValue("filter/use_similar_image", self.chk_similar_image.isChecked())
        self.settings.setValue("filter/similarity_threshold", self.spin_similarity.value())
        self.settings.setValue("folders", self.selected_folders)
        
        # 단축키 저장
        if self.custom_shortcuts:
            self.settings.setValue("app/shortcuts", json.dumps(self.custom_shortcuts))
        
        # 제외 패턴 저장
        if self.exclude_patterns:
            self.settings.setValue("filter/exclude_patterns", json.dumps(self.exclude_patterns))

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
        self.chk_use_trash.setChecked(str(self.settings.value("filter/use_trash", False)).lower() == 'true')
        self.chk_similar_image.setChecked(str(self.settings.value("filter/use_similar_image", False)).lower() == 'true')
        similarity = self.settings.value("filter/similarity_threshold", 0.9)
        try:
            self.spin_similarity.setValue(float(similarity))
        except (TypeError, ValueError):
            self.spin_similarity.setValue(0.9)
        self._sync_filter_states()
        
        folders = self.settings.value("folders", [])
        # 리스트가 아니라 단일 문자열로 저장되는 경우가 있어 타입 체크
        if isinstance(folders, str): folders = [folders]
        elif not isinstance(folders, list): folders = []
        
        self.selected_folders = [f for f in folders if os.path.exists(f)]
        
        # Populate ListWidget
        self.list_folders.clear()
        for f in self.selected_folders:
            self.list_folders.addItem(f)
        self._on_folders_changed()

        # Restore Theme
        theme = self.settings.value("app/theme", "light")
        self.action_theme.setChecked(theme == "dark")
        
        # Issue #14: Restore Language setting
        lang = self.settings.value("app/language", "ko")
        strings.set_language(lang)
        
        # 단축키 로드
        shortcuts_json = self.settings.value("app/shortcuts", "")
        if shortcuts_json:
            try:
                self.custom_shortcuts = json.loads(shortcuts_json)
                self._apply_shortcuts(self.custom_shortcuts)
            except:
                pass
        
        # 제외 패턴 로드
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

    def _restore_cached_session(self):
        self.cache_manager.cleanup_old_sessions()
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

        if session.get("status") == "completed":
            results = self.cache_manager.load_scan_results(self.current_session_id)
            if results:
                selected_paths = self.cache_manager.load_selected_paths(self.current_session_id)
                self.scan_results = results
                pruned = self._prune_missing_results()
                if pruned:
                    results = self.scan_results
                    selected_paths = [p for p in selected_paths if os.path.exists(p)]
                self.tree_widget.populate(results, selected_paths=selected_paths)
                self.filter_results_tree(self.txt_result_filter.text())
                self._set_results_view(bool(results))
                self._update_results_summary(len(selected_paths))
                self.status_label.setText(strings.tr("msg_results_loaded").format(len(results)))
                # Restore UX: bring the user to the focused results page when data is available.
                try:
                    self._navigate_to("results")
                except Exception:
                    pass
                if pruned and self.current_session_id:
                    self.cache_manager.save_scan_results(self.current_session_id, results)
                    self.cache_manager.save_selected_paths(self.current_session_id, selected_paths)
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
                "error": "Error",
                "abandoned": "Abandoned",
            }
            stage_label = stage_map.get(stage_code, stage_code or strings.tr("status_ready"))

            updated_at = session.get("updated_at")
            if updated_at:
                dt = datetime.fromtimestamp(float(updated_at)).strftime("%Y-%m-%d %H:%M")
            else:
                dt = "—"

            msg = str(session.get("progress_message") or "").strip()
            prog = session.get("progress")
            if isinstance(prog, int) and prog:
                msg = f"{msg}\n{prog}%" if msg else f"{prog}%"
            if not msg:
                msg = "—"

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

    def _get_scan_hash_config(self, config: dict) -> dict:
        hash_config = dict(config)
        hash_config.pop("use_trash", None)
        if not hash_config.get("use_similar_image"):
            hash_config.pop("similarity_threshold", None)
        return hash_config

    def on_checked_files_changed(self, paths):
        self._update_results_summary(len(paths))
        self._update_action_buttons_state(selected_count=len(paths))
        if not self.current_session_id:
            return
        self._pending_selected_paths = paths
        self._selection_save_timer.start(400)

    def _flush_selected_paths(self):
        if not self.current_session_id:
            return
        self.cache_manager.save_selected_paths(self.current_session_id, self._pending_selected_paths)

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

        # File item context
        if path and os.path.exists(path):
            action_open = QAction(self.style().standardIcon(QStyle.SP_FileIcon), strings.tr("ctx_open"), self)
            action_open.triggered.connect(lambda: self.open_file(item, 0))
            menu.addAction(action_open)

            action_folder = QAction(self.style().standardIcon(QStyle.SP_DirIcon), strings.tr("ctx_open_folder"), self)
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
                    keep_set, delete_set = decide_keep_delete_for_group(paths, self.selection_rules)
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
                            canonical = min(paths, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
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

    # === 새 기능 메서드들 ===
    
    def save_scan_results(self):
        """스캔 결과를 JSON으로 저장"""
        if not self.scan_results:
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_files_selected"))
            return
        
        path, _ = QFileDialog.getSaveFileName(
            self, strings.tr("action_save_results"),
            "scan_results.json", "JSON Files (*.json)"
        )
        if not path:
            return
        
        try:
            # 결과 직렬화 (키 튜플을 문자열로 변환)
            serializable = {}
            for key, paths in self.scan_results.items():
                str_key = json.dumps(key)
                serializable[str_key] = paths
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            
            self.status_label.setText(strings.tr("msg_results_saved").format(path))
        except Exception as e:
            QMessageBox.critical(self, strings.tr("app_title"), strings.tr("err_save").format(e))
    
    def load_scan_results(self):
        """저장된 스캔 결과를 불러오기"""
        path, _ = QFileDialog.getOpenFileName(
            self, strings.tr("action_load_results"),
            "", "JSON Files (*.json)"
        )
        if not path:
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 키 역변환
            self.scan_results = {}
            for str_key, paths in data.items():
                key = tuple(json.loads(str_key))
                self.scan_results[key] = paths
            
            self.tree_widget.populate(self.scan_results)
            self.filter_results_tree(self.txt_result_filter.text())
            self._set_results_view(bool(self.scan_results))
            self._update_results_summary(0)
            self.status_label.setText(strings.tr("msg_results_loaded").format(len(self.scan_results)))
            try:
                self._navigate_to("results")
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, strings.tr("app_title"), strings.tr("err_load").format(e))
    
    def open_preset_dialog(self):
        """프리셋 관리 다이얼로그 열기"""
        current_config = self._get_current_config()
        dlg = PresetDialog(self.preset_manager, current_config, self)
        if dlg.exec() and dlg.selected_config:
            self._apply_config(dlg.selected_config)
    
    def open_exclude_patterns_dialog(self):
        """제외 패턴 설정 다이얼로그 열기"""
        dlg = ExcludePatternsDialog(self.exclude_patterns, self)
        if dlg.exec():
            self.exclude_patterns = dlg.get_patterns()
            # 제외 패턴 수 표시
            if self.exclude_patterns:
                self.btn_exclude_patterns.setText(
                    f"{strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})"
                )
            else:
                self.btn_exclude_patterns.setText(strings.tr("btn_exclude_patterns"))
    
    def open_shortcut_settings(self):
        """단축키 설정 다이얼로그 열기"""
        dlg = ShortcutSettingsDialog(self.custom_shortcuts, self)
        if dlg.exec():
            self.custom_shortcuts = dlg.get_shortcuts()
            self._apply_shortcuts(self.custom_shortcuts)
    
    def _get_current_config(self) -> dict:
        """현재 스캔 설정을 딕셔너리로 반환"""
        return {
            'folders': self.selected_folders.copy(),
            'extensions': self.txt_extensions.text(),
            'min_size_kb': self.spin_min_size.value(),
            'protect_system': self.chk_protect_system.isChecked(),
            'byte_compare': self.chk_byte_compare.isChecked(),
            'same_name': self.chk_same_name.isChecked(),
            'name_only': self.chk_name_only.isChecked(),
            'exclude_patterns': self.exclude_patterns.copy(),
            'use_trash': self.chk_use_trash.isChecked(),
            'use_similar_image': self.chk_similar_image.isChecked(),
            'similarity_threshold': self.spin_similarity.value()
        }
    
    def _apply_config(self, config: dict):
        """딕셔너리 설정을 UI에 적용"""
        # 폴더
        if 'folders' in config:
            self.selected_folders = config['folders']
            self.list_folders.clear()
            for f in self.selected_folders:
                self.list_folders.addItem(f)
            self._on_folders_changed()
        
        # 필터
        if 'extensions' in config:
            self.txt_extensions.setText(config['extensions'])
        if 'min_size_kb' in config:
            self.spin_min_size.setValue(config['min_size_kb'])
        
        # 체크박스
        if 'protect_system' in config:
            self.chk_protect_system.setChecked(config['protect_system'])
        if 'byte_compare' in config:
            self.chk_byte_compare.setChecked(config['byte_compare'])
        if 'same_name' in config:
            self.chk_same_name.setChecked(config['same_name'])
        if 'name_only' in config:
            self.chk_name_only.setChecked(config['name_only'])
        if 'use_trash' in config:
            self.chk_use_trash.setChecked(config['use_trash'])
        if 'use_similar_image' in config:
            self.chk_similar_image.setChecked(config['use_similar_image'])
        if 'similarity_threshold' in config:
            self.spin_similarity.setValue(config['similarity_threshold'])
        
        # 제외 패턴
        if 'exclude_patterns' in config:
            self.exclude_patterns = config['exclude_patterns']
            if self.exclude_patterns:
                self.btn_exclude_patterns.setText(
                    f"{strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})"
                )
        self._sync_filter_states()
    
    def _apply_shortcuts(self, shortcuts: dict):
        """커스텀 단축키를 액션에 적용"""
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
            dt = datetime.fromtimestamp(float(created)).strftime("%Y-%m-%d %H:%M") if created else "—"

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
            dt = datetime.fromtimestamp(float(created)).strftime("%Y-%m-%d %H:%M") if created else "—"

            i0 = QTableWidgetItem(str(op_id))
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
        dlg.exec()

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
                keep_set, delete_set = decide_keep_delete_for_group(paths, rules)
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
        self._op_queue = list(ops or [])
        self._start_next_operation()

    def _start_next_operation(self):
        if not self._op_queue:
            return
        op = self._op_queue.pop(0)
        self._start_operation(op, allow_queue_continue=True)

    def _start_operation(self, op: Operation, allow_queue_continue: bool = False):
        if self._op_worker and self._op_worker.isRunning():
            return

        # Mandatory preflight for destructive operations.
        rep = None
        if op.op_type in ("delete_quarantine", "delete_trash"):
            if op.op_type == "delete_quarantine":
                qdir = None
                try:
                    qdir = self.quarantine_manager.get_quarantine_dir()
                except Exception:
                    qdir = None
                rep = self.preflight_analyzer.analyze_delete(op.paths, quarantine_dir=qdir)
            else:
                rep = self.preflight_analyzer.analyze_delete_trash(op.paths)
            dlg = PreflightDialog(rep, self)
            if not dlg.exec():
                self._op_queue.clear()
                return
            if not dlg.can_proceed:
                self._op_queue.clear()
                return

            # Final confirmation (includes filter/hidden warning + size).
            try:
                eligible = list(getattr(rep, "eligible_paths", []) or [])
                count = len(eligible)
                opt = getattr(op, "options", {}) or {}
                filter_active = bool(opt.get("filter_active"))
                try:
                    visible_checked = int(opt.get("visible_checked") or 0)
                except Exception:
                    visible_checked = 0
                visible_checked = min(visible_checked, count) if count else visible_checked

                size_str = self.format_size(int(getattr(rep, "bytes_total", 0) or 0))
                info_lines = [
                    strings.tr("confirm_delete_selected_counts").format(total=count, visible=visible_checked),
                    strings.tr("msg_total_size").format(size=size_str),
                ]
                if filter_active:
                    info_lines.append(strings.tr("msg_delete_includes_hidden"))

                if op.op_type == "delete_trash":
                    msg = strings.tr("confirm_trash_delete").format(count)
                else:
                    msg = strings.tr("confirm_delete_quarantine").format(count=count)
                if info_lines:
                    msg = msg + "\n\n" + "\n".join(info_lines)

                res = QMessageBox.question(
                    self,
                    strings.tr("confirm_delete_title"),
                    msg,
                    QMessageBox.Yes | QMessageBox.No,
                )
                if res != QMessageBox.Yes:
                    self._op_queue.clear()
                    return

                # Only proceed with eligible paths (preflight filtered).
                op.paths = eligible
            except Exception:
                pass
        elif op.op_type == "hardlink_consolidate":
            rep = self.preflight_analyzer.analyze_hardlink(
                str(op.options.get("canonical") or ""),
                list(op.options.get("targets") or []),
            )
            dlg = PreflightDialog(rep, self)
            if not dlg.exec():
                self._op_queue.clear()
                return
            if not dlg.can_proceed:
                self._op_queue.clear()
                return

        # Progress dialog (unified)
        self._op_progress = QProgressDialog(strings.tr("status_working"), strings.tr("btn_cancel"), 0, 100, self)
        self._op_progress.setWindowTitle(strings.tr("app_title"))
        self._op_progress.setAutoClose(False)
        self._op_progress.setAutoReset(False)
        self._op_progress.canceled.connect(self._cancel_operation)
        self._op_progress.show()

        self._op_worker = OperationWorker(
            cache_manager=self.cache_manager,
            quarantine_manager=self.quarantine_manager,
            history_manager=self.history_manager,
            op=op,
        )
        self._op_worker.progress_updated.connect(self._on_op_progress)
        self._op_worker.operation_result.connect(lambda result: self._on_op_finished(result, allow_queue_continue))
        self._op_worker.start()

    def _cancel_operation(self):
        try:
            if self._op_worker:
                self._op_worker.stop()
        except Exception:
            pass

    def _on_op_progress(self, val: int, msg: str):
        try:
            if self._op_progress:
                self._op_progress.setValue(int(val))
                self._op_progress.setLabelText(str(msg or ""))
        except Exception:
            pass

    def _on_op_finished(self, result, allow_queue_continue: bool):
        try:
            if self._op_progress:
                self._op_progress.setValue(100)
                self._op_progress.close()
        except Exception:
            pass
        self._op_progress = None

        try:
            self._op_worker = None
        except Exception:
            pass

        # Refresh tools lists after any op.
        try:
            if result and getattr(result, "op_type", "") in ("delete_quarantine", "hardlink_consolidate", "purge"):
                self._apply_quarantine_retention()
            self.refresh_quarantine_list()
            self.refresh_operations_list()
        except Exception:
            pass

        # Sync scan results for destructive operations.
        try:
            if result and getattr(result, "op_type", "") in ("delete_quarantine", "delete_trash", "hardlink_consolidate"):
                removed = list(getattr(result, "succeeded", []) or [])
                if removed:
                    self._remove_paths_from_results(removed)
                    self.tree_widget.populate(self.scan_results, selected_paths=self.cache_manager.load_selected_paths(self.current_session_id) if self.current_session_id else [])
                    self.filter_results_tree(self.txt_result_filter.text())
                    self._set_results_view(bool(self.scan_results))
                    self._update_results_summary()
                    self._update_action_buttons_state()
                    if self.current_session_id:
                        self.cache_manager.save_scan_results(self.current_session_id, self.scan_results)
        except Exception:
            pass

        # Show message
        try:
            msg = getattr(result, "message", "") or strings.tr("status_done")
            self.status_label.setText(msg)
            if hasattr(self, "toast_manager") and self.toast_manager:
                if getattr(result, "status", "") == "failed":
                    self.toast_manager.error(msg, duration=3500)
                elif getattr(result, "status", "") == "partial":
                    self.toast_manager.warning(msg, duration=3500)
                else:
                    self.toast_manager.success(msg, duration=2500)
        except Exception:
            pass

        # Offer retry for failures when not queued.
        try:
            failed = list(getattr(result, "failed", []) or [])
            if failed and not allow_queue_continue:
                res = QMessageBox.question(
                    self,
                    strings.tr("app_title"),
                    strings.tr("msg_retry_failed").format(len(failed)),
                    QMessageBox.Yes | QMessageBox.No,
                )
                if res == QMessageBox.Yes:
                    paths = [p for p, _r in failed if p]
                    if getattr(result, "op_type", "") in ("delete_quarantine", "delete_trash"):
                        self._start_operation(Operation(getattr(result, "op_type", ""), paths=paths))
                        return
        except Exception:
            pass

        # Continue queued operations if requested and not cancelled.
        if allow_queue_continue and self._op_queue and getattr(result, "status", "") not in ("cancelled", "failed"):
            self._start_next_operation()
        else:
            self._op_queue.clear()
    
    def _on_page_changed(self, page_name: str):
        """Handle sidebar navigation - switch pages and show toast"""
        try:
            # Page index mapping
            page_indices = {
                "scan": 0,
                "results": 1,
                "tools": 2,
                "settings": 3,
            }
            
            page_names = {
                "scan": strings.tr("nav_scan"),
                "results": strings.tr("nav_results"),
                "tools": strings.tr("nav_tools"),
                "settings": strings.tr("nav_settings"),
            }
            
            if page_name in page_indices:
                # Switch to the selected page
                self.page_stack.setCurrentIndex(page_indices[page_name])
                if page_name == "tools":
                    try:
                        self.refresh_quarantine_list()
                        self.refresh_operations_list()
                    except Exception:
                        pass
                
                # Update status label
                if page_name in page_names:
                    # Don't overwrite scan progress messages while scanning.
                    is_scanning = bool(getattr(self, "btn_stop_scan", None) and self.btn_stop_scan.isEnabled())
                    if not is_scanning:
                        self.status_label.setText(page_names[page_name])
                
                # Show toast notification
                if hasattr(self, 'toast_manager') and self.toast_manager:
                    self.toast_manager.info(page_names[page_name], duration=2000)
                    
        except Exception as e:
            print(f"Navigation error: {page_name} - {e}")

    def _navigate_to(self, page_name: str):
        if hasattr(self, "sidebar"):
            self.sidebar.set_page(page_name)
        self._on_page_changed(page_name)


