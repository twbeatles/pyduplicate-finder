from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel, QProgressBar, QCheckBox, QMessageBox, QGroupBox, QTreeWidget, QTreeWidgetItem, QToolBar, QSpinBox, QLineEdit, QMenu, QSplitter, QTextEdit, QScrollArea, QStyle, QProgressDialog)
from PySide6.QtCore import Qt, Slot, QSize, QSettings
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
from src.ui.empty_folder_dialog import EmptyFolderDialog
from src.utils.i18n import strings

class DuplicateFinderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(strings.tr("app_title"))
        self.resize(1100, 800)
        self.selected_folders = []
        self.scan_results = {}
        self.history_manager = HistoryManager()
        
        self.init_ui()
        self.create_toolbar()
        
        # Settings
        self.settings = QSettings("MySoft", "PyDuplicateFinderPro")
        self.load_settings()

        # Apply initial theme (defaults to light if not set)
        current_theme = self.settings.value("app/theme", "light")
        self.apply_theme(current_theme)

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
            self.status_label.setText(f"{added_count}개 폴더가 추가되었습니다.")
        
        event.accept()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # === 1. 검색 설정 영역 (폴더 + 필터) ===
        settings_layout = QHBoxLayout()

        # [좌측] 폴더 선택 그룹
        folder_group = QGroupBox(strings.tr("grp_search_loc"))
        folder_vbox = QVBoxLayout(folder_group)
        
        btn_folder_box = QHBoxLayout()
        self.btn_add_folder = QPushButton(strings.tr("btn_add_folder"))
        self.btn_add_folder.clicked.connect(self.add_folder)
        
        self.btn_add_drive = QPushButton(strings.tr("btn_add_drive"))
        self.btn_add_drive.clicked.connect(self.add_drive_dialog)

        self.btn_clear_folder = QPushButton(strings.tr("btn_clear"))
        self.btn_clear_folder.clicked.connect(self.clear_folders)

        btn_folder_box.addWidget(self.btn_add_folder)
        btn_folder_box.addWidget(self.btn_add_drive)
        btn_folder_box.addWidget(self.btn_clear_folder)
        
        self.lbl_folders = QLabel(strings.tr("lbl_no_selection"))
        self.lbl_folders.setStyleSheet("color: #666; font-size: 11px;")
        
        folder_vbox.addLayout(btn_folder_box)
        folder_vbox.addWidget(self.lbl_folders)
        
        # [우측] 필터 옵션 그룹
        filter_group = QGroupBox(strings.tr("grp_search_opt"))
        filter_grid = QVBoxLayout(filter_group)
        
        # 확장자 필터
        ext_layout = QHBoxLayout()
        ext_layout.addWidget(QLabel(strings.tr("lbl_ext")))
        self.txt_extensions = QLineEdit()
        self.txt_extensions.setPlaceholderText(strings.tr("ph_ext"))
        ext_layout.addWidget(self.txt_extensions)
        
        # 최소 크기 필터
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel(strings.tr("lbl_min_size")))
        self.spin_min_size = QSpinBox()
        self.spin_min_size.setRange(0, 10000000)
        self.spin_min_size.setValue(0)
        self.spin_min_size.setSuffix(" KB")
        size_layout.addWidget(self.spin_min_size)

        self.chk_same_name = QCheckBox(strings.tr("chk_same_name"))
        self.chk_byte_compare = QCheckBox(strings.tr("chk_byte_compare"))
        self.chk_protect_system = QCheckBox(strings.tr("chk_protect_system"))
        self.chk_protect_system.setChecked(True) # Default On
        
        filter_grid.addLayout(ext_layout)
        filter_grid.addLayout(size_layout)
        filter_grid.addWidget(self.chk_same_name)
        filter_grid.addWidget(self.chk_byte_compare)
        filter_grid.addWidget(self.chk_protect_system)

        settings_layout.addWidget(folder_group, 6)
        settings_layout.addWidget(filter_group, 4)
        main_layout.addLayout(settings_layout)

        # === 2. 실행 버튼 영역 ===
        action_layout = QHBoxLayout()
        self.btn_start_scan = QPushButton(strings.tr("btn_start_scan"))
        self.btn_start_scan.setMinimumHeight(45)
        self.btn_start_scan.setStyleSheet("background-color: #2ecc71; color: white; font-size: 14px; font-weight: bold; border-radius: 5px;")
        self.btn_start_scan.clicked.connect(self.start_scan)

        self.btn_stop_scan = QPushButton(strings.tr("scan_stop"))
        self.btn_stop_scan.setMinimumHeight(45)
        self.btn_stop_scan.clicked.connect(self.stop_scan)
        self.btn_stop_scan.setEnabled(False)

        action_layout.addWidget(self.btn_start_scan)
        action_layout.addWidget(self.btn_stop_scan)
        main_layout.addLayout(action_layout)

        # === 3. 결과 트리 뷰 + 미리보기 (Splitter) ===
        self.splitter = QSplitter(Qt.Horizontal)
        
        # [Left] Tree Widget
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels([strings.tr("col_path"), strings.tr("col_size"), strings.tr("col_mtime"), strings.tr("col_ext")])
        self.tree_widget.setColumnWidth(0, 400)
        self.tree_widget.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_widget.itemDoubleClicked.connect(self.open_file) # 더블 클릭 시 열기
        self.tree_widget.currentItemChanged.connect(self.update_preview)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.splitter.addWidget(self.tree_widget)

        # [Right] Preview Panel
        self.preview_container = QWidget()
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_preview_header = QLabel(strings.tr("lbl_preview"))
        self.lbl_preview_header.setStyleSheet("font-weight: bold; background-color: #ecf0f1; padding: 5px;")
        preview_layout.addWidget(self.lbl_preview_header)

        # Scroll Area for flexibility
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
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
        scroll_layout.addWidget(self.lbl_info_preview)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        preview_layout.addWidget(scroll)

        self.splitter.addWidget(self.preview_container)
        self.splitter.setSizes([700, 400])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, True)

        main_layout.addWidget(self.splitter)

        # === 4. 하단 선택 및 삭제 ===
        bottom_layout = QHBoxLayout()
        self.btn_select_smart = QPushButton(strings.tr("btn_smart_select"))
        self.btn_select_smart.setToolTip(strings.tr("tip_smart_select"))
        self.btn_select_smart.clicked.connect(self.select_duplicates_smart)
        
        self.btn_export = QPushButton(strings.tr("btn_export"))
        self.btn_export.clicked.connect(self.export_results)

        self.btn_delete = QPushButton(strings.tr("btn_delete_selected"))
        self.btn_delete.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 5px 15px;")
        self.btn_delete.clicked.connect(self.delete_selected_files)

        bottom_layout.addWidget(self.btn_select_smart)
        bottom_layout.addWidget(self.btn_export)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_delete)
        main_layout.addLayout(bottom_layout)

        # === 5. 상태 표시줄 ===
        self.progress_bar = QProgressBar()
        self.status_label = QLabel(strings.tr("status_ready"))
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.status_label)

    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        # 아이콘이 없을 경우 텍스트로 대체될 수 있습니다 (시스템 테마 의존)
        self.action_undo = QAction("실행 취소 (Undo)", self)
        self.action_undo.setShortcut(QKeySequence.Undo)
        self.action_undo.triggered.connect(self.perform_undo)
        self.action_undo.setEnabled(False)
        toolbar.addAction(self.action_undo)

        self.action_redo = QAction("다시 실행 (Redo)", self)
        self.action_redo.setShortcut(QKeySequence.Redo)
        self.action_redo.triggered.connect(self.perform_redo)
        self.action_redo.setEnabled(False)
        toolbar.addAction(self.action_redo)

        toolbar.addSeparator()

        self.action_empty_finder = QAction("빈 폴더 찾기", self)
        self.action_empty_finder.triggered.connect(self.open_empty_finder)
        toolbar.addAction(self.action_empty_finder)

        self.action_theme = QAction("다크 모드", self)
        self.action_theme.setCheckable(True)
        self.action_theme.triggered.connect(self.toggle_theme)
        toolbar.addAction(self.action_theme)

    def open_empty_finder(self):
        if not self.selected_folders:
            QMessageBox.warning(self, "알림", "먼저 검색할 위치를 추가해주세요.")
            return
        
        dlg = EmptyFolderDialog(self.selected_folders, self)
        dlg.exec()

    def apply_theme(self, theme_name):
        light_theme = {
            "bg": "#f8f9fa", "fg": "#2c3e50", 
            "panel": "#ffffff", "border": "#dcdde1",
            "btn_bg": "#ecf0f1", "btn_fg": "#2c3e50", "btn_hover": "#bdc3c7",
            "header": "#ecf0f1", "highlight": "#d6eaf8"
        }
        
        dark_theme = {
            "bg": "#2b2b2b", "fg": "#ecf0f1", 
            "panel": "#3c3f41", "border": "#555555",
            "btn_bg": "#3c3f41", "btn_fg": "#ecf0f1", "btn_hover": "#4b4e50",
            "header": "#333333", "highlight": "#0d293e"
        }
        
        theme = dark_theme if theme_name == "dark" else light_theme
        
        style = f"""
            QMainWindow, QWidget {{ background-color: {theme['bg']}; color: {theme['fg']}; }}
            QGroupBox {{ 
                font-weight: bold; border: 1px solid {theme['border']}; 
                border-radius: 6px; margin-top: 10px; background-color: {theme['panel']}; 
                color: {theme['fg']};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
            QTreeWidget {{ border: 1px solid {theme['border']}; background-color: {theme['panel']}; color: {theme['fg']}; alternate-background-color: {theme['bg']}; }}
            QTreeWidget::item:selected {{ background-color: {theme['highlight']}; color: {theme['fg']}; }}
            QHeaderView::section {{ background-color: {theme['header']}; color: {theme['fg']}; border: 1px solid {theme['border']}; padding: 4px; }}
            
            QPushButton {{ 
                border-radius: 6px; border: 1px solid {theme['border']}; 
                padding: 6px 12px; background-color: {theme['btn_bg']}; color: {theme['btn_fg']}; 
            }}
            QPushButton:hover {{ background-color: {theme['btn_hover']}; }}
            QPushButton:disabled {{ background-color: {theme['bg']}; color: #7f8c8d; border: 1px dashed {theme['border']}; }}
            
            QLineEdit, QSpinBox, QTextEdit {{ 
                padding: 5px; border-radius: 4px; 
                background-color: {theme['panel']}; color: {theme['fg']}; border: 1px solid {theme['border']}; 
            }}
            
            QProgressBar {{ border: 1px solid {theme['border']}; border-radius: 4px; text-align: center; background-color: {theme['panel']}; }}
            QProgressBar::chunk {{ background-color: #3498db; width: 10px; margin: 0.5px; }}
            
            QSplitter::handle {{ background-color: {theme['border']}; }}
            QScrollBar:vertical {{ background: {theme['bg']}; width: 12px; }}
            QScrollBar::handle:vertical {{ background: {theme['border']}; min-height: 20px; border-radius: 2px; }}
            
            QLabel {{ color: {theme['fg']}; }}
            QCheckBox {{ color: {theme['fg']}; spacing: 5px; }}
        """
        self.setStyleSheet(style)
        self.settings.setValue("app/theme", theme_name)
        
        # Action state update
        if hasattr(self, 'action_theme'):
             self.action_theme.setChecked(theme_name == "dark")

    def toggle_theme(self, checked):
        self.apply_theme("dark" if checked else "light")

    # --- 기능 구현: 드라이브 및 폴더 ---
    def get_available_drives(self):
        drives = []
        if platform.system() == "Windows":
            try:
                bitmask = ctypes.windll.kernel32.GetLogicalDrives()
                for letter in string.ascii_uppercase:
                    if bitmask & 1:
                        path = f"{letter}:\\"
                        if os.path.exists(path):
                            drives.append(path)
                    bitmask >>= 1
            except:
                pass
        else:
            # Unix/Mac
            if os.path.exists("/Volumes"):
                for d in os.listdir("/Volumes"):
                    drives.append(os.path.join("/Volumes", d))
            drives.append("/")
        return drives

    def add_drive_dialog(self):
        drives = self.get_available_drives()
        menu = QMenu(self)
        for drive in drives:
            action = menu.addAction(f"{drive}")
            action.triggered.connect(lambda checked, d=drive: self.add_path_to_list(d))
        menu.exec_(self.btn_add_drive.mapToGlobal(self.btn_add_drive.rect().bottomLeft()))

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, strings.tr("file_open_dialog"))
        if folder:
             self.add_path_to_list(folder)

    def add_path_to_list(self, path):
        if path not in self.selected_folders:
            self.selected_folders.append(path)
            self.update_folder_label()

    def clear_folders(self):
        self.selected_folders = []
        self.update_folder_label()

    def update_folder_label(self):
        if not self.selected_folders:
            self.lbl_folders.setText(strings.tr("lbl_no_selection"))
        else:
            txt = ", ".join(self.selected_folders)
            if len(txt) > 80: txt = txt[:80] + "..."
            self.lbl_folders.setText(f"{strings.tr('lbl_search_target').format(len(self.selected_folders))}: {txt}")

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
            byte_compare=self.chk_byte_compare.isChecked()
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
        self.populate_tree(results)

    def populate_tree(self, results):
        self.tree_widget.clear()
        for key, paths in results.items():
            size = key[1]
            size_str = self.format_size(size)
            
            group_item = QTreeWidgetItem(self.tree_widget)
            group_item.setText(0, f"📂 중복 그룹 ({len(paths)}개 파일) - {key[0][:8]}...")
            group_item.setText(1, size_str)
            group_item.setBackground(0, Qt.darkGray)
            group_item.setForeground(0, Qt.white)
            group_item.setExpanded(True)

            for p in paths:
                child = QTreeWidgetItem(group_item)
                child.setText(0, p)
                child.setText(1, size_str)
                child.setText(3, os.path.splitext(p)[1])
                
                try:
                    mtime = os.path.getmtime(p)
                    dt = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                    child.setText(2, dt)
                except:
                    child.setText(2, "-")

                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Unchecked)
                child.setData(0, Qt.UserRole, p)

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
                files.append((mtime, item))
            
            # 오래된 순 정렬 -> 첫번째(가장 오래된 것) 제외하고 모두 체크
            files.sort(key=lambda x: x[0])
            for idx, (_, item) in enumerate(files):
                item.setCheckState(0, Qt.Unchecked if idx == 0 else Qt.Checked)

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
                if item.checkState(0) == Qt.Checked:
                    targets.append(item.data(0, Qt.UserRole))
                    self.pending_delete_items.append(item)

        if not targets:
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_no_files_selected"))
            return

        res = QMessageBox.question(self, strings.tr("confirm_delete_title"), 
                                   strings.tr("confirm_delete_msg").format(len(targets)),
                                   QMessageBox.Yes | QMessageBox.No)
        if res != QMessageBox.Yes: return

        self.start_file_operation('delete', targets)

    def perform_undo(self):
        self.start_file_operation('undo')

    def perform_redo(self):
        self.start_file_operation('redo')

    def start_file_operation(self, op_type, data=None):
        # Disable UI
        self.toggle_ui_state(scanning=True) # Re-use scanning state (disables interactions)
        
        # Show Progress Dialog
        self.file_op_dialog = QProgressDialog(strings.tr("status_analyzing"), None, 0, 0, self)
        self.file_op_dialog.setWindowTitle(strings.tr("app_title"))
        self.file_op_dialog.setWindowModality(Qt.WindowModal)
        self.file_op_dialog.setMinimumDuration(0)
        self.file_op_dialog.setCancelButton(None) # Not cancellable for safety
        self.file_op_dialog.show()

        self.file_worker = FileOperationWorker(self.history_manager, op_type, data)
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
                    for item in self.pending_delete_items:
                        parent = item.parent()
                        if parent: parent.removeChild(item)
                    self.pending_delete_items = []
            elif op_type in ('undo', 'redo'):
                 # Refresh tree might be better but checking logic is missing.
                 # For now, just accept the message. Ideally we should re-scan or update tree.
                 QMessageBox.information(self, strings.tr("app_title"), message + "\n" + strings.tr("status_ready"))
            
            self.update_undo_redo_buttons()
        else:
             QMessageBox.warning(self, strings.tr("app_title"), message)
             if op_type == 'delete':
                 self.pending_delete_items = []

    def update_undo_redo_buttons(self):
        self.action_undo.setEnabled(bool(self.history_manager.undo_stack))
        self.action_redo.setEnabled(bool(self.history_manager.redo_stack))

    # --- 기능 구현: 미리보기 ---
    def update_preview(self, current, previous):
        if not current: return
        
        path = current.data(0, Qt.UserRole)
        # 그룹 아이템인 경우 path가 없을 수 있음
        if not path or not os.path.exists(path):
            self.show_preview_info("파일을 선택하세요.")
            return

        if os.path.isdir(path):
            self.show_preview_info(f"폴더: {path}")
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
                    self.lbl_info_preview.setText(f"{path}\n(텍스트 미리보기)")
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

    def load_settings(self):
        geo = self.settings.value("app/geometry")
        if geo: self.restoreGeometry(geo)
        
        state = self.settings.value("app/splitter")
        if state: self.splitter.restoreState(state)
        
        self.txt_extensions.setText(self.settings.value("filter/extensions", ""))
        
        val = self.settings.value("filter/min_size", 0)
        self.spin_min_size.setValue(int(val) if val else 0)
        
        self.chk_protect_system.setChecked(self.settings.value("filter/protect_system", True, type=bool))
        self.chk_byte_compare.setChecked(self.settings.value("filter/byte_compare", False, type=bool))
        
        folders = self.settings.value("folders", [])
        # 리스트가 아니라 단일 문자열로 저장되는 경우가 있어 타입 체크
        if isinstance(folders, str): folders = [folders]
        elif not isinstance(folders, list): folders = []
        
        self.selected_folders = [f for f in folders if os.path.exists(f)]
        self.update_folder_label()

        # Restore Theme
        theme = self.settings.value("app/theme", "light")
        self.action_theme.setChecked(theme == "dark")

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
