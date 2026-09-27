"""
Toast Notification Component (Fluent InfoBar visual language, pure PySide6).

Clean, modern toast notifications with proper cleanup and positioning.
Severity colors come from the shared Fluent tokens
(``src.ui.design_system.fluent``) so toasts match inline InfoBars.
Show/dismiss uses a short Fluent-style fade for a calmer transition.
"""
from contextlib import suppress

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from src.ui.design_system import fluent
from src.ui.theme import ModernTheme


class ToastNotification(QFrame):
    """
    Modern toast notification with clean rounded design
    Inherits from QFrame for proper background painting
    """

    ICONS = {
        "info": "ℹ️",
        "success": "✓",
        "warning": "⚠",
        "error": "✕",
    }

    FADE_IN_MS = 120
    FADE_OUT_MS = 150

    @staticmethod
    def _style_for(toast_type: str, mode: str):
        colors = fluent.info_colors(toast_type, mode)
        return {"bg": colors["bg"], "fg": colors["fg"], "border": colors["border"]}

    def __init__(
        self,
        message: str,
        toast_type: str = "info",
        duration: int = 2500,
        parent=None,
        theme_mode: str = "light",
    ):
        super().__init__(parent)

        self.duration = duration
        self.toast_type = toast_type if toast_type in fluent.VALID_SEVERITIES else "info"
        self.theme_mode = fluent.normalize_mode(theme_mode)
        self.style_config = self._style_for(self.toast_type, self.theme_mode)
        self.icon = self.ICONS.get(self.toast_type, self.ICONS["info"])

        # Window setup for floating notification
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Fluent fade effect (opacity animated on show/dismiss).
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)
        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.finished.connect(self._on_fade_finished)
        self._closing = False

        self._setup_ui(message)
        self._setup_timer()

    def _setup_ui(self, message: str):
        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Icon
        icon_label = QLabel(self.icon)
        icon_label.setFont(self.font())
        icon_label.setStyleSheet(f"color: {self.style_config['fg']}; background: transparent;")
        layout.addWidget(icon_label)

        # Message
        msg_label = QLabel(message)
        msg_label.setFont(self.font())
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(f"color: {self.style_config['fg']}; background: transparent;")
        layout.addWidget(msg_label)

        # Frame styling
        self.setStyleSheet(f"""
            ToastNotification {{
                background-color: {self.style_config['bg']};
                border: 1px solid {self.style_config['border']};
                border-radius: {ModernTheme.RADIUS_MD};
            }}
        """)

        self.setMinimumWidth(200)
        self.setMinimumHeight(44)
        self.adjustSize()

    def _setup_timer(self):
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.dismiss)

    def _on_fade_finished(self):
        """Close and ensure cleanup once the fade-out completes."""
        if self._closing:
            self.close()
            self.deleteLater()

    def show_toast(self):
        """Show the toast with a short fade-in."""
        self._closing = False
        self.show()
        self.raise_()
        self.activateWindow()
        self._opacity.setOpacity(0.0)
        self._fade_anim.stop()
        self._fade_anim.setDuration(self.FADE_IN_MS)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()
        self.dismiss_timer.start(self.duration)

    def dismiss(self):
        """Manually dismiss with a short fade-out."""
        with suppress(Exception):
            self.dismiss_timer.stop()
        if self._closing:
            return
        self._closing = True
        self._fade_anim.stop()
        self._fade_anim.setDuration(self.FADE_OUT_MS)
        self._fade_anim.setStartValue(self._opacity.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()


class ToastManager:
    """
    Manages toast notifications - only shows one at a time for cleaner UI
    """

    def __init__(self, parent: QWidget):
        self.parent = parent
        self.current_toast = None
        self.margin_bottom = 80
        self.margin_right = 24
        self.theme_mode = "light"

    def set_theme_mode(self, mode: str):
        self.theme_mode = fluent.normalize_mode(mode)

    def show_toast(self, message: str, toast_type: str = "info",
                   duration: int = 2500):
        """Show a toast notification (replaces any existing one)"""
        if not self.parent:
            return

        # Close existing toast first
        if self.current_toast:
            with suppress(Exception):
                self.current_toast.dismiss_timer.stop()
                self.current_toast.close()
                self.current_toast.deleteLater()
            self.current_toast = None

        # Create new toast
        toast = ToastNotification(message, toast_type, duration, theme_mode=self.theme_mode)
        self.current_toast = toast

        # Position
        self._position_toast(toast)

        # Show
        toast.show_toast()

        # Cleanup reference when closed
        toast.destroyed.connect(self._on_toast_destroyed)

    def _position_toast(self, toast):
        """Position toast in bottom-right of parent"""
        if not self.parent:
            return

        with suppress(Exception):
            parent_rect = self.parent.geometry()
            global_pos = self.parent.mapToGlobal(QPoint(0, 0))

            toast_width = toast.width()
            toast_height = toast.height()

            x = global_pos.x() + parent_rect.width() - toast_width - self.margin_right
            y = global_pos.y() + parent_rect.height() - toast_height - self.margin_bottom

            toast.move(max(0, x), max(0, y))

    def _on_toast_destroyed(self):
        """Clear reference when toast is destroyed"""
        self.current_toast = None

    def info(self, message: str, duration: int = 2500):
        self.show_toast(message, "info", duration)

    def success(self, message: str, duration: int = 2500):
        self.show_toast(message, "success", duration)

    def warning(self, message: str, duration: int = 2500):
        self.show_toast(message, "warning", duration)

    def error(self, message: str, duration: int = 2500):
        self.show_toast(message, "error", duration)
