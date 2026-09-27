"""WinUI InfoBar widget (pure PySide6).

A persistent inline notice: severity icon + title + message + optional close
button. Unlike ``ToastNotification`` (transient, timed), an InfoBar stays in
the page layout until dismissed — used for partial-scan warnings and other
sticky states. Colors come from ``src.ui.design_system.fluent``; the global
Fluent QSS fragment styles ``QFrame#InfoBar`` per ``severity`` property.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.design_system import fluent
from src.utils.i18n import strings


class InfoBar(QFrame):
    """Inline severity notice with title, message, and dismiss action."""

    closed = Signal()

    def __init__(
        self,
        severity: str = "info",
        title: str = "",
        message: str = "",
        closable: bool = True,
        parent: QWidget | None = None,
        mode: str = "light",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("InfoBar")
        self._severity = severity if severity in fluent.VALID_SEVERITIES else "info"
        self._mode = fluent.normalize_mode(mode)
        self.setProperty("severity", self._severity)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.icon_label = QLabel(fluent.INFO_ICONS[self._severity], self)
        self.icon_label.setObjectName("InfoBarIcon")
        layout.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("InfoBarTitle")
        self.title_label.setWordWrap(True)
        self.message_label = QLabel(message, self)
        self.message_label.setObjectName("InfoBarMessage")
        self.message_label.setWordWrap(True)
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.message_label)
        layout.addLayout(text_col, 1)

        self.close_button = QPushButton("\u2715", self)
        self.close_button.setObjectName("InfoBarClose")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip(strings.tr("infobar_close"))
        fluent.apply_fluent_button(self.close_button, "subtle")
        self.close_button.clicked.connect(self.dismiss)
        self.close_button.setVisible(closable)
        layout.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)

        self._apply_severity_style()

    def apply_mode(self, mode: str) -> None:
        """Refresh label colors after a light/dark theme switch."""
        self._mode = fluent.normalize_mode(mode)
        self._apply_severity_style()

    def _apply_severity_style(self) -> None:
        colors = fluent.info_colors(self._severity, self._mode)
        self.icon_label.setStyleSheet(f"color: {colors['icon']}; background: transparent; border: none;")
        self.title_label.setStyleSheet(f"color: {colors['fg']}; background: transparent; border: none;")
        self.message_label.setStyleSheet(f"color: {colors['fg']}; background: transparent; border: none;")

    @property
    def severity(self) -> str:
        return self._severity

    def set_severity(self, severity: str) -> None:
        if severity not in fluent.VALID_SEVERITIES:
            severity = "info"
        self._severity = severity
        self.setProperty("severity", severity)
        self.icon_label.setText(fluent.INFO_ICONS[severity])
        self._apply_severity_style()
        self.style().unpolish(self)
        self.style().polish(self)

    def set_text(self, title: str, message: str = "") -> None:
        self.title_label.setText(title)
        self.message_label.setText(message)
        self.message_label.setVisible(bool(message))

    def show_notice(self, severity: str, title: str, message: str = "") -> None:
        """One-call update used by scan-completion handlers."""
        self.set_severity(severity)
        self.set_text(title, message)
        self.setVisible(True)

    def dismiss(self) -> None:
        self.setVisible(False)
        self.closed.emit()

    def retranslate(self) -> None:
        self.close_button.setToolTip(strings.tr("infobar_close"))


def create_info_bar(
    severity: str = "info",
    title: str = "",
    message: str = "",
    closable: bool = True,
    parent: QWidget | None = None,
    mode: str = "light",
) -> InfoBar:
    """Factory mirroring the other ``create_*`` component helpers."""
    bar = InfoBar(severity=severity, title=title, message=message, closable=closable, parent=parent, mode=mode)
    bar.setVisible(False)
    return bar


__all__ = ["InfoBar", "create_info_bar"]
