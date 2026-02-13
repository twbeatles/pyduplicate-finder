from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel, QProgressBar, QCheckBox, QMessageBox, QGroupBox, QTreeWidget, QTreeWidgetItem, QToolBar, QSpinBox, QLineEdit, QMenu, QSplitter, QTextEdit, QScrollArea, QStyle, QProgressDialog, QToolButton, QSizePolicy, QListWidget, QDoubleSpinBox, QInputDialog, QStackedWidget, QFrame)
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
from src.ui.empty_folder_dialog import EmptyFolderDialog
from src.ui.components.results_tree import ResultsTreeWidget
from src.ui.components.sidebar import Sidebar
from src.ui.components.toast import ToastManager
from src.ui.dialogs.preset_dialog import PresetDialog
from src.ui.dialogs.exclude_patterns_dialog import ExcludePatternsDialog
from src.ui.dialogs.shortcut_settings_dialog import ShortcutSettingsDialog
from src.utils.i18n import strings
from src.ui.theme import ModernTheme


class DuplicateFinderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(strings.tr("app_title"))
        self.resize(1200, 850)
        self.selected_folders = []
        self.scan_results = {}
        self.history_manager = HistoryManager()
        self.cache_manager = CacheManager()
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

        # Current scan page layout mode: "scan" (shows options) or "results" (results-focused).
        self._scan_page_mode = "scan"
        self._scan_splitter_sizes_scan = None
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
        self.history_manager.cleanup()
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
        
        # === PAGE 0: SCAN PAGE (Contains splitter with settings + results) ===
        self.scan_page = QWidget()
        main_layout = QVBoxLayout(self.scan_page)  # main_layout refers to scan page now
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 12, 16, 12)
        self.page_stack.addWidget(self.scan_page)

        # === GLOBAL VERTICAL SPLITTER ===
        self.main_v_splitter = QSplitter(Qt.Vertical)
        self.main_v_splitter.setHandleWidth(6) 

        # === TOP CONTAINER: Settings & Scan Actions (Card style) ===
        self.top_container = QWidget()
        self.top_container.setObjectName("folder_card")
        top_main_layout = QVBoxLayout(self.top_container)
        top_main_layout.setSpacing(12)
        top_main_layout.setContentsMargins(20, 16, 20, 16)

        # --- ROW 1: Folder Selection Header ---
        folder_header = QHBoxLayout()
        folder_header.setSpacing(8)
        
        folder_label = QLabel(strings.tr("grp_search_loc"))
        folder_label.setObjectName("card_title")
        folder_header.addWidget(folder_label)

        self.lbl_folder_count = QLabel("")
        self.lbl_folder_count.setObjectName("results_meta")
        folder_header.addWidget(self.lbl_folder_count)
        
        self.btn_add_folder = QPushButton(strings.tr("btn_add_folder"))
        self.btn_add_folder.setMinimumHeight(32)
        self.btn_add_folder.setCursor(Qt.PointingHandCursor)
        self.btn_add_folder.clicked.connect(self.add_folder)
        
        self.btn_add_drive = QPushButton(strings.tr("btn_add_drive"))
        self.btn_add_drive.setMinimumHeight(32)
        self.btn_add_drive.setCursor(Qt.PointingHandCursor)
        self.btn_add_drive.clicked.connect(self.add_drive_dialog)

        self.btn_remove_folder = QPushButton(strings.tr("btn_remove_folder"))
        self.btn_remove_folder.setMinimumHeight(32)
        self.btn_remove_folder.setCursor(Qt.PointingHandCursor)
        self.btn_remove_folder.setToolTip(strings.tr("btn_remove_folder"))
        self.btn_remove_folder.clicked.connect(self.remove_selected_folder)

        self.btn_clear_folder = QPushButton(strings.tr("btn_clear"))
        self.btn_clear_folder.setMinimumHeight(32)
        self.btn_clear_folder.setCursor(Qt.PointingHandCursor)
        self.btn_clear_folder.clicked.connect(self.clear_folders)

        folder_header.addStretch()
        folder_header.addWidget(self.btn_add_folder)
        folder_header.addWidget(self.btn_add_drive)
        folder_header.addWidget(self.btn_remove_folder)
        folder_header.addWidget(self.btn_clear_folder)
        
        top_main_layout.addLayout(folder_header)
        
        # --- ROW 2: Folder List ---
        self.list_folders = QListWidget()
        self.list_folders.setMinimumHeight(50)
        self.list_folders.setMaximumHeight(100)
        top_main_layout.addWidget(self.list_folders)

        # --- ROW 3: Collapsible Filter Options ---
        # Filter Header (Toggle Button)
        self.btn_filter_toggle = QPushButton(strings.tr("lbl_filter_options") + " ▼")
        self.btn_filter_toggle.setObjectName("filter_header")
        self.btn_filter_toggle.setCheckable(True)
        self.btn_filter_toggle.setChecked(True)
        self.btn_filter_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_filter_toggle.clicked.connect(self._toggle_filter_panel)
        top_main_layout.addWidget(self.btn_filter_toggle)
        
        # Filter Content Container
        self.filter_container = QWidget()
        self.filter_container.setObjectName("filter_card")
        filter_main_layout = QVBoxLayout(self.filter_container)
        filter_main_layout.setSpacing(12)
        filter_main_layout.setContentsMargins(12, 12, 12, 12)
        
        # --- Filter Section: Basic Filters ---
        self.lbl_filter_basic = QLabel(strings.tr("hdr_filters_basic"))
        self.lbl_filter_basic.setObjectName("section_header")
        filter_main_layout.addWidget(self.lbl_filter_basic)

        # --- Filter Row 1: Basic Filters ---
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(20)
        
        # Extension Filter
        ext_layout = QHBoxLayout()
        ext_layout.setSpacing(8)
        self.lbl_ext = QLabel(strings.tr("lbl_ext"))
        self.lbl_ext.setObjectName("filter_label")
        ext_layout.addWidget(self.lbl_ext)
        self.txt_extensions = QLineEdit()
        self.txt_extensions.setPlaceholderText(strings.tr("ph_ext"))
        self.txt_extensions.setMinimumWidth(120)
        self.txt_extensions.setMaximumWidth(180)
        self.txt_extensions.setMinimumHeight(32)
        ext_layout.addWidget(self.txt_extensions)
        row1_layout.addLayout(ext_layout)
        
        # Min Size Filter
        size_layout = QHBoxLayout()
        size_layout.setSpacing(8)
        self.lbl_min_size = QLabel(strings.tr("lbl_min_size"))
        self.lbl_min_size.setObjectName("filter_label")
        size_layout.addWidget(self.lbl_min_size)
        self.spin_min_size = QSpinBox()
        self.spin_min_size.setRange(0, 10000000)
        self.spin_min_size.setValue(0)
        self.spin_min_size.setSuffix(" KB")
        self.spin_min_size.setMinimumWidth(100)
        self.spin_min_size.setMaximumWidth(140)
        self.spin_min_size.setMinimumHeight(32)
        size_layout.addWidget(self.spin_min_size)
        row1_layout.addLayout(size_layout)
        
        filter_main_layout.addLayout(row1_layout)
        
        # --- Filter Section: Comparison ---
        self.lbl_filter_compare = QLabel(strings.tr("hdr_filters_compare"))
        self.lbl_filter_compare.setObjectName("section_header")
        filter_main_layout.addWidget(self.lbl_filter_compare)

        # --- Filter Row 2: Comparison Options ---
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(20)
        
        self.chk_same_name = QCheckBox(strings.tr("chk_same_name"))
        self.chk_same_name.setToolTip(strings.tr("tip_same_name"))
        self.chk_name_only = QCheckBox(strings.tr("chk_name_only"))
        self.chk_name_only.setToolTip(strings.tr("tip_name_only"))
        self.chk_byte_compare = QCheckBox(strings.tr("chk_byte_compare"))

        row2_layout.addWidget(self.chk_same_name)
        row2_layout.addWidget(self.chk_name_only)
        row2_layout.addWidget(self.chk_byte_compare)
        row2_layout.addStretch()

        filter_main_layout.addLayout(row2_layout)

        # --- Filter Section: Advanced ---
        self.lbl_filter_advanced = QLabel(strings.tr("hdr_filters_advanced"))
        self.lbl_filter_advanced.setObjectName("section_header")
        filter_main_layout.addWidget(self.lbl_filter_advanced)

        # --- Filter Row 3: Advanced Options ---
        row3_layout = QHBoxLayout()
        row3_layout.setSpacing(20)

        self.chk_protect_system = QCheckBox(strings.tr("chk_protect_system"))
        self.chk_protect_system.setChecked(True)
        self.chk_use_trash = QCheckBox(strings.tr("chk_use_trash"))
        self.chk_use_trash.setToolTip(strings.tr("tip_use_trash"))
        
        row3_layout.addWidget(self.chk_protect_system)
        row3_layout.addWidget(self.chk_use_trash)
        row3_layout.addWidget(self._create_separator())
        
        # Similar Image Section
        self.chk_similar_image = QCheckBox(strings.tr("chk_similar_image"))
        self.chk_similar_image.setToolTip(strings.tr("tip_similar_image"))
        row3_layout.addWidget(self.chk_similar_image)
        
        self.lbl_similarity = QLabel(strings.tr("lbl_similarity_threshold"))
        self.spin_similarity = QDoubleSpinBox()
        self.spin_similarity.setRange(0.1, 1.0)
        self.spin_similarity.setSingleStep(0.05)
        self.spin_similarity.setValue(0.9)
        self.spin_similarity.setDecimals(2)
        self.spin_similarity.setMinimumWidth(80)
        self.spin_similarity.setEnabled(False)
        row3_layout.addWidget(self.lbl_similarity)
        row3_layout.addWidget(self.spin_similarity)
        row3_layout.addWidget(self._create_separator())
        
        # Exclude Patterns Button
        self.btn_exclude_patterns = QPushButton(strings.tr("btn_exclude_patterns"))
        self.btn_exclude_patterns.setMinimumHeight(32)
        self.btn_exclude_patterns.setObjectName("btn_icon")
        self.btn_exclude_patterns.setCursor(Qt.PointingHandCursor)
        self.btn_exclude_patterns.clicked.connect(self.open_exclude_patterns_dialog)
        row3_layout.addWidget(self.btn_exclude_patterns)
        
        row3_layout.addStretch()
        
        filter_main_layout.addLayout(row3_layout)

        self.chk_name_only.toggled.connect(self._sync_filter_states)
        self.chk_similar_image.toggled.connect(self._sync_filter_states)
        
        top_main_layout.addWidget(self.filter_container)
        self._sync_filter_states()

        # --- ROW 4: Action Buttons ---
        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)
        
        self.btn_start_scan = QPushButton(strings.tr("btn_start_scan"))
        self.btn_start_scan.setMinimumHeight(40)
        self.btn_start_scan.setMinimumWidth(150)
        self.btn_start_scan.setCursor(Qt.PointingHandCursor)
        self.btn_start_scan.setObjectName("btn_primary")
        self.btn_start_scan.clicked.connect(self.start_scan)

        self.btn_stop_scan = QPushButton(strings.tr("scan_stop"))
        self.btn_stop_scan.setMinimumHeight(40)
        self.btn_stop_scan.setCursor(Qt.PointingHandCursor)
        self.btn_stop_scan.clicked.connect(self.stop_scan)
        self.btn_stop_scan.setEnabled(False)

        action_layout.addWidget(self.btn_start_scan)
        action_layout.addWidget(self.btn_stop_scan)
        self.lbl_scan_stage = QLabel(
            strings.tr("msg_scan_stage").format(stage=strings.tr("status_ready"))
        )
        self.lbl_scan_stage.setObjectName("stage_badge")
        action_layout.addWidget(self.lbl_scan_stage)
        action_layout.addStretch()
        
        top_main_layout.addLayout(action_layout)

        # Add Top Container to V-Splitter
        self.main_v_splitter.addWidget(self.top_container)

        # === BOTTOM CONTAINER: Results Tree + Preview ===
        # Use existing Horizontal splitter, but put it into the V-Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(12)
        
        # [Left] Tree Widget Container
        self.tree_container = QWidget()
        self.tree_container.setObjectName("result_card")
        tree_layout = QVBoxLayout(self.tree_container)
        tree_layout.setContentsMargins(12, 12, 12, 12)
        tree_layout.setSpacing(8)

        # Results header
        results_header = QHBoxLayout()
        results_header.setSpacing(8)
        self.lbl_results_title = QLabel(strings.tr("nav_results"))
        self.lbl_results_title.setObjectName("results_title")
        self.lbl_results_meta = QLabel("")
        self.lbl_results_meta.setObjectName("results_meta")
        results_header.addWidget(self.lbl_results_title)
        results_header.addStretch()
        # In results-focused mode, provide a quick way back to scan options.
        self.btn_show_options = QPushButton(strings.tr("btn_show_options"))
        self.btn_show_options.setMinimumHeight(28)
        self.btn_show_options.setCursor(Qt.PointingHandCursor)
        self.btn_show_options.setObjectName("btn_icon")
        self.btn_show_options.clicked.connect(lambda: self._navigate_to("scan"))
        self.btn_show_options.setVisible(False)
        results_header.addWidget(self.btn_show_options)
        results_header.addWidget(self.lbl_results_meta)
        tree_layout.addLayout(results_header)
        
        # Filter Input
        filter_row = QHBoxLayout()
        self.txt_result_filter = QLineEdit()
        self.txt_result_filter.setPlaceholderText("🔍 " + strings.tr("ph_filter_results"))
        self.txt_result_filter.setClearButtonEnabled(True)
        self.txt_result_filter.textChanged.connect(self.filter_results_tree)
        filter_row.addWidget(self.txt_result_filter)
        filter_row.addStretch()
        self.lbl_filter_count = QLabel("")
        self.lbl_filter_count.setObjectName("filter_count")
        filter_row.addWidget(self.lbl_filter_count)
        tree_layout.addLayout(filter_row)
        
        self.tree_widget = ResultsTreeWidget()
        self.tree_widget.itemDoubleClicked.connect(self.open_file) 
        self.tree_widget.currentItemChanged.connect(self.update_preview)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.tree_widget.files_checked.connect(self.on_checked_files_changed)
        
        self.results_stack = QStackedWidget()
        self.results_stack.setObjectName("results_stack")

        empty_wrap = QWidget()
        empty_layout = QVBoxLayout(empty_wrap)
        empty_layout.setContentsMargins(24, 24, 24, 24)
        self.lbl_results_empty = QLabel(strings.tr("msg_no_results"))
        self.lbl_results_empty.setAlignment(Qt.AlignCenter)
        self.lbl_results_empty.setWordWrap(True)
        self.lbl_results_empty.setObjectName("empty_state")
        empty_layout.addStretch()
        empty_layout.addWidget(self.lbl_results_empty)

        # Empty-state CTAs
        empty_btn_row = QHBoxLayout()
        empty_btn_row.setSpacing(10)
        self.btn_results_empty_add_folder = QPushButton(strings.tr("btn_add_folder"))
        self.btn_results_empty_add_folder.setMinimumHeight(40)
        self.btn_results_empty_add_folder.setCursor(Qt.PointingHandCursor)
        self.btn_results_empty_add_folder.clicked.connect(self.add_folder)
        empty_btn_row.addWidget(self.btn_results_empty_add_folder)

        self.btn_results_empty_start_scan = QPushButton(strings.tr("btn_start_scan"))
        self.btn_results_empty_start_scan.setMinimumHeight(40)
        self.btn_results_empty_start_scan.setCursor(Qt.PointingHandCursor)
        self.btn_results_empty_start_scan.setObjectName("btn_primary")
        self.btn_results_empty_start_scan.clicked.connect(self.start_scan)
        empty_btn_row.addWidget(self.btn_results_empty_start_scan)
        empty_layout.addLayout(empty_btn_row)

        empty_layout.addStretch()

        self.results_stack.addWidget(empty_wrap)
        self.results_stack.addWidget(self.tree_widget)
        tree_layout.addWidget(self.results_stack)

        self.splitter.addWidget(self.tree_container)

        # [Right] Preview Panel
        self.preview_container = QWidget()
        self.preview_container.setObjectName("preview_card")
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        
        self.lbl_preview_header = QLabel(strings.tr("lbl_preview"))
        self.lbl_preview_header.setAlignment(Qt.AlignCenter)
        self.lbl_preview_header.setStyleSheet("""
            font-weight: 600; 
            font-size: 14px;
            padding: 12px; 
            border-bottom: 1px solid palette(mid);
        """) 
        preview_layout.addWidget(self.lbl_preview_header)

        # Preview info panel
        self.preview_info = QWidget()
        self.preview_info.setObjectName("preview_info")
        info_layout = QVBoxLayout(self.preview_info)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(4)

        self.lbl_preview_name = QLabel("")
        self.lbl_preview_name.setObjectName("preview_name")
        self.lbl_preview_path = QLabel("")
        self.lbl_preview_path.setObjectName("preview_path")
        self.lbl_preview_path.setWordWrap(True)
        self.lbl_preview_meta = QLabel("")
        self.lbl_preview_meta.setObjectName("preview_meta")

        info_layout.addWidget(self.lbl_preview_name)
        info_layout.addWidget(self.lbl_preview_path)
        info_layout.addWidget(self.lbl_preview_meta)
        preview_layout.addWidget(self.preview_info)
        self.preview_info.hide()

        # Scroll Area for preview content
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QScrollArea.NoFrame)
        
        scroll_content = QWidget()
        scroll_content.setObjectName("preview_content")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(16, 16, 16, 16)
        scroll_layout.setSpacing(12)
        
        self.lbl_image_preview = QLabel()
        self.lbl_image_preview.setAlignment(Qt.AlignCenter)
        self.lbl_image_preview.hide()
        scroll_layout.addWidget(self.lbl_image_preview)

        self.txt_text_preview = QTextEdit()
        self.txt_text_preview.setReadOnly(True)
        self.txt_text_preview.hide()
        scroll_layout.addWidget(self.txt_text_preview)

        self.lbl_info_preview = QLabel(strings.tr("msg_select_file"))
        self.lbl_info_preview.setAlignment(Qt.AlignCenter)
        self.lbl_info_preview.setWordWrap(True)
        self.lbl_info_preview.setStyleSheet("color: palette(mid); font-size: 14px; padding: 40px;")
        scroll_layout.addWidget(self.lbl_info_preview)
        
        scroll_layout.addStretch()
        self.preview_scroll.setWidget(scroll_content)
        preview_layout.addWidget(self.preview_scroll)

        self.splitter.addWidget(self.preview_container)
        self.splitter.setSizes([700, 400])
        self.splitter.setCollapsible(0, False) # Tree view always visible
        self.splitter.setCollapsible(1, True) # Preview collapsible

        # Add Horizontal Splitter to Vertical Splitter
        self.main_v_splitter.addWidget(self.splitter)
        
        # Set V-Splitter Proportions (Top small, Bottom big)
        self.main_v_splitter.setStretchFactor(0, 1) # Top
        self.main_v_splitter.setStretchFactor(1, 10) # Bottom (much bigger)
        self.main_v_splitter.setCollapsible(0, True) # Allow collapsing top

        main_layout.addWidget(self.main_v_splitter)
        self.main_v_splitter.setSizes([260, 740])

        # === 4. 하단 선택 및 삭제 (Fixed at bottom) ===
        self.action_bar = QWidget()
        self.action_bar.setObjectName("action_bar")
        bottom_layout = QHBoxLayout(self.action_bar)
        bottom_layout.setSpacing(12)
        bottom_layout.setContentsMargins(16, 8, 16, 8)
        
        self.btn_select_smart = QToolButton()
        self.btn_select_smart.setText(strings.tr("btn_smart_select"))
        self.btn_select_smart.setToolTip(strings.tr("tip_smart_select"))
        self.btn_select_smart.setMinimumHeight(44)
        self.btn_select_smart.setObjectName("btn_secondary")
        self.btn_select_smart.setCursor(Qt.PointingHandCursor)
        self.btn_select_smart.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_select_smart.clicked.connect(self.select_duplicates_smart)
        
        # Smart Select Menu
        self.menu_smart_select = QMenu(self)
        
        # 1. Smart Select (Default)
        self.action_smart = QAction(strings.tr("btn_smart_select"), self)
        self.action_smart.triggered.connect(self.select_duplicates_smart)
        self.menu_smart_select.addAction(self.action_smart)
        
        self.menu_smart_select.addSeparator()
        
        # 2. Select Newest (Keep Oldest)
        self.action_newest = QAction(strings.tr("action_select_newest"), self)
        self.action_newest.setToolTip(strings.tr("tip_select_newest"))
        self.action_newest.triggered.connect(self.select_duplicates_newest)
        self.menu_smart_select.addAction(self.action_newest)
        
        # 3. Select Oldest (Keep Newest)
        self.action_oldest = QAction(strings.tr("action_select_oldest"), self)
        self.action_oldest.setToolTip(strings.tr("tip_select_oldest"))
        self.action_oldest.triggered.connect(self.select_duplicates_oldest)
        self.menu_smart_select.addAction(self.action_oldest)
        
        self.menu_smart_select.addSeparator()
        
        # 4. Select by Path Pattern
        self.action_pattern = QAction(strings.tr("action_select_pattern"), self)
        self.action_pattern.triggered.connect(self.select_duplicates_by_pattern)
        self.menu_smart_select.addAction(self.action_pattern)

        self.btn_select_smart.setMenu(self.menu_smart_select)
        
        self.btn_export = QPushButton(strings.tr("btn_export"))
        self.btn_export.setMinimumHeight(44)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self.export_results)

        self.btn_delete = QPushButton(strings.tr("btn_delete_selected"))
        self.btn_delete.setObjectName("btn_danger")
        self.btn_delete.setMinimumHeight(44)
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.clicked.connect(self.delete_selected_files)

        bottom_layout.addWidget(self.btn_select_smart)
        bottom_layout.addWidget(self.btn_export)

        # UX: show selection count / filter state next to actions
        self.lbl_action_meta = QLabel("")
        self.lbl_action_meta.setObjectName("filter_count")
        bottom_layout.addWidget(self.lbl_action_meta)

        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_delete)
        main_layout.addWidget(self.action_bar)

        self._set_results_view(False)
        self._update_results_summary(0)

        # === PAGE 1: RESULTS PAGE (Placeholder for now - can be used for dedicated results view) ===
        self.results_page = QWidget()
        results_layout = QVBoxLayout(self.results_page)
        results_layout.setContentsMargins(16, 12, 16, 12)
        self.lbl_results_page_title = QLabel(strings.tr("nav_results"))
        self.lbl_results_page_title.setObjectName("card_title")
        self.lbl_results_page_title.setStyleSheet("font-size: 18px; padding: 8px 0;")
        results_layout.addWidget(self.lbl_results_page_title)

        self.lbl_results_hint = QLabel(strings.tr("msg_results_page_hint"))
        self.lbl_results_hint.setObjectName("empty_state")
        self.lbl_results_hint.setWordWrap(True)
        results_layout.addWidget(self.lbl_results_hint)

        self.lbl_results_page_summary = QLabel("")
        self.lbl_results_page_summary.setObjectName("results_meta")
        results_layout.addWidget(self.lbl_results_page_summary)

        self.btn_go_scan = QPushButton(strings.tr("btn_go_scan"))
        self.btn_go_scan.setMinimumHeight(40)
        self.btn_go_scan.setCursor(Qt.PointingHandCursor)
        self.btn_go_scan.clicked.connect(lambda: self._navigate_to("scan"))
        results_layout.addWidget(self.btn_go_scan)
        results_layout.addStretch()
        self.page_stack.addWidget(self.results_page)
        
        # === PAGE 2: TOOLS PAGE ===
        self.tools_page = QWidget()
        tools_layout = QVBoxLayout(self.tools_page)
        tools_layout.setSpacing(16)
        tools_layout.setContentsMargins(16, 12, 16, 12)
        
        self.lbl_tools_title = QLabel(strings.tr("nav_tools"))
        self.lbl_tools_title.setObjectName("card_title")
        self.lbl_tools_title.setStyleSheet("font-size: 18px; padding: 8px 0;")
        tools_layout.addWidget(self.lbl_tools_title)

        self.lbl_tools_hint = QLabel(strings.tr("msg_tools_page_hint"))
        self.lbl_tools_hint.setObjectName("empty_state")
        self.lbl_tools_hint.setWordWrap(True)
        tools_layout.addWidget(self.lbl_tools_hint)

        self.lbl_tools_target = QLabel("")
        self.lbl_tools_target.setObjectName("filter_count")
        tools_layout.addWidget(self.lbl_tools_target)

        self.btn_tools_go_scan = QPushButton(strings.tr("btn_go_scan"))
        self.btn_tools_go_scan.setMinimumHeight(40)
        self.btn_tools_go_scan.setCursor(Qt.PointingHandCursor)
        self.btn_tools_go_scan.clicked.connect(lambda: self._navigate_to("scan"))
        self.btn_tools_go_scan.setVisible(False)
        tools_layout.addWidget(self.btn_tools_go_scan)
         
        # Empty Folder Finder Card
        empty_card = QWidget()
        empty_card.setObjectName("folder_card")
        empty_card_layout = QVBoxLayout(empty_card)
        empty_card_layout.setContentsMargins(20, 16, 20, 16)
        empty_card_layout.setSpacing(12)
        
        self.lbl_empty_title = QLabel(strings.tr("action_empty_finder"))
        self.lbl_empty_title.setObjectName("card_title")
        empty_card_layout.addWidget(self.lbl_empty_title)

        self.lbl_empty_desc = QLabel(strings.tr("msg_empty_finder_desc"))
        self.lbl_empty_desc.setWordWrap(True)
        self.lbl_empty_desc.setObjectName("empty_state")
        empty_card_layout.addWidget(self.lbl_empty_desc)
        
        self.btn_empty_tools = QPushButton(strings.tr("btn_scan_empty"))
        self.btn_empty_tools.setMinimumHeight(44)
        self.btn_empty_tools.setCursor(Qt.PointingHandCursor)
        self.btn_empty_tools.clicked.connect(self.open_empty_finder)
        empty_card_layout.addWidget(self.btn_empty_tools)
        
        tools_layout.addWidget(empty_card)
        tools_layout.addStretch()
        self.page_stack.addWidget(self.tools_page)
        
        # === PAGE 3: SETTINGS PAGE ===
        self.settings_page = QWidget()
        settings_layout = QVBoxLayout(self.settings_page)
        settings_layout.setSpacing(16)
        settings_layout.setContentsMargins(16, 12, 16, 12)
        
        self.lbl_settings_title = QLabel(strings.tr("nav_settings"))
        self.lbl_settings_title.setObjectName("card_title")
        self.lbl_settings_title.setStyleSheet("font-size: 18px; padding: 8px 0;")
        settings_layout.addWidget(self.lbl_settings_title)

        self.lbl_settings_hint = QLabel(strings.tr("msg_settings_page_hint"))
        self.lbl_settings_hint.setObjectName("empty_state")
        self.lbl_settings_hint.setWordWrap(True)
        settings_layout.addWidget(self.lbl_settings_hint)
        
        # Theme Card
        theme_card = QWidget()
        theme_card.setObjectName("folder_card")
        theme_card_layout = QVBoxLayout(theme_card)
        theme_card_layout.setContentsMargins(20, 16, 20, 16)
        theme_card_layout.setSpacing(12)
        
        self.lbl_theme_title = QLabel(strings.tr("action_theme"))
        self.lbl_theme_title.setObjectName("card_title")
        theme_card_layout.addWidget(self.lbl_theme_title)
        
        self.btn_theme_settings = QPushButton(strings.tr("action_theme"))
        self.btn_theme_settings.setCheckable(True)
        self.btn_theme_settings.setMinimumHeight(44)
        self.btn_theme_settings.setCursor(Qt.PointingHandCursor)
        self.btn_theme_settings.clicked.connect(self.toggle_theme)
        theme_card_layout.addWidget(self.btn_theme_settings)
        
        settings_layout.addWidget(theme_card)
        
        # Shortcuts Card
        shortcut_card = QWidget()
        shortcut_card.setObjectName("folder_card")
        shortcut_card_layout = QVBoxLayout(shortcut_card)
        shortcut_card_layout.setContentsMargins(20, 16, 20, 16)
        shortcut_card_layout.setSpacing(12)
        
        self.lbl_shortcut_title = QLabel(strings.tr("action_shortcut_settings"))
        self.lbl_shortcut_title.setObjectName("card_title")
        shortcut_card_layout.addWidget(self.lbl_shortcut_title)
        
        self.btn_shortcuts_settings = QPushButton(strings.tr("action_shortcut_settings"))
        self.btn_shortcuts_settings.setMinimumHeight(44)
        self.btn_shortcuts_settings.setCursor(Qt.PointingHandCursor)
        self.btn_shortcuts_settings.clicked.connect(self.open_shortcut_settings)
        shortcut_card_layout.addWidget(self.btn_shortcuts_settings)
        
        settings_layout.addWidget(shortcut_card)
        
        # Presets Card
        preset_card = QWidget()
        preset_card.setObjectName("folder_card")
        preset_card_layout = QVBoxLayout(preset_card)
        preset_card_layout.setContentsMargins(20, 16, 20, 16)
        preset_card_layout.setSpacing(12)
        
        self.lbl_preset_title = QLabel(strings.tr("action_preset"))
        self.lbl_preset_title.setObjectName("card_title")
        preset_card_layout.addWidget(self.lbl_preset_title)
        
        self.btn_preset_settings = QPushButton(strings.tr("btn_manage_presets"))
        self.btn_preset_settings.setMinimumHeight(44)
        self.btn_preset_settings.setCursor(Qt.PointingHandCursor)
        self.btn_preset_settings.clicked.connect(self.open_preset_dialog)
        preset_card_layout.addWidget(self.btn_preset_settings)
        
        settings_layout.addWidget(preset_card)
        settings_layout.addStretch()
        self.page_stack.addWidget(self.settings_page)

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

    def _set_scan_page_mode(self, mode: str):
        """
        Make the Scan page either option-focused or results-focused.
        This keeps the UI simple and avoids duplicating the results view.
        """
        if not hasattr(self, "main_v_splitter") or not hasattr(self, "top_container"):
            return
        if mode not in ("scan", "results"):
            mode = "scan"
        if getattr(self, "_scan_page_mode", "scan") == mode:
            return

        if mode == "results":
            try:
                self._scan_splitter_sizes_scan = self.main_v_splitter.sizes()
            except Exception:
                self._scan_splitter_sizes_scan = None

            self.top_container.setVisible(False)
            if hasattr(self, "btn_show_options"):
                self.btn_show_options.setVisible(True)
            try:
                self.main_v_splitter.setSizes([0, 1])
            except Exception:
                pass

            # Focus results interaction
            if hasattr(self, "tree_widget"):
                self.tree_widget.setFocus()
        else:
            self.top_container.setVisible(True)
            if hasattr(self, "btn_show_options"):
                self.btn_show_options.setVisible(False)
            try:
                sizes = self._scan_splitter_sizes_scan
                if sizes and len(sizes) >= 2 and sizes[1] > 0:
                    self.main_v_splitter.setSizes(sizes)
                else:
                    self.main_v_splitter.setSizes([360, 640])
            except Exception:
                pass

        self._scan_page_mode = mode

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
        colors = ModernTheme.get_palette(theme_name)
        
        # Apply preview panel and filter panel specific styling
        extra_style = f"""
        QWidget#preview_content {{
            background-color: {colors['preview_bg']};
        }}
        
        QPushButton#filter_header {{
            text-align: left;
            padding: 10px 14px;
            font-weight: 600;
            font-size: 13px;
            border: 1px solid {colors['border']};
            border-radius: 8px;
            background-color: {colors['card_bg']};
            color: {colors['text_primary']};
        }}
        QPushButton#filter_header:checked {{
            border-bottom-left-radius: 0;
            border-bottom-right-radius: 0;
        }}
        QPushButton#filter_header:hover {{
            background-color: {colors['hover']};
        }}
        
        QWidget#filter_card {{
            border: 1px solid {colors['border']};
            border-top: none;
            border-bottom-left-radius: 8px;
            border-bottom-right-radius: 8px;
            background-color: {colors['card_bg']};
        }}
        
        QLabel#filter_label {{
            font-weight: 600;
            font-size: 12px;
            color: {colors['text_primary']};
            background: transparent;
            border: none;
        }}
        """
        
        self.setStyleSheet(style + extra_style)
        self.settings.setValue("app/theme", theme_name)
        
        # Propagate to custom widgets
        self.tree_widget.set_theme_mode(theme_name)
        
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
            import csv
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                # Keep CSV schema stable but avoid assuming scan_results key shape.
                writer.writerow(["Group ID", "Group Label", "Size (Bytes)", "File Path", "Modified Time"])
                
                group_id = 1
                for key, paths in self.scan_results.items():
                    # Human-friendly label for group key variants (hash/name-only/similar/etc.)
                    try:
                        if isinstance(key, (tuple, list)) and key:
                            if key[0] == "NAME_ONLY":
                                group_label = f"NAME_ONLY:{key[1] if len(key) > 1 else ''}"
                            else:
                                group_label = ""
                                for part in key:
                                    if isinstance(part, str) and part.startswith("similar_"):
                                        group_label = f"SIMILAR:{part.split('_', 1)[1] if '_' in part else part}"
                                        break
                                if not group_label:
                                    for part in key:
                                        if isinstance(part, str):
                                            group_label = part
                                            break
                        else:
                            group_label = str(key)
                    except Exception:
                        group_label = ""
                    for p in paths:
                        size = ""
                        try:
                            size = os.path.getsize(p)
                        except Exception:
                            size = ""

                        mtime_str = ""
                        try:
                            mtime = os.path.getmtime(p)
                            mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                        except: pass
                        
                        writer.writerow([group_id, group_label, size, p, mtime_str])
                    group_id += 1
            
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

        extra_lines = []
        if filter_active:
            extra_lines.append(
                strings.tr("confirm_delete_selected_counts").format(total=len(targets), visible=visible_checked)
            )
            extra_lines.append(strings.tr("msg_delete_includes_hidden"))
        extra_msg = ("\n\n" + "\n".join(extra_lines)) if extra_lines else ""
        
        if use_trash:
            res = QMessageBox.question(self, strings.tr("confirm_delete_title"), 
                                       strings.tr("confirm_trash_delete").format(len(targets)) + extra_msg,
                                       QMessageBox.Yes | QMessageBox.No)
        else:
            res = QMessageBox.question(self, strings.tr("confirm_delete_title"), 
                                       strings.tr("confirm_delete_msg").format(len(targets)) + extra_msg,
                                       QMessageBox.Yes | QMessageBox.No)
        
        if res != QMessageBox.Yes: return

        self.start_file_operation('delete', targets, use_trash=use_trash)

    def perform_undo(self):
        self.start_file_operation('undo')

    def perform_redo(self):
        self.start_file_operation('redo')

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
        self.lbl_results_meta.setText(
            strings.tr("msg_results_summary").format(
                groups=groups, files=files, selected=selected_count
            )
        )
        if hasattr(self, "lbl_results_page_summary"):
            self.lbl_results_page_summary.setText(
                strings.tr("msg_results_summary").format(
                    groups=groups, files=files, selected=selected_count
                )
            )

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

        if hasattr(self, "lbl_action_meta"):
            parts = [strings.tr("msg_selected_count").format(count=selected_count)]
            if hasattr(self, "txt_result_filter") and self.txt_result_filter.text().strip():
                parts.append(strings.tr("msg_filter_active"))
            self.lbl_action_meta.setText("  |  ".join(parts) if parts else "")

    def show_context_menu(self, position):
        item = self.tree_widget.itemAt(position)
        if not item: return
        
        path = item.data(0, Qt.UserRole)
        # Check if it's a valid file path
        if not path or not os.path.exists(path): return

        menu = QMenu()
        
        # Style the menu with icons
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
    
    def _on_page_changed(self, page_name: str):
        """Handle sidebar navigation - switch pages and show toast"""
        try:
            # Page index mapping
            page_indices = {
                "scan": 0,
                # "results" is a focused view of the Scan page (same results tree/preview).
                "results": 0,
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

                # Toggle scan page layout mode
                if page_name == "scan":
                    self._set_scan_page_mode("scan")
                elif page_name == "results":
                    self._set_scan_page_mode("results")
                
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


