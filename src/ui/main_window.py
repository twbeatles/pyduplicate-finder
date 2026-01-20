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

        # Drag & Drop 활성화
        self.setAcceptDrops(True)

    def closeEvent(self, event):
        self.save_settings()
        self.history_manager.cleanup()
        event.accept()

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
        
        folder_label = QLabel("📁 " + strings.tr("grp_search_loc"))
        folder_label.setObjectName("card_title")
        folder_header.addWidget(folder_label)
        
        self.btn_add_folder = QPushButton("📂 " + strings.tr("btn_add_folder"))
        self.btn_add_folder.setMinimumHeight(32)
        self.btn_add_folder.setCursor(Qt.PointingHandCursor)
        self.btn_add_folder.clicked.connect(self.add_folder)
        
        self.btn_add_drive = QPushButton("💾 " + strings.tr("btn_add_drive"))
        self.btn_add_drive.setMinimumHeight(32)
        self.btn_add_drive.setCursor(Qt.PointingHandCursor)
        self.btn_add_drive.clicked.connect(self.add_drive_dialog)

        self.btn_remove_folder = QPushButton("➖")
        self.btn_remove_folder.setMinimumHeight(32)
        self.btn_remove_folder.setFixedWidth(36)
        self.btn_remove_folder.setCursor(Qt.PointingHandCursor)
        self.btn_remove_folder.setToolTip(strings.tr("btn_clear"))
        self.btn_remove_folder.clicked.connect(self.remove_selected_folder)

        self.btn_clear_folder = QPushButton("🗑️ " + strings.tr("btn_clear"))
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
        self.btn_filter_toggle = QPushButton("⚙️ " + strings.tr("lbl_filter_options") + " ▼")
        self.btn_filter_toggle.setObjectName("filter_header")
        self.btn_filter_toggle.setCheckable(True)
        self.btn_filter_toggle.setChecked(True)
        self.btn_filter_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_filter_toggle.clicked.connect(self._toggle_filter_panel)
        top_main_layout.addWidget(self.btn_filter_toggle)
        
        # Filter Content Container
        self.filter_container = QWidget()
        self.filter_container.setObjectName("filter_content")
        filter_main_layout = QVBoxLayout(self.filter_container)
        filter_main_layout.setSpacing(12)
        filter_main_layout.setContentsMargins(12, 12, 12, 12)
        
        # --- Filter Row 1: Basic Filters ---
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(20)
        
        # Extension Filter
        ext_layout = QHBoxLayout()
        ext_layout.setSpacing(8)
        self.lbl_ext = QLabel("📄 " + strings.tr("lbl_ext"))
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
        self.lbl_min_size = QLabel("📏 " + strings.tr("lbl_min_size"))
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
        
        row1_layout.addWidget(self._create_separator())
        
        # Basic Checkboxes
        self.chk_same_name = QCheckBox("🏷️ " + strings.tr("chk_same_name"))
        self.chk_name_only = QCheckBox("📝 " + strings.tr("chk_name_only"))
        self.chk_name_only.setToolTip(strings.tr("tip_name_only"))
        
        row1_layout.addWidget(self.chk_same_name)
        row1_layout.addWidget(self.chk_name_only)
        row1_layout.addStretch()
        
        filter_main_layout.addLayout(row1_layout)
        
        # --- Filter Row 2: Advanced Options ---
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(20)
        
        self.chk_byte_compare = QCheckBox("🔍 " + strings.tr("chk_byte_compare"))
        self.chk_protect_system = QCheckBox("🛡️ " + strings.tr("chk_protect_system"))
        self.chk_protect_system.setChecked(True)
        self.chk_use_trash = QCheckBox("♻️ " + strings.tr("chk_use_trash"))
        self.chk_use_trash.setToolTip(strings.tr("tip_use_trash"))
        
        row2_layout.addWidget(self.chk_byte_compare)
        row2_layout.addWidget(self.chk_protect_system)
        row2_layout.addWidget(self.chk_use_trash)
        
        row2_layout.addWidget(self._create_separator())
        
        # Similar Image Section
        self.chk_similar_image = QCheckBox("🖼️ " + strings.tr("chk_similar_image"))
        self.chk_similar_image.setToolTip(strings.tr("tip_similar_image"))
        row2_layout.addWidget(self.chk_similar_image)
        
        self.lbl_similarity = QLabel(strings.tr("lbl_similarity_threshold"))
        self.spin_similarity = QDoubleSpinBox()
        self.spin_similarity.setRange(0.1, 1.0)
        self.spin_similarity.setSingleStep(0.05)
        self.spin_similarity.setValue(0.9)
        self.spin_similarity.setDecimals(2)
        self.spin_similarity.setMinimumWidth(80)
        self.spin_similarity.setEnabled(False)
        self.chk_similar_image.toggled.connect(self.spin_similarity.setEnabled)
        
        row2_layout.addWidget(self.lbl_similarity)
        row2_layout.addWidget(self.spin_similarity)
        
        row2_layout.addWidget(self._create_separator())
        
        # Exclude Patterns Button
        self.btn_exclude_patterns = QPushButton("🚫 " + strings.tr("btn_exclude_patterns"))
        self.btn_exclude_patterns.setMinimumHeight(32)
        self.btn_exclude_patterns.setObjectName("btn_icon")
        self.btn_exclude_patterns.setCursor(Qt.PointingHandCursor)
        self.btn_exclude_patterns.clicked.connect(self.open_exclude_patterns_dialog)
        row2_layout.addWidget(self.btn_exclude_patterns)
        
        row2_layout.addStretch()
        
        filter_main_layout.addLayout(row2_layout)
        
        top_main_layout.addWidget(self.filter_container)

        # --- ROW 4: Action Buttons ---
        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)
        
        self.btn_start_scan = QPushButton("▶️ " + strings.tr("btn_start_scan"))
        self.btn_start_scan.setMinimumHeight(40)
        self.btn_start_scan.setMinimumWidth(150)
        self.btn_start_scan.setCursor(Qt.PointingHandCursor)
        self.btn_start_scan.setObjectName("btn_primary")
        self.btn_start_scan.clicked.connect(self.start_scan)

        self.btn_stop_scan = QPushButton("⏹️ " + strings.tr("scan_stop"))
        self.btn_stop_scan.setMinimumHeight(40)
        self.btn_stop_scan.setCursor(Qt.PointingHandCursor)
        self.btn_stop_scan.clicked.connect(self.stop_scan)
        self.btn_stop_scan.setEnabled(False)

        action_layout.addWidget(self.btn_start_scan)
        action_layout.addWidget(self.btn_stop_scan)
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
        tree_layout = QVBoxLayout(self.tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(4)
        
        # Filter Input
        self.txt_result_filter = QLineEdit()
        self.txt_result_filter.setPlaceholderText("🔍 " + strings.tr("ph_filter_results"))
        self.txt_result_filter.textChanged.connect(self.filter_results_tree)
        tree_layout.addWidget(self.txt_result_filter)
        
        self.tree_widget = ResultsTreeWidget()
        self.tree_widget.itemDoubleClicked.connect(self.open_file) 
        self.tree_widget.currentItemChanged.connect(self.update_preview)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        tree_layout.addWidget(self.tree_widget)
        
        self.splitter.addWidget(self.tree_container)

        # [Right] Preview Panel
        self.preview_container = QWidget()
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        
        self.lbl_preview_header = QLabel("🔍 " + strings.tr("lbl_preview"))
        self.lbl_preview_header.setAlignment(Qt.AlignCenter)
        self.lbl_preview_header.setStyleSheet("""
            font-weight: 600; 
            font-size: 14px;
            padding: 12px; 
            border-bottom: 1px solid palette(mid);
        """) 
        preview_layout.addWidget(self.lbl_preview_header)

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

        # === 4. 하단 선택 및 삭제 (Fixed at bottom) ===
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(12)
        bottom_layout.setContentsMargins(0, 8, 0, 0)
        
        self.btn_select_smart = QToolButton()
        self.btn_select_smart.setText("⚡ " + strings.tr("btn_smart_select"))
        self.btn_select_smart.setToolTip(strings.tr("tip_smart_select"))
        self.btn_select_smart.setMinimumHeight(44)
        self.btn_select_smart.setObjectName("btn_secondary")
        self.btn_select_smart.setCursor(Qt.PointingHandCursor)
        self.btn_select_smart.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_select_smart.clicked.connect(self.select_duplicates_smart)
        
        # Smart Select Menu
        self.menu_smart_select = QMenu(self)
        
        # 1. Smart Select (Default)
        self.action_smart = QAction("⚡ " + strings.tr("btn_smart_select"), self)
        self.action_smart.triggered.connect(self.select_duplicates_smart)
        self.menu_smart_select.addAction(self.action_smart)
        
        self.menu_smart_select.addSeparator()
        
        # 2. Select Newest (Keep Oldest)
        self.action_newest = QAction("🆕 " + strings.tr("action_select_newest"), self)
        self.action_newest.setToolTip(strings.tr("tip_select_newest"))
        self.action_newest.triggered.connect(self.select_duplicates_newest)
        self.menu_smart_select.addAction(self.action_newest)
        
        # 3. Select Oldest (Keep Newest)
        self.action_oldest = QAction("💾 " + strings.tr("action_select_oldest"), self)
        self.action_oldest.setToolTip(strings.tr("tip_select_oldest"))
        self.action_oldest.triggered.connect(self.select_duplicates_oldest)
        self.menu_smart_select.addAction(self.action_oldest)
        
        self.menu_smart_select.addSeparator()
        
        # 4. Select by Path Pattern
        self.action_pattern = QAction("📝 " + strings.tr("action_select_pattern"), self)
        self.action_pattern.triggered.connect(self.select_duplicates_by_pattern)
        self.menu_smart_select.addAction(self.action_pattern)

        self.btn_select_smart.setMenu(self.menu_smart_select)
        
        self.btn_export = QPushButton("📄 " + strings.tr("btn_export"))
        self.btn_export.setMinimumHeight(44)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self.export_results)

        self.btn_delete = QPushButton("🗑️ " + strings.tr("btn_delete_selected"))
        self.btn_delete.setObjectName("btn_danger")
        self.btn_delete.setMinimumHeight(44)
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.clicked.connect(self.delete_selected_files)

        bottom_layout.addWidget(self.btn_select_smart)
        bottom_layout.addWidget(self.btn_export)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_delete)
        main_layout.addLayout(bottom_layout)

        # === PAGE 1: RESULTS PAGE (Placeholder for now - can be used for dedicated results view) ===
        self.results_page = QWidget()
        results_layout = QVBoxLayout(self.results_page)
        results_layout.setContentsMargins(16, 12, 16, 12)
        results_lbl = QLabel("📊 " + strings.tr("nav_results"))
        results_lbl.setObjectName("card_title")
        results_lbl.setStyleSheet("font-size: 18px; padding: 20px;")
        results_layout.addWidget(results_lbl)
        results_info = QLabel(strings.tr("msg_select_file"))
        results_info.setStyleSheet("color: palette(mid); padding: 20px;")
        results_layout.addWidget(results_info)
        results_layout.addStretch()
        self.page_stack.addWidget(self.results_page)
        
        # === PAGE 2: TOOLS PAGE ===
        self.tools_page = QWidget()
        tools_layout = QVBoxLayout(self.tools_page)
        tools_layout.setSpacing(16)
        tools_layout.setContentsMargins(16, 12, 16, 12)
        
        tools_title = QLabel("🛠️ " + strings.tr("nav_tools"))
        tools_title.setObjectName("card_title")
        tools_title.setStyleSheet("font-size: 18px; padding: 8px 0;")
        tools_layout.addWidget(tools_title)
        
        # Empty Folder Finder Card
        empty_card = QWidget()
        empty_card.setObjectName("folder_card")
        empty_card_layout = QVBoxLayout(empty_card)
        empty_card_layout.setContentsMargins(20, 16, 20, 16)
        empty_card_layout.setSpacing(12)
        
        empty_title = QLabel("📁 " + strings.tr("action_empty_finder"))
        empty_title.setObjectName("card_title")
        empty_card_layout.addWidget(empty_title)
        
        btn_empty_tools = QPushButton("🔍 " + strings.tr("btn_scan_empty"))
        btn_empty_tools.setMinimumHeight(44)
        btn_empty_tools.setCursor(Qt.PointingHandCursor)
        btn_empty_tools.clicked.connect(self.open_empty_finder)
        empty_card_layout.addWidget(btn_empty_tools)
        
        tools_layout.addWidget(empty_card)
        tools_layout.addStretch()
        self.page_stack.addWidget(self.tools_page)
        
        # === PAGE 3: SETTINGS PAGE ===
        self.settings_page = QWidget()
        settings_layout = QVBoxLayout(self.settings_page)
        settings_layout.setSpacing(16)
        settings_layout.setContentsMargins(16, 12, 16, 12)
        
        settings_title = QLabel("⚙️ " + strings.tr("nav_settings"))
        settings_title.setObjectName("card_title")
        settings_title.setStyleSheet("font-size: 18px; padding: 8px 0;")
        settings_layout.addWidget(settings_title)
        
        # Theme Card
        theme_card = QWidget()
        theme_card.setObjectName("folder_card")
        theme_card_layout = QVBoxLayout(theme_card)
        theme_card_layout.setContentsMargins(20, 16, 20, 16)
        theme_card_layout.setSpacing(12)
        
        theme_title = QLabel("🌙 " + strings.tr("action_theme"))
        theme_title.setObjectName("card_title")
        theme_card_layout.addWidget(theme_title)
        
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
        
        shortcut_title = QLabel("⌨️ " + strings.tr("action_shortcut_settings"))
        shortcut_title.setObjectName("card_title")
        shortcut_card_layout.addWidget(shortcut_title)
        
        btn_shortcuts_settings = QPushButton(strings.tr("action_shortcut_settings"))
        btn_shortcuts_settings.setMinimumHeight(44)
        btn_shortcuts_settings.setCursor(Qt.PointingHandCursor)
        btn_shortcuts_settings.clicked.connect(self.open_shortcut_settings)
        shortcut_card_layout.addWidget(btn_shortcuts_settings)
        
        settings_layout.addWidget(shortcut_card)
        
        # Presets Card
        preset_card = QWidget()
        preset_card.setObjectName("folder_card")
        preset_card_layout = QVBoxLayout(preset_card)
        preset_card_layout.setContentsMargins(20, 16, 20, 16)
        preset_card_layout.setSpacing(12)
        
        preset_title = QLabel("📋 " + strings.tr("action_preset"))
        preset_title.setObjectName("card_title")
        preset_card_layout.addWidget(preset_title)
        
        btn_preset_settings = QPushButton(strings.tr("btn_manage_presets"))
        btn_preset_settings.setMinimumHeight(44)
        btn_preset_settings.setCursor(Qt.PointingHandCursor)
        btn_preset_settings.clicked.connect(self.open_preset_dialog)
        preset_card_layout.addWidget(btn_preset_settings)
        
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

    def retranslate_ui(self):
        """Dynamic text update for language switching"""
        self.setWindowTitle(strings.tr("app_title"))
        
        self.btn_add_folder.setText("📂 " + strings.tr("btn_add_folder"))
        self.btn_add_drive.setText("💾 " + strings.tr("btn_add_drive"))
        self.btn_clear_folder.setText("🗑️ " + strings.tr("btn_clear"))
        self.btn_remove_folder.setToolTip(strings.tr("btn_clear"))
        
        # Labels
        if hasattr(self, 'lbl_ext'):
            self.lbl_ext.setText("📄 " + strings.tr("lbl_ext"))
        if hasattr(self, 'lbl_min_size'):
            self.lbl_min_size.setText("📏 " + strings.tr("lbl_min_size"))
        
        self.txt_extensions.setPlaceholderText(strings.tr("ph_ext"))
        self.spin_min_size.setSuffix(" KB")
        self.chk_same_name.setText("🏷️ " + strings.tr("chk_same_name"))
        self.chk_byte_compare.setText("🔍 " + strings.tr("chk_byte_compare"))
        self.chk_protect_system.setText("🛡️ " + strings.tr("chk_protect_system"))
        
        self.btn_start_scan.setText("▶️ " + strings.tr("btn_start_scan"))
        self.btn_stop_scan.setText("⏹️ " + strings.tr("scan_stop"))
        
        # New Feature: Filter Placeholder
        if hasattr(self, 'txt_result_filter'):
            self.txt_result_filter.setPlaceholderText("🔍 " + strings.tr("ph_filter_results"))

        self.tree_widget.setHeaderLabels([strings.tr("col_path"), strings.tr("col_size"), strings.tr("col_mtime"), strings.tr("col_ext")])
        self.lbl_preview_header.setText("🔍 " + strings.tr("lbl_preview"))
        
        if not self.lbl_image_preview.isVisible() and not self.txt_text_preview.isVisible():
            self.lbl_info_preview.setText(strings.tr("msg_select_file"))

        self.btn_select_smart.setText("⚡ " + strings.tr("btn_smart_select"))
        self.btn_select_smart.setToolTip(strings.tr("tip_smart_select"))
        
        # New Feature: Menu Actions
        if hasattr(self, 'action_smart'):
            self.action_smart.setText("⚡ " + strings.tr("btn_smart_select"))
        if hasattr(self, 'action_newest'):
            self.action_newest.setText("🆕 " + strings.tr("action_select_newest"))
            self.action_newest.setToolTip(strings.tr("tip_select_newest"))
        if hasattr(self, 'action_oldest'):
            self.action_oldest.setText("💾 " + strings.tr("action_select_oldest"))
            self.action_oldest.setToolTip(strings.tr("tip_select_oldest"))
        if hasattr(self, 'action_pattern'):
            self.action_pattern.setText("📝 " + strings.tr("action_select_pattern"))

        self.btn_export.setText("📄 " + strings.tr("btn_export"))
        self.btn_delete.setText("🗑️ " + strings.tr("btn_delete_selected"))
        
        if self.status_label.text() in ["Ready", "준비됨"]:
             self.status_label.setText(strings.tr("status_ready"))
             
        # Toolbar Actions
        if hasattr(self, 'action_undo'):
            self.action_undo.setText("↩️ " + strings.tr("action_undo"))
        if hasattr(self, 'action_redo'):
            self.action_redo.setText("↪️ " + strings.tr("action_redo"))
        if hasattr(self, 'action_empty_finder'):
            self.action_empty_finder.setText("📁 " + strings.tr("action_empty_finder"))
        if hasattr(self, 'action_theme'):
            self.action_theme.setText("🌙 " + strings.tr("action_theme"))
        if hasattr(self, 'menu_lang'):
            self.menu_lang.setTitle("🌐 " + strings.tr("menu_lang"))

    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Language Menu
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        # Actions
        self.action_undo = QAction("↩️ " + strings.tr("action_undo"), self)
        self.action_undo.setShortcut(QKeySequence.Undo)
        self.action_undo.triggered.connect(self.perform_undo)
        self.action_undo.setEnabled(False)
        toolbar.addAction(self.action_undo)

        self.action_redo = QAction("↪️ " + strings.tr("action_redo"), self)
        self.action_redo.setShortcut(QKeySequence.Redo)
        self.action_redo.triggered.connect(self.perform_redo)
        self.action_redo.setEnabled(False)
        toolbar.addAction(self.action_redo)

        toolbar.addSeparator()
        
        # Expand/Collapse Actions
        self.action_expand_all = QAction("➕ " + strings.tr("action_expand_all"), self)
        self.action_expand_all.setToolTip(strings.tr("action_expand_all"))
        self.action_expand_all.triggered.connect(self.tree_widget.expandAll)
        toolbar.addAction(self.action_expand_all)
        
        self.action_collapse_all = QAction("➖ " + strings.tr("action_collapse_all"), self)
        self.action_collapse_all.setToolTip(strings.tr("action_collapse_all"))
        self.action_collapse_all.triggered.connect(self.tree_widget.collapseAll)
        toolbar.addAction(self.action_collapse_all)
        
        toolbar.addSeparator()
        
        # 결과 저장/불러오기
        self.action_save_results = QAction("💾 " + strings.tr("action_save_results"), self)
        self.action_save_results.setShortcut(QKeySequence.Save)
        self.action_save_results.triggered.connect(self.save_scan_results)
        toolbar.addAction(self.action_save_results)
        
        self.action_load_results = QAction("📂 " + strings.tr("action_load_results"), self)
        self.action_load_results.setShortcut(QKeySequence.Open)
        self.action_load_results.triggered.connect(self.load_scan_results)
        toolbar.addAction(self.action_load_results)
        
        toolbar.addSeparator()

        self.action_empty_finder = QAction("📁 " + strings.tr("action_empty_finder"), self)
        self.action_empty_finder.triggered.connect(self.open_empty_finder)
        toolbar.addAction(self.action_empty_finder)

        self.action_theme = QAction("🌙 " + strings.tr("action_theme"), self)
        self.action_theme.setCheckable(True)
        self.action_theme.triggered.connect(self.toggle_theme)
        toolbar.addAction(self.action_theme)
        
        toolbar.addSeparator()
        
        # 프리셋 메뉴
        btn_preset = QToolButton(self)
        btn_preset.setText("📋 " + strings.tr("action_preset"))
        btn_preset.setPopupMode(QToolButton.InstantPopup)
        
        self.menu_preset = QMenu(self)
        action_save_preset = QAction(strings.tr("btn_save_preset"), self)
        action_save_preset.triggered.connect(self.open_preset_dialog)
        self.menu_preset.addAction(action_save_preset)
        
        action_manage_presets = QAction(strings.tr("btn_manage_presets"), self)
        action_manage_presets.triggered.connect(self.open_preset_dialog)
        self.menu_preset.addAction(action_manage_presets)
        
        btn_preset.setMenu(self.menu_preset)
        toolbar.addWidget(btn_preset)
        
        # 단축키 설정
        self.action_shortcut_settings = QAction("⌨️ " + strings.tr("action_shortcut_settings"), self)
        self.action_shortcut_settings.triggered.connect(self.open_shortcut_settings)
        toolbar.addAction(self.action_shortcut_settings)
        
        toolbar.addSeparator()
        
        # Language Button with Menu
        btn_lang = QToolButton(self)
        btn_lang.setText("Language")
        btn_lang.setPopupMode(QToolButton.InstantPopup)
        
        self.menu_lang = QMenu(self)
        
        action_ko = QAction(strings.tr("lang_ko"), self)
        action_ko.triggered.connect(lambda: self.change_language("ko"))
        self.menu_lang.addAction(action_ko)
        
        action_en = QAction(strings.tr("lang_en"), self)
        action_en.triggered.connect(lambda: self.change_language("en"))
        self.menu_lang.addAction(action_en)
        
        btn_lang.setMenu(self.menu_lang)
        toolbar.addWidget(btn_lang)

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
        
        QWidget#filter_content {{
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

    def toggle_theme(self, checked):
        self.apply_theme("dark" if checked else "light")
    
    def _toggle_filter_panel(self, checked):
        """Toggle visibility of the filter panel with animation"""
        self.filter_container.setVisible(checked)
        arrow = "▼" if checked else "▶"
        self.btn_filter_toggle.setText("⚙️ " + strings.tr("lbl_filter_options") + " " + arrow)

    # --- 기능 구현: 드라이브 및 폴더 ---

    def add_path_to_list(self, path):
        path = os.path.normpath(path)
        if path not in self.selected_folders:
            self.selected_folders.append(path)
            self.list_folders.addItem(path)

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

    def remove_selected_folder(self):
        """Remove the currently selected folder from the list"""
        current_row = self.list_folders.currentRow()
        if current_row >= 0:
            self.list_folders.takeItem(current_row)
            if current_row < len(self.selected_folders):
                del self.selected_folders[current_row]

    # --- 기능 구현: 스캔 ---
    # --- 기능 구현: 스캔 ---
    def start_scan(self):
        if not self.selected_folders:
            QMessageBox.warning(self, strings.tr("app_title"), strings.tr("err_no_folder"))
            return

        raw_ext = self.txt_extensions.text()
        extensions = [x.strip() for x in raw_ext.split(',')] if raw_ext.strip() else None
        min_size = self.spin_min_size.value()

        self.tree_widget.clear()
        self.toggle_ui_state(scanning=True)
        
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
            similarity_threshold=self.spin_similarity.value()
        )
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.scan_finished.connect(self.on_scan_finished)
        self.worker.start()

    def stop_scan(self):
        if hasattr(self, 'worker'):
            self.worker.stop()
            self.status_label.setText(strings.tr("status_stopped"))

    def toggle_ui_state(self, scanning):
        self.btn_start_scan.setEnabled(not scanning)
        self.btn_stop_scan.setEnabled(scanning)
        self.btn_delete.setEnabled(not scanning)
        self.btn_select_smart.setEnabled(not scanning)
        self.btn_export.setEnabled(not scanning)
        # Issue #22: Disable folder buttons during scan
        self.btn_add_folder.setEnabled(not scanning)
        self.btn_add_drive.setEnabled(not scanning)
        self.btn_clear_folders.setEnabled(not scanning)

    @Slot(int, str)
    def update_progress(self, val, msg):
        self.progress_bar.setValue(val)
        self.status_label.setText(msg)

    @Slot(dict)
    def on_scan_finished(self, results):
        self.scan_results = results
        self.toggle_ui_state(scanning=False)
        self.progress_bar.setValue(100)
        self.status_label.setText(strings.tr("msg_scan_complete").format(len(results)))
        self.tree_widget.populate(results)

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
            QMessageBox.warning(self, strings.tr("app_title"), strings.tr("msg_no_files_selected"))
            return

        path, _ = QFileDialog.getSaveFileName(self, strings.tr("btn_export"), "duplicates.csv", "CSV Files (*.csv)")
        if not path: return

        try:
            import csv
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["Group ID", "Size (Bytes)", "File Path", "Modified Time"])
                
                group_id = 1
                for key, paths in self.scan_results.items():
                    size = key[1]
                    hash_val = key[0] # Note: key might contain extra info
                    
                    for p in paths:
                        mtime_str = ""
                        try:
                            mtime = os.path.getmtime(p)
                            mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                        except: pass
                        
                        writer.writerow([group_id, size, p, mtime_str])
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
                path = item.data(0, Qt.UserRole).lower()
                
                if pattern in path:
                    item.setCheckState(0, Qt.Checked)
                    count += 1
        
        self.status_label.setText(f"Selected {count} files matching '{text}'")

    def filter_results_tree(self, text):
        """Filter the result tree by filename/path"""
        text = text.lower()
        root = self.tree_widget.invisibleRootItem()
        
        for i in range(root.childCount()):
            group = root.child(i)
            group_visible = False
            
            for j in range(group.childCount()):
                item = group.child(j)
                path = item.data(0, Qt.UserRole).lower()
                
                # Simple containment check
                if not text or text in path:
                    item.setHidden(False)
                    group_visible = True
                else:
                    item.setHidden(True)
            
            # Hide group if no children visible
            group.setHidden(not group_visible)

    def delete_selected_files(self):
        targets = []
        # Store items to remove from UI *after* operation success
        # But for async, we need a way to link targets back to UI items.
        # Simplest: Reload the tree or just delete UI items if success.
        # Better: Store targets and wait for signal.
        
        self.pending_delete_items = [] # temporary storage

        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            for j in range(group.childCount()):
                item = group.child(j)
                # Issue #15: Skip hidden (filtered) items
                if item.isHidden():
                    continue
                if item.checkState(0) == Qt.Checked:
                    targets.append(item.data(0, Qt.UserRole))
                    self.pending_delete_items.append(item)

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
        
        if use_trash:
            res = QMessageBox.question(self, strings.tr("confirm_delete_title"), 
                                       strings.tr("confirm_trash_delete").format(len(targets)),
                                       QMessageBox.Yes | QMessageBox.No)
        else:
            res = QMessageBox.question(self, strings.tr("confirm_delete_title"), 
                                       strings.tr("confirm_delete_msg").format(len(targets)),
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
        self.file_op_dialog = QProgressDialog(strings.tr("status_analyzing"), None, 0, 0, self)
        self.file_op_dialog.setWindowTitle(strings.tr("app_title"))
        self.file_op_dialog.setWindowModality(Qt.WindowModal)
        self.file_op_dialog.setMinimumDuration(0)
        self.file_op_dialog.setCancelButton(None) # Not cancellable for safety
        self.file_op_dialog.show()

        self.file_worker = FileOperationWorker(self.history_manager, op_type, data, use_trash=use_trash)
        self.file_worker.progress_updated.connect(lambda val, msg: self.file_op_dialog.setLabelText(msg))
        self.file_worker.operation_finished.connect(lambda s, m: self.on_file_op_finished(op_type, s, m))
        self.file_worker.start()

    def on_file_op_finished(self, op_type, success, message):
        self.file_op_dialog.close()
        self.toggle_ui_state(scanning=False)
        self.status_label.setText(message)
        
        if success:
            if op_type == 'delete':
                if hasattr(self, 'pending_delete_items'):
                    # Issue #13: Also update scan_results
                    deleted_paths = set()
                    for item in self.pending_delete_items:
                        path = item.data(0, Qt.UserRole)
                        if path:
                            deleted_paths.add(path)
                        parent = item.parent()
                        if parent: parent.removeChild(item)
                    
                    # Remove deleted files from scan_results
                    self._remove_paths_from_results(deleted_paths)
                    self.pending_delete_items = []
                    
            elif op_type == 'undo':
                # Issue #23: Recommend rescan after undo since restored files may not be in scan_results
                if self.scan_results:
                    self.tree_widget.populate(self.scan_results)
                # Inform user that rescan may be needed for accurate results
                undo_msg = message + "\n\n" + (strings.tr("msg_rescan_recommended") 
                           if strings.tr("msg_rescan_recommended") != "msg_rescan_recommended" 
                           else "Rescan recommended for accurate results.")
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
            self.show_preview_info(f"Folder: {path}")
            return

        _, ext = os.path.splitext(path)
        ext = ext.lower()

        try:
            # 1. 이미지
            if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.ico']:
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(self.lbl_image_preview.size().boundedTo(QSize(400, 400)), 
                                         Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.lbl_image_preview.setPixmap(scaled)
                    self.lbl_image_preview.show()
                    self.txt_text_preview.hide()
                    self.lbl_info_preview.setText(f"{path}\n({pixmap.width()}x{pixmap.height()})")
                    return
            
            # 2. 텍스트 및 코드
            elif ext in ['.txt', '.py', '.c', '.cpp', '.h', '.java', '.md', '.json', '.xml', 
                         '.html', '.css', '.js', '.log', '.bat', '.sh', '.ini', '.yaml', '.yml', '.csv']:
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(4096) # 4KB 읽기
                    
                    # JSON Pretty Print
                    if ext == '.json':
                        try:
                            parsed = json.loads(content)
                            content = json.dumps(parsed, indent=4, ensure_ascii=False)
                        except: pass
                        
                    self.txt_text_preview.setText(content)
                    font = QFont("Consolas")
                    font.setStyleHint(QFont.Monospace)
                    font.setPointSize(10)
                    self.txt_text_preview.setFont(font)
                    self.txt_text_preview.show()
                    self.lbl_image_preview.hide()
                    self.txt_text_preview.show()
                    self.lbl_image_preview.hide()
                    self.lbl_info_preview.setText(f"{path}\n({strings.tr('lbl_preview')})")
                    return
                except:
                    pass

        except Exception as e:
            pass

        # 3. 그 외
        size_str = self.format_size(os.path.getsize(path))
        self.show_preview_info(f"{strings.tr('lbl_preview')}: {os.path.basename(path)}\n{size_str}")

    def show_preview_info(self, msg):
        self.lbl_image_preview.hide()
        self.txt_text_preview.hide()
        self.lbl_info_preview.setText(msg)
        self.lbl_info_preview.show()

    # --- 기능 구현: 설정 저장/로드 ---
    def save_settings(self):
        self.settings.setValue("app/geometry", self.saveGeometry())
        self.settings.setValue("app/splitter", self.splitter.saveState())
        self.settings.setValue("filter/extensions", self.txt_extensions.text())
        self.settings.setValue("filter/min_size", self.spin_min_size.value())
        self.settings.setValue("filter/protect_system", self.chk_protect_system.isChecked())
        self.settings.setValue("filter/byte_compare", self.chk_byte_compare.isChecked())
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
        
        folders = self.settings.value("folders", [])
        # 리스트가 아니라 단일 문자열로 저장되는 경우가 있어 타입 체크
        if isinstance(folders, str): folders = [folders]
        elif not isinstance(folders, list): folders = []
        
        self.selected_folders = [f for f in folders if os.path.exists(f)]
        
        # Populate ListWidget
        self.list_folders.clear()
        for f in self.selected_folders:
            self.list_folders.addItem(f)

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
                    self.btn_exclude_patterns.setText(f"🚫 {strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})")
            except:
                self.exclude_patterns = []

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
            self.status_label.setText(strings.tr("msg_results_loaded").format(len(self.scan_results)))
        except Exception as e:
            QMessageBox.critical(self, strings.tr("app_title"), strings.tr("err_save").format(e))
    
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
                self.btn_exclude_patterns.setText(f"🚫 {strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})")
            else:
                self.btn_exclude_patterns.setText(f"🚫 {strings.tr('btn_exclude_patterns')}")
    
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
                self.btn_exclude_patterns.setText(f"🚫 {strings.tr('btn_exclude_patterns')} ({len(self.exclude_patterns)})")
    
    def _apply_shortcuts(self, shortcuts: dict):
        """커스텀 단축키를 액션에 적용"""
        shortcut_map = {
            'undo': self.action_undo,
            'redo': self.action_redo,
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
                "results": 1,
                "tools": 2,
                "settings": 3,
            }
            
            page_names = {
                "scan": "🔍 " + strings.tr("nav_scan"),
                "results": "📊 " + strings.tr("nav_results"),
                "tools": "🛠️ " + strings.tr("nav_tools"),
                "settings": "⚙️ " + strings.tr("nav_settings"),
            }
            
            if page_name in page_indices:
                # Switch to the selected page
                self.page_stack.setCurrentIndex(page_indices[page_name])
                
                # Update status label
                if page_name in page_names:
                    self.status_label.setText(page_names[page_name])
                
                # Show toast notification
                if hasattr(self, 'toast_manager') and self.toast_manager:
                    self.toast_manager.info(page_names[page_name], duration=2000)
                    
        except Exception as e:
            print(f"Navigation error: {page_name} - {e}")


