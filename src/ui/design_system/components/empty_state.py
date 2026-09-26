"""Empty-state + status badge helpers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.ui.design_system.tokens import SPACING_MD, SPACING_XL


def create_empty_state(
    message: str,
    icon: str = "",
    parent: QWidget | None = None,
) -> tuple[QWidget, QLabel]:
    """Centered empty-state block; decoration (icon) stays outside tr strings."""
    wrap = QWidget(parent)
    layout = QVBoxLayout(wrap)
    layout.setContentsMargins(SPACING_XL, SPACING_XL, SPACING_XL, SPACING_XL)
    layout.setSpacing(SPACING_MD)
    layout.addStretch()
    text = f"{icon}\n\n{message}" if icon else message
    label = QLabel(text, wrap)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setObjectName("empty_state")
    layout.addWidget(label)
    layout.addStretch()
    return wrap, label


def create_status_row(parent: QWidget | None = None) -> tuple[QWidget, QHBoxLayout, QLabel]:
    """Progress + status pair (srtgo 28px ProgressRing + status label, ring omitted)."""
    wrap = QWidget(parent)
    row = QHBoxLayout(wrap)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(SPACING_MD)
    status = QLabel(wrap)
    status.setObjectName("stage_badge")
    row.addWidget(status)
    row.addStretch()
    return wrap, row, status


__all__ = ["create_empty_state", "create_status_row"]
