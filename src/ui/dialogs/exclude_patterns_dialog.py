"""
제외 패턴 설정 다이얼로그
스캔 시 제외할 폴더/파일 패턴을 설정합니다.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QLabel, QGroupBox, QMessageBox, QComboBox, QAbstractItemView
)
from PySide6.QtCore import Qt

from typing import Optional

from src.utils.i18n import strings


class ExcludePatternsDialog(QDialog):
    """패턴 설정 다이얼로그 (Exclude/Include 공용으로 사용 가능)."""
    
    # 일반적인 제외 패턴 프리셋
    COMMON_PATTERNS = [
        ("node_modules", "Node.js modules"),
        (".git", "Git repository"),
        ("__pycache__", "Python cache"),
        (".venv", "Python virtual environment"),
        ("*.log", "Log files"),
        ("*.tmp", "Temporary files"),
        ("*.bak", "Backup files"),
        ("Thumbs.db", "Windows thumbnails"),
        (".DS_Store", "macOS metadata"),
        ("*.pyc", "Python compiled"),
        ("dist", "Distribution folder"),
        ("build", "Build folder"),
    ]
    
    COMMON_INCLUDE_PATTERNS = [
        ("*.jpg", "JPEG images"),
        ("*.png", "PNG images"),
        ("*.gif", "GIF images"),
        ("*.mp4", "MP4 videos"),
        ("*.pdf", "PDF documents"),
        ("*.zip", "ZIP archives"),
    ]

    def __init__(
        self,
        patterns: list[str],
        parent=None,
        *,
        title: Optional[str] = None,
        desc: Optional[str] = None,
        placeholder: Optional[str] = None,
        common_patterns=None,
    ):
        super().__init__(parent)
        self.patterns = patterns.copy() if patterns else []
        self._title = title
        self._desc = desc
        self._placeholder = placeholder
        self._common_patterns = list(common_patterns) if common_patterns is not None else list(self.COMMON_PATTERNS)
        
        self.setWindowTitle(self._title or strings.tr("dlg_exclude_title"))
        self.setMinimumSize(500, 450)
        
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
        
        # === 설명 ===
        desc = QLabel(self._desc or strings.tr("lbl_exclude_desc"))
        desc.setWordWrap(True)
        desc.setObjectName("card_desc")
        layout.addWidget(desc)
        
        # === 패턴 목록 ===
        list_group = QGroupBox(strings.tr("lbl_current_patterns"))
        list_layout = QVBoxLayout(list_group)
        
        self.pattern_list = QListWidget()
        self.pattern_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        list_layout.addWidget(self.pattern_list)
        
        layout.addWidget(list_group)
        
        # === 추가 영역 ===
        add_group = QGroupBox(strings.tr("lbl_add_pattern"))
        add_layout = QVBoxLayout(add_group)
        
        # 직접 입력
        input_layout = QHBoxLayout()
        self.txt_pattern = QLineEdit()
        self.txt_pattern.setPlaceholderText(self._placeholder or strings.tr("ph_exclude_pattern"))
        self.txt_pattern.returnPressed.connect(self.add_pattern)
        input_layout.addWidget(self.txt_pattern, 1)
        
        self.btn_add = QPushButton("+")
        self.btn_add.setFixedWidth(40)
        self.btn_add.clicked.connect(self.add_pattern)
        input_layout.addWidget(self.btn_add)
        
        add_layout.addLayout(input_layout)
        
        # 일반 패턴 드롭다운
        preset_layout = QHBoxLayout()
        preset_label = QLabel(strings.tr("lbl_common_patterns"))
        preset_layout.addWidget(preset_label)
        
        self.combo_presets = QComboBox()
        self.combo_presets.addItem(strings.tr("opt_select"), None)
        for pattern, desc in self._common_patterns:
            self.combo_presets.addItem(f"{pattern} ({desc})", pattern)
        preset_layout.addWidget(self.combo_presets, 1)
        
        self.btn_add_preset = QPushButton(strings.tr("btn_add"))
        self.btn_add_preset.clicked.connect(self.add_preset_pattern)
        preset_layout.addWidget(self.btn_add_preset)
        
        add_layout.addLayout(preset_layout)
        
        layout.addWidget(add_group)
        
        # === 버튼 영역 ===
        btn_layout = QHBoxLayout()
        
        self.btn_remove = QPushButton(strings.tr("btn_remove"))
        self.btn_remove.clicked.connect(self.remove_selected)
        btn_layout.addWidget(self.btn_remove)
        
        self.btn_clear = QPushButton(strings.tr("btn_clear_all"))
        self.btn_clear.clicked.connect(self.clear_all)
        btn_layout.addWidget(self.btn_clear)
        
        btn_layout.addStretch()
        
        self.btn_cancel = QPushButton(strings.tr("btn_cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        self.btn_ok = QPushButton(strings.tr("btn_ok"))
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)
        
        layout.addLayout(btn_layout)
    
    def refresh_list(self):
        """패턴 목록 새로고침"""
        self.pattern_list.clear()
        for pattern in self.patterns:
            item = QListWidgetItem(pattern)
            item.setData(Qt.ItemDataRole.UserRole, pattern)
            self.pattern_list.addItem(item)
    
    def add_pattern(self):
        """새 패턴 추가"""
        pattern = self.txt_pattern.text().strip()
        if pattern and pattern not in self.patterns:
            self.patterns.append(pattern)
            self.refresh_list()
            self.txt_pattern.clear()
    
    def add_preset_pattern(self):
        """프리셋에서 패턴 추가"""
        pattern = self.combo_presets.currentData()
        if pattern and pattern not in self.patterns:
            self.patterns.append(pattern)
            self.refresh_list()
    
    def remove_selected(self):
        """선택된 패턴 삭제"""
        selected_items = self.pattern_list.selectedItems()
        for item in selected_items:
            pattern = item.data(Qt.ItemDataRole.UserRole)
            if pattern in self.patterns:
                self.patterns.remove(pattern)
        self.refresh_list()
    
    def clear_all(self):
        """모든 패턴 삭제"""
        if self.patterns:
            res = QMessageBox.question(
                self,
                strings.tr("app_title"),
                strings.tr("confirm_clear_patterns"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Yes:
                self.patterns.clear()
                self.refresh_list()
    
    def get_patterns(self) -> list[str]:
        """현재 패턴 목록 반환"""
        return self.patterns.copy()
