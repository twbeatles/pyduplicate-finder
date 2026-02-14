"""
Sidebar Navigation Component

Notes:
- Sidebar styling is theme-aware (light/dark) and uses ModernTheme tokens.
- Uses QPropertyAnimation for smooth expand/collapse transitions.
- Active page indicated by left accent bar + button highlight.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QButtonGroup, QLabel, QFrame, QHBoxLayout
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor
from src.utils.i18n import strings
from src.ui.theme import ModernTheme


class SidebarButton(QPushButton):
    """Custom sidebar button with icon and label — styled explicitly"""

    def __init__(self, icon: str, label: str, name: str, parent=None):
        super().__init__(parent)
        self.icon_text = icon
        self.label_text = label
        self.setObjectName(name)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(label)

        self._expanded = True
        self.setProperty("sidebar_btn", True)
        self._update_display()

    def _update_display(self):
        """Update button display based on expanded state"""
        if self._expanded:
            self.setText(f"  {self.icon_text}  {self.label_text}")
            self.setFixedHeight(40)
            self.setMinimumWidth(80)
            self.setMaximumWidth(130)
        else:
            self.setText(self.icon_text)
            self.setFixedSize(44, 44)
        self.setProperty("sidebar_btn", True)

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self._update_display()

    def paintEvent(self, event):
        """Paint the active indicator bar on the left side"""
        super().paintEvent(event)
        if self.isChecked():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 220))
            # draw a small rounded bar on the left edge
            bar_h = 20
            bar_w = 3
            y = (self.height() - bar_h) // 2
            painter.drawRoundedRect(1, y, bar_w, bar_h, 2, 2)
            painter.end()


class Sidebar(QFrame):
    """Collapsible sidebar navigation with smooth animation"""

    page_changed = Signal(str)

    EXPANDED_WIDTH = 128
    COLLAPSED_WIDTH = 52

    NAV_ITEMS = [
        ("⊙", "nav_scan", "scan"),
        ("≡", "nav_results", "results"),
        ("⚒", "nav_tools", "tools"),
    ]

    BOTTOM_ITEMS = [
        ("⚙", "nav_settings", "settings"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._expanded = True
        self.setFixedWidth(self.EXPANDED_WIDTH)
        self.current_page = "scan"

        # Animation for smooth expand/collapse
        self._anim = QPropertyAnimation(self, b"fixedWidth")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._setup_ui()
        self.apply_theme("light")

    # Property for QPropertyAnimation to animate width
    def _get_fixed_width(self) -> int:
        return self.width()

    def _set_fixed_width(self, w: int):
        self.setFixedWidth(w)

    fixedWidth = Property(int, _get_fixed_width, _set_fixed_width)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 14, 6, 14)
        layout.setSpacing(4)

        # Toggle button at top
        self.btn_toggle = QPushButton(self._get_toggle_text())
        self.btn_toggle.setObjectName("sidebar_toggle")
        self.btn_toggle.setFixedHeight(26)
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setToolTip(strings.tr("sidebar_toggle_tooltip"))
        self.btn_toggle.clicked.connect(self.toggle_expand)
        layout.addWidget(self.btn_toggle, alignment=Qt.AlignRight)

        layout.addSpacing(12)

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

        # Bottom items (settings)
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

    def apply_theme(self, mode: str = "light"):
        """Theme-aware styling for the sidebar and its buttons."""
        c = ModernTheme.get_palette(mode)
        bg0 = c.get("primary", "#6366f1")
        bg1 = c.get("primary_hover", "#4f46e5")
        toggle_bg = "rgba(255, 255, 255, 0.15)" if mode == "light" else "rgba(255, 255, 255, 0.08)"
        toggle_hover = "rgba(255, 255, 255, 0.28)" if mode == "light" else "rgba(255, 255, 255, 0.16)"

        self.setStyleSheet(
            f"""
            QFrame#sidebar {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {bg0}, stop:1 {bg1});
                border: none;
            }}

            QPushButton[sidebar_btn="true"] {{
                background: transparent;
                border: none;
                border-radius: 10px;
                color: rgba(255, 255, 255, 0.8);
                padding: 4px;
                text-align: left;
            }}
            QPushButton[sidebar_btn="true"]:hover {{
                background: rgba(255, 255, 255, 0.14);
                color: #ffffff;
            }}
            QPushButton[sidebar_btn="true"]:checked {{
                background: rgba(255, 255, 255, 0.22);
                color: #ffffff;
                font-weight: 600;
            }}

            QPushButton#sidebar_toggle {{
                background: {toggle_bg};
                border: none;
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.85);
                padding: 4px 8px;
                font-size: 8pt;
            }}
            QPushButton#sidebar_toggle:hover {{
                background: {toggle_hover};
            }}
            """
        )

    def toggle_expand(self):
        """Toggle expanded/collapsed state with animation"""
        self._expanded = not self._expanded

        target_width = self.EXPANDED_WIDTH if self._expanded else self.COLLAPSED_WIDTH
        self._anim.stop()
        self._anim.setStartValue(self.width())
        self._anim.setEndValue(target_width)
        self._anim.start()

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
