"""
빈 폴더 찾기 다이얼로그
Empty folder finder dialog with async scanning support.
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QListWidget, 
                               QLabel, QMessageBox, QHBoxLayout, QFrame, QApplication)
from PySide6.QtCore import Qt
from src.core.empty_folder_finder import EmptyFolderFinder, EmptyFolderWorker
from src.utils.i18n import strings
from src.ui.theme import ModernTheme


class EmptyFolderDialog(QDialog):
    """
    Dialog for finding and deleting empty folders.
    Enhanced with modern styling, async scanning, and better UX.
    """
    
    def __init__(self, folders, parent=None):
        super().__init__(parent)
        self.setWindowTitle(strings.tr("dlg_empty_title"))
        self.resize(700, 550)
        self.folders = folders
        self.finder = EmptyFolderFinder(self.folders)
        self.worker = None
        
        # Apply parent theme if available
        if parent and hasattr(parent, 'settings'):
            theme = parent.settings.value("app/theme", "light")
            self.apply_theme(theme)
        
        self.init_ui()

    def apply_theme(self, theme_name):
        """Apply theme styling to the dialog."""
        style = ModernTheme.get_stylesheet(theme_name)
        colors = ModernTheme.get_palette(theme_name)
        
        # Additional dialog-specific styling
        extra_style = f"""
        QDialog {{
            background-color: {colors['bg']};
        }}
        """
        self.setStyleSheet(style + extra_style)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header_label = QLabel(strings.tr('lbl_search_target').format(len(self.folders)))
        header_label.setStyleSheet("font-size: 15px; font-weight: 600; padding: 8px 0;")
        layout.addWidget(header_label)
        
        # Results list
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(350)
        layout.addWidget(self.list_widget)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.btn_scan = QPushButton(strings.tr("btn_scan_empty"))
        self.btn_scan.setMinimumHeight(44)
        self.btn_scan.setCursor(Qt.PointingHandCursor)
        self.btn_scan.setObjectName("btn_primary")
        self.btn_scan.clicked.connect(self.scan_folders)
        
        self.btn_stop = QPushButton(strings.tr("action_stop_scan"))
        self.btn_stop.setMinimumHeight(44)
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_scan)
        
        self.btn_delete = QPushButton(strings.tr("btn_delete_all"))
        self.btn_delete.setMinimumHeight(44)
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setObjectName("btn_danger")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self.delete_folders)
        
        btn_layout.addWidget(self.btn_scan)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)
        
        # Status bar
        self.lbl_status = QLabel(strings.tr("status_ready"))
        self.lbl_status.setStyleSheet("color: palette(mid); font-size: 13px; padding: 8px 0;")
        layout.addWidget(self.lbl_status)

    def scan_folders(self):
        """비동기적으로 빈 폴더 검색 시작"""
        self.lbl_status.setText(strings.tr("status_searching"))
        self.list_widget.clear()
        self.btn_scan.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_delete.setEnabled(False)
        
        # 워커 스레드 시작
        # Issue #F3: EmptyFolderWorker takes only 1 argument (roots)
        self.worker = EmptyFolderWorker(self.folders)
        # Issue #F1: Connect to search_finished signal (not QThread.finished)
        self.worker.search_finished.connect(self.on_scan_finished)
        self.worker.start()
    
    def stop_scan(self):
        """스캔 중단"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.lbl_status.setText(strings.tr("status_stopped"))
            self.btn_scan.setEnabled(True)
            self.btn_stop.setEnabled(False)
    
    def on_scan_finished(self, empties):
        """스캔 완료 핸들러"""
        for path in empties:
            self.list_widget.addItem(path)
            
        self.lbl_status.setText(strings.tr("status_search_done").format(len(empties)))
        self.btn_delete.setEnabled(len(empties) > 0)
        self.btn_scan.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.worker = None

    def delete_folders(self):
        count = self.list_widget.count()
        if count == 0:
            return
        
        res = QMessageBox.warning(
            self, 
            strings.tr("confirm_delete_title"), 
            strings.tr("confirm_empty_delete").format(count), 
            QMessageBox.Yes | QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return
        
        # Extract paths (remove the folder emoji prefix)
        targets = []
        for i in range(count):
            item_text = self.list_widget.item(i).text()
            targets.append(item_text)
        
        deleted, failed = self.finder.delete_folders(targets)
        
        QMessageBox.information(
            self, 
            strings.tr("status_done"), 
            strings.tr("msg_empty_delete_result").format(len(deleted), len(failed))
        )
        
        # Rescan to verify or find newly empty parents
        self.scan_folders()
    
    def closeEvent(self, event):
        """다이얼로그 종료 시 워커 정리"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)  # 최대 2초 대기
        event.accept()
