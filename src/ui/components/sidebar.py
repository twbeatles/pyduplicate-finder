"""
Sidebar Navigation Component
Collapsible sidebar with icon-based navigation and visible labels
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QButtonGroup, QLabel, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from src.utils.i18n import strings


class SidebarButton(QPushButton):
    """Custom sidebar button with icon and label - styled explicitly"""
    
    def __init__(self, icon: str, label: str, name: str, parent=None):
        super().__init__(parent)
        self.icon_text = icon
        self.label_text = label
        self.setObjectName(name)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(label)
        
        self._expanded = True
        self._update_display()
    
    def _update_display(self):
        """Update button display"""
        if self._expanded:
            self.setText(f"{self.icon_text}\n{self.label_text}")
            self.setFixedSize(80, 68)
            self.setFont(QFont("Malgun Gothic", 10))
        else:
            self.setText(self.icon_text)
            self.setFixedSize(52, 52)
            self.setFont(QFont("Segoe UI Emoji", 18))
        
        # Explicit white text styling
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 10px;
                color: white;
                padding: 4px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QPushButton:checked {
                background: rgba(255, 255, 255, 0.3);
            }
        """)
    
    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self._update_display()


class Sidebar(QFrame):
    """
    Collapsible sidebar navigation
    """
    
    page_changed = Signal(str)
    
    EXPANDED_WIDTH = 88
    COLLAPSED_WIDTH = 64
    
    NAV_ITEMS = [
        ("🔍", "nav_scan", "scan"),
        ("📊", "nav_results", "results"),
        ("🛠️", "nav_tools", "tools"),
    ]
    
    BOTTOM_ITEMS = [
        ("⚙️", "nav_settings", "settings"),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._expanded = True
        self.setFixedWidth(self.EXPANDED_WIDTH)
        self.current_page = "scan"
        
        # Apply gradient background directly
        self.setStyleSheet("""
            QFrame#sidebar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6366f1, stop:1 #4f46e5);
                border: none;
            }
        """)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(6)
        
        # Toggle button at top with label
        self.btn_toggle = QPushButton(self._get_toggle_text())
        self.btn_toggle.setFixedHeight(28)
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setToolTip(strings.tr("sidebar_toggle_tooltip"))
        self.btn_toggle.setFont(QFont("Malgun Gothic", 9))
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.2);
                border: none;
                border-radius: 6px;
                color: white;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.35);
            }
        """)
        self.btn_toggle.clicked.connect(self.toggle_expand)
        layout.addWidget(self.btn_toggle, alignment=Qt.AlignRight)
        
        layout.addSpacing(10)
        
        # Button group
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.buttons = {}
        
        # Main nav items
        for icon, i18n_key, name in self.NAV_ITEMS:
            label = strings.tr(i18n_key)
            btn = SidebarButton(icon, label, f"nav_{name}", self)
            btn.clicked.connect(lambda checked, n=name: self._on_nav_clicked(n))
            self.button_group.addButton(btn)
            self.buttons[name] = btn
            layout.addWidget(btn, alignment=Qt.AlignCenter)
        
        layout.addStretch()
        
        # Bottom items
        for icon, i18n_key, name in self.BOTTOM_ITEMS:
            label = strings.tr(i18n_key)
            btn = SidebarButton(icon, label, f"nav_{name}", self)
            btn.clicked.connect(lambda checked, n=name: self._on_nav_clicked(n))
            self.button_group.addButton(btn)
            self.buttons[name] = btn
            layout.addWidget(btn, alignment=Qt.AlignCenter)
        
        # Default selection
        if "scan" in self.buttons:
            self.buttons["scan"].setChecked(True)
    
    def toggle_expand(self):
        """Toggle expanded/collapsed state"""
        self._expanded = not self._expanded
        
        if self._expanded:
            self.setFixedWidth(self.EXPANDED_WIDTH)
            self.btn_toggle.setText(self._get_toggle_text())
        else:
            self.setFixedWidth(self.COLLAPSED_WIDTH)
            self.btn_toggle.setText(self._get_toggle_text())
        
        for btn in self.buttons.values():
            btn.set_expanded(self._expanded)
    
    def _on_nav_clicked(self, name: str):
        if name != self.current_page:
            self.current_page = name
            self.page_changed.emit(name)
    
    def set_page(self, name: str):
        if name in self.buttons:
            self.buttons[name].setChecked(True)
            self.current_page = name
    
    def retranslate(self):
        self.btn_toggle.setToolTip(strings.tr("sidebar_toggle_tooltip"))
        self.btn_toggle.setText(self._get_toggle_text())
        for icon, i18n_key, name in self.NAV_ITEMS + self.BOTTOM_ITEMS:
            if name in self.buttons:
                label = strings.tr(i18n_key)
                btn = self.buttons[name]
                btn.label_text = label
                btn.setToolTip(label)
                btn._update_display()

    def _get_toggle_text(self):
        return strings.tr("sidebar_collapse") if self._expanded else strings.tr("sidebar_expand")
