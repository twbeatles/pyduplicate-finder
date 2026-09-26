"""Layout skeletons: master-detail splitter + scroll with fixed action bar."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.ui.design_system.tokens import MARGIN_PAGE, SPACING_MD, SPLITTER_HANDLE


def create_master_detail(
    parent: QWidget | None = None,
    handle_width: int = SPLITTER_HANDLE,
) -> tuple[QSplitter, QWidget, QWidget]:
    """Horizontal master | detail splitter with non-collapsible children."""
    splitter = QSplitter(Qt.Orientation.Horizontal, parent)
    splitter.setHandleWidth(handle_width)
    splitter.setChildrenCollapsible(False)
    master = QWidget(splitter)
    detail = QWidget(splitter)
    splitter.addWidget(master)
    splitter.addWidget(detail)
    return splitter, master, detail


def create_scroll_with_action_bar(
    parent: QWidget | None = None,
) -> tuple[QWidget, QVBoxLayout, QScrollArea, QWidget, QHBoxLayout]:
    """Scrollable form body with a fixed bottom action bar (srtgo condition card)."""
    body = QWidget(parent)
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(SPACING_MD)

    scroll = QScrollArea(body)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    body_layout.addWidget(scroll, 1)

    action_bar = QWidget(body)
    action_row = QHBoxLayout(action_bar)
    action_row.setContentsMargins(0, 0, 0, 0)
    action_row.setSpacing(SPACING_MD)
    body_layout.addWidget(action_bar)
    return body, body_layout, scroll, action_bar, action_row


def apply_page_margins(layout: QVBoxLayout | QHBoxLayout, margin: int = MARGIN_PAGE) -> None:
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(SPACING_MD)


__all__ = [
    "apply_page_margins",
    "create_master_detail",
    "create_scroll_with_action_bar",
]
