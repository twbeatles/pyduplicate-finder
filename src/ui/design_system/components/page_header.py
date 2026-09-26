"""Page header + filter row helpers (srtgo PageHeader/FilterRow pattern)."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from src.ui.design_system.tokens import SPACING_MD, SPACING_SM


def create_page_header(
    title: str,
    parent: QWidget | None = None,
) -> tuple[QWidget, QHBoxLayout, QLabel]:
    """Title row: title + stretch (callers append actions + meta)."""
    wrap = QWidget(parent)
    row = QHBoxLayout(wrap)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(SPACING_MD)
    title_label = QLabel(title, wrap)
    title_label.setObjectName("results_title")
    row.addWidget(title_label)
    row.addStretch()
    return wrap, row, title_label


def create_filter_row(parent: QWidget | None = None) -> QHBoxLayout:
    """One-line filter standard: label + input + action + stretch + count."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(SPACING_SM)
    _ = parent
    return row


__all__ = ["create_filter_row", "create_page_header"]
