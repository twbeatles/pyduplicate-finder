"""
단축키 설정 다이얼로그
주요 기능의 키보드 단축키를 커스터마이징합니다.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QMessageBox, QHeaderView, QKeySequenceEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

from src.utils.i18n import strings


class ShortcutSettingsDialog(QDialog):
    """단축키 설정 다이얼로그"""
    
    # 기본 단축키 정의
    DEFAULT_SHORTCUTS = {
        'start_scan': ('Ctrl+Return', 'action_start_scan'),
        'stop_scan': ('Escape', 'action_stop_scan'),
        'undo': ('Ctrl+Z', 'action_undo'),
        'redo': ('Ctrl+Y', 'action_redo'),
        'delete_selected': ('Delete', 'action_delete'),
        'smart_select': ('Ctrl+A', 'action_smart_select'),
        'export_csv': ('Ctrl+E', 'action_export'),
        'save_results': ('Ctrl+S', 'action_save_results'),
        'load_results': ('Ctrl+O', 'action_load_results'),
        'expand_all': ('Ctrl+Plus', 'action_expand_all'),
        'collapse_all': ('Ctrl+Minus', 'action_collapse_all'),
        'empty_finder': ('Ctrl+Shift+E', 'action_empty_finder'),
        'toggle_theme': ('Ctrl+T', 'action_theme'),
    }
    
    def __init__(self, current_shortcuts: dict, parent=None):
        super().__init__(parent)
        # 현재 설정과 기본값 병합
        self.shortcuts = {**self.DEFAULT_SHORTCUTS}
        if current_shortcuts:
            for key, value in current_shortcuts.items():
                if key in self.shortcuts:
                    self.shortcuts[key] = (value, self.shortcuts[key][1])
        
        self.setWindowTitle(strings.tr("dlg_shortcuts_title"))
        self.setMinimumSize(550, 500)
        
        # Issue #26: Inherit parent theme instead of hardcoded light theme
        if parent and hasattr(parent, 'settings'):
            from src.ui.theme import ModernTheme
            theme = parent.settings.value("app/theme", "light")
            self.setStyleSheet(ModernTheme.get_stylesheet(theme))
        
        self.init_ui()
        self.populate_table()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # === 설명 ===
        desc = QLabel(strings.tr("lbl_shortcut_desc") if strings.tr("lbl_shortcut_desc") != "lbl_shortcut_desc" 
                     else "Click on a shortcut to edit it. Press the new key combination to change.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(desc)
        
        # === 단축키 테이블 ===
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([
            strings.tr("col_action") if strings.tr("col_action") != "col_action" else "Action",
            strings.tr("col_shortcut") if strings.tr("col_shortcut") != "col_shortcut" else "Shortcut",
            strings.tr("col_default") if strings.tr("col_default") != "col_default" else "Default"
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 100)
        
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        
        layout.addWidget(self.table)
        
        # === 편집 영역 ===
        edit_layout = QHBoxLayout()
        
        self.lbl_editing = QLabel(strings.tr("lbl_press_key") if strings.tr("lbl_press_key") != "lbl_press_key" else "Press keys:")
        edit_layout.addWidget(self.lbl_editing)
        
        self.key_edit = QKeySequenceEdit()
        self.key_edit.setMaximumSequenceLength(1)
        self.key_edit.editingFinished.connect(self.on_key_changed)
        edit_layout.addWidget(self.key_edit, 1)
        
        self.btn_clear_key = QPushButton(strings.tr("btn_clear_key") if strings.tr("btn_clear_key") != "btn_clear_key" else "Clear")
        self.btn_clear_key.clicked.connect(self.clear_selected_shortcut)
        edit_layout.addWidget(self.btn_clear_key)
        
        layout.addLayout(edit_layout)
        
        # === 버튼 영역 ===
        btn_layout = QHBoxLayout()
        
        self.btn_reset = QPushButton(strings.tr("btn_reset_defaults") if strings.tr("btn_reset_defaults") != "btn_reset_defaults" else "🔄 Reset to Defaults")
        self.btn_reset.clicked.connect(self.reset_defaults)
        btn_layout.addWidget(self.btn_reset)
        
        btn_layout.addStretch()
        
        self.btn_cancel = QPushButton(strings.tr("btn_cancel") if strings.tr("btn_cancel") != "btn_cancel" else "Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        self.btn_ok = QPushButton(strings.tr("btn_ok") if strings.tr("btn_ok") != "btn_ok" else "OK")
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)
        
        layout.addLayout(btn_layout)
        
        # 테이블 선택 변경 시 키 편집기 업데이트
        self.table.currentCellChanged.connect(self.on_selection_changed)
    
    def populate_table(self):
        """테이블 채우기"""
        self.table.setRowCount(len(self.shortcuts))
        
        for row, (action_id, (shortcut, label_key)) in enumerate(self.shortcuts.items()):
            # 액션 이름
            action_name = strings.tr(label_key) if strings.tr(label_key) != label_key else action_id.replace('_', ' ').title()
            name_item = QTableWidgetItem(action_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            name_item.setData(Qt.UserRole, action_id)
            self.table.setItem(row, 0, name_item)
            
            # 현재 단축키
            shortcut_item = QTableWidgetItem(shortcut)
            shortcut_item.setFlags(shortcut_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, shortcut_item)
            
            # 기본값
            default_shortcut = self.DEFAULT_SHORTCUTS.get(action_id, ('', ''))[0]
            default_item = QTableWidgetItem(default_shortcut)
            default_item.setFlags(default_item.flags() & ~Qt.ItemIsEditable)
            default_item.setForeground(Qt.gray)
            self.table.setItem(row, 2, default_item)
    
    def on_selection_changed(self, row, col, prev_row, prev_col):
        """선택 변경 시 키 편집기 업데이트"""
        if row >= 0:
            shortcut_item = self.table.item(row, 1)
            if shortcut_item:
                self.key_edit.setKeySequence(QKeySequence(shortcut_item.text()))
    
    def on_key_changed(self):
        """키 변경 완료"""
        row = self.table.currentRow()
        if row < 0:
            return
        
        new_key = self.key_edit.keySequence().toString()
        
        # 충돌 확인
        if new_key:
            for r in range(self.table.rowCount()):
                if r != row:
                    existing = self.table.item(r, 1).text()
                    if existing == new_key:
                        action_name = self.table.item(r, 0).text()
                        QMessageBox.warning(
                            self, strings.tr("app_title"),
                            strings.tr("err_shortcut_conflict").format(action_name) if strings.tr("err_shortcut_conflict") != "err_shortcut_conflict" 
                            else f"This shortcut is already used by '{action_name}'."
                        )
                        return
        
        # 테이블 및 데이터 업데이트
        self.table.item(row, 1).setText(new_key)
        
        action_id = self.table.item(row, 0).data(Qt.UserRole)
        old_data = self.shortcuts.get(action_id)
        if old_data:
            self.shortcuts[action_id] = (new_key, old_data[1])
    
    def clear_selected_shortcut(self):
        """선택된 단축키 지우기"""
        row = self.table.currentRow()
        if row >= 0:
            self.table.item(row, 1).setText("")
            self.key_edit.clear()
            
            action_id = self.table.item(row, 0).data(Qt.UserRole)
            old_data = self.shortcuts.get(action_id)
            if old_data:
                self.shortcuts[action_id] = ("", old_data[1])
    
    def reset_defaults(self):
        """모든 단축키를 기본값으로 복원"""
        res = QMessageBox.question(
            self, strings.tr("app_title"),
            strings.tr("confirm_reset_shortcuts") if strings.tr("confirm_reset_shortcuts") != "confirm_reset_shortcuts" 
            else "Reset all shortcuts to defaults?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if res == QMessageBox.Yes:
            self.shortcuts = {k: v for k, v in self.DEFAULT_SHORTCUTS.items()}
            self.populate_table()
    
    def get_shortcuts(self) -> dict:
        """
        현재 단축키 설정 반환
        
        Returns:
            {action_id: shortcut_string, ...}
        """
        return {k: v[0] for k, v in self.shortcuts.items()}
