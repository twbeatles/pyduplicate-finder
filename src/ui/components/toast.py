"""
Toast Notification Component
Clean, modern toast notifications with proper cleanup and positioning
"""
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QFrame
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QFont, QColor, QPalette, QPainter, QBrush, QPen, QPainterPath


class ToastNotification(QFrame):
    """
    Modern toast notification with clean rounded design
    Inherits from QFrame for proper background painting
    """
    
    TOAST_STYLES = {
        "info": {
            "icon": "ℹ️",
            "bg": "#dbeafe",
            "fg": "#1e40af", 
            "border": "#93c5fd",
        },
        "success": {
            "icon": "✓",
            "bg": "#dcfce7",
            "fg": "#166534",
            "border": "#86efac",
        },
        "warning": {
            "icon": "⚠",
            "bg": "#fef3c7",
            "fg": "#92400e",
            "border": "#fcd34d",
        },
        "error": {
            "icon": "✕",
            "bg": "#fee2e2",
            "fg": "#991b1b",
            "border": "#fca5a5",
        },
    }
    
    def __init__(self, message: str, toast_type: str = "info", 
                 duration: int = 2500, parent=None):
        super().__init__(parent)
        
        self.duration = duration
        self.toast_type = toast_type
        self.style_config = self.TOAST_STYLES.get(toast_type, self.TOAST_STYLES["info"])
        
        # Window setup for floating notification
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        
        self._setup_ui(message)
        self._setup_timer()
    
    def _setup_ui(self, message: str):
        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        
        # Icon
        icon_label = QLabel(self.style_config["icon"])
        icon_label.setFont(QFont("Segoe UI Symbol", 12))
        icon_label.setStyleSheet(f"color: {self.style_config['fg']}; background: transparent;")
        layout.addWidget(icon_label)
        
        # Message
        msg_label = QLabel(message)
        msg_label.setFont(QFont("Malgun Gothic", 10))
        msg_label.setStyleSheet(f"color: {self.style_config['fg']}; background: transparent;")
        layout.addWidget(msg_label)
        
        # Frame styling
        self.setStyleSheet(f"""
            ToastNotification {{
                background-color: {self.style_config['bg']};
                border: 1px solid {self.style_config['border']};
                border-radius: 10px;
            }}
        """)
        
        self.setMinimumWidth(200)
        self.setFixedHeight(44)
        self.adjustSize()
    
    def _setup_timer(self):
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self._auto_close)
    
    def _auto_close(self):
        """Close and ensure cleanup"""
        self.close()
        self.deleteLater()
    
    def show_toast(self):
        """Show the toast"""
        self.show()
        self.raise_()
        self.activateWindow()
        self.dismiss_timer.start(self.duration)
    
    def dismiss(self):
        """Manually dismiss"""
        self.dismiss_timer.stop()
        self._auto_close()


class ToastManager:
    """
    Manages toast notifications - only shows one at a time for cleaner UI
    """
    
    def __init__(self, parent: QWidget):
        self.parent = parent
        self.current_toast = None
        self.margin_bottom = 80
        self.margin_right = 24
    
    def show_toast(self, message: str, toast_type: str = "info", 
                   duration: int = 2500):
        """Show a toast notification (replaces any existing one)"""
        if not self.parent:
            return
        
        # Close existing toast first
        if self.current_toast:
            try:
                self.current_toast.dismiss_timer.stop()
                self.current_toast.close()
                self.current_toast.deleteLater()
            except:
                pass
            self.current_toast = None
        
        # Create new toast
        toast = ToastNotification(message, toast_type, duration)
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
        
        try:
            parent_rect = self.parent.geometry()
            global_pos = self.parent.mapToGlobal(QPoint(0, 0))
            
            toast_width = toast.width()
            toast_height = toast.height()
            
            x = global_pos.x() + parent_rect.width() - toast_width - self.margin_right
            y = global_pos.y() + parent_rect.height() - toast_height - self.margin_bottom
            
            toast.move(max(0, x), max(0, y))
        except:
            pass
    
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
