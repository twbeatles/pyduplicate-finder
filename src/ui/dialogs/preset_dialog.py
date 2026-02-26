"""
프리셋 관리 다이얼로그
스캔 프리셋을 저장, 로드, 삭제할 수 있는 다이얼로그입니다.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QLabel, QGroupBox, QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt

from src.core.preset_manager import PresetManager, get_default_config
from src.utils.i18n import strings


class PresetDialog(QDialog):
    """프리셋 관리 다이얼로그"""
    
    def __init__(self, preset_manager: PresetManager, current_config: dict, parent=None):
        super().__init__(parent)
        self.preset_manager = preset_manager
        self.current_config = current_config
        self.selected_config = None
        
        self.setWindowTitle(strings.tr("dlg_preset_title"))
        self.setMinimumSize(450, 400)
        
        # Apply parent theme
        if parent and hasattr(parent, 'settings'):
            from src.ui.theme import ModernTheme
            theme = parent.settings.value("app/theme", "light")
            self.setStyleSheet(ModernTheme.get_stylesheet(theme))
        
        self.init_ui()
        self.refresh_list()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # === 프리셋 목록 ===
        list_group = QGroupBox(strings.tr("dlg_preset_title"))
        list_layout = QVBoxLayout(list_group)
        
        self.preset_list = QListWidget()
        self.preset_list.itemDoubleClicked.connect(self.load_selected)
        list_layout.addWidget(self.preset_list)
        
        layout.addWidget(list_group)
        
        # === 저장 영역 ===
        save_layout = QHBoxLayout()
        
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText(strings.tr("ph_preset_name"))
        save_layout.addWidget(self.txt_name, 1)
        
        self.btn_save = QPushButton(strings.tr("btn_save_preset"))
        self.btn_save.clicked.connect(self.save_preset)
        save_layout.addWidget(self.btn_save)
        
        layout.addLayout(save_layout)
        
        # === 버튼 영역 ===
        btn_layout = QHBoxLayout()
        
        self.btn_load = QPushButton(strings.tr("btn_load_preset"))
        self.btn_load.clicked.connect(self.load_selected)
        btn_layout.addWidget(self.btn_load)
        
        self.btn_delete = QPushButton(strings.tr("btn_delete_preset"))
        self.btn_delete.clicked.connect(self.delete_selected)
        btn_layout.addWidget(self.btn_delete)
        
        btn_layout.addStretch()
        
        self.btn_close = QPushButton(strings.tr("btn_close"))
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
    
    def refresh_list(self):
        """프리셋 목록 새로고침"""
        self.preset_list.clear()
        
        for preset in self.preset_manager.list_presets():
            item = QListWidgetItem(preset['name'])
            item.setData(Qt.UserRole, preset['name'])
            if preset.get('created_at'):
                item.setToolTip(strings.tr("preset_created_at").format(created=preset['created_at']))
            self.preset_list.addItem(item)
    
    def save_preset(self):
        """현재 설정을 프리셋으로 저장"""
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, strings.tr("app_title"), 
                              strings.tr("err_preset_name"))
            return
        
        # 이미 존재하는 경우 덮어쓰기 확인
        if self.preset_manager.preset_exists(name):
            res = QMessageBox.question(
                self, strings.tr("app_title"),
                strings.tr("confirm_overwrite_preset").format(name),
                QMessageBox.Yes | QMessageBox.No
            )
            if res != QMessageBox.Yes:
                return
        
        if self.preset_manager.save_preset(name, self.current_config):
            QMessageBox.information(self, strings.tr("app_title"),
                                  strings.tr("msg_preset_saved").format(name))
            self.txt_name.clear()
            self.refresh_list()
        else:
            QMessageBox.warning(self, strings.tr("app_title"),
                              strings.tr("err_preset_save"))
    
    def load_selected(self):
        """선택된 프리셋 로드"""
        item = self.preset_list.currentItem()
        if not item:
            return
        
        name = item.data(Qt.UserRole)
        config = self.preset_manager.load_preset(name)
        
        if config:
            self.selected_config = config
            self.accept()
        else:
            QMessageBox.warning(self, strings.tr("app_title"),
                              strings.tr("err_preset_load"))
    
    def delete_selected(self):
        """선택된 프리셋 삭제"""
        item = self.preset_list.currentItem()
        if not item:
            return
        
        name = item.data(Qt.UserRole)
        
        res = QMessageBox.question(
            self, strings.tr("app_title"),
            strings.tr("confirm_delete_preset").format(name),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if res == QMessageBox.Yes:
            if self.preset_manager.delete_preset(name):
                self.refresh_list()
            else:
                QMessageBox.warning(self, strings.tr("app_title"),
                                  strings.tr("err_preset_delete"))
