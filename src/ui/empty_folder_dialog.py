from PySide6.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QListWidget, 
                               QLabel, QMessageBox, QHBoxLayout)
from PySide6.QtCore import Qt
from src.core.empty_folder_finder import EmptyFolderFinder
from src.utils.i18n import strings

class EmptyFolderDialog(QDialog):
    def __init__(self, folders, parent=None):
        super().__init__(parent)
        self.setWindowTitle(strings.tr("dlg_empty_title"))
        self.resize(600, 500)
        self.folders = folders
        self.finder = EmptyFolderFinder(self.folders)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(strings.tr("lbl_search_target").format(len(self.folders))))
        
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        self.btn_scan = QPushButton(strings.tr("btn_scan_empty"))
        self.btn_scan.clicked.connect(self.scan_folders)
        
        self.btn_delete = QPushButton(strings.tr("btn_delete_all"))
        self.btn_delete.setStyleSheet("background-color: #e74c3c; color: white;")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self.delete_folders)
        
        btn_layout.addWidget(self.btn_scan)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)
        
        self.lbl_status = QLabel(strings.tr("status_ready"))
        layout.addWidget(self.lbl_status)

    def scan_folders(self):
        self.lbl_status.setText(strings.tr("status_searching"))
        self.list_widget.clear()
        
        empties = self.finder.find_empty_folders()
        
        for path in empties:
            self.list_widget.addItem(path)
            
        self.lbl_status.setText(strings.tr("status_search_done").format(len(empties)))
        self.btn_delete.setEnabled(len(empties) > 0)

    def delete_folders(self):
        count = self.list_widget.count()
        if count == 0: return
        
        res = QMessageBox.warning(self, strings.tr("confirm_delete_title"), strings.tr("confirm_empty_delete").format(count), 
                                  QMessageBox.Yes | QMessageBox.No)
        if res != QMessageBox.Yes: return
        
        targets = [self.list_widget.item(i).text() for i in range(count)]
        deleted, failed = self.finder.delete_folders(targets)
        
        QMessageBox.information(self, strings.tr("status_done"), strings.tr("msg_empty_delete_result").format(len(deleted), len(failed)))
        self.scan_folders() # Rescan to verify or find newly empty parents
