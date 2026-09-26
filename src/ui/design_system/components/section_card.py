"""SectionCard — srtgo HeaderCard pattern on pure PySide6.

Header (title + optional hint/actions) over a body layout, built on
QGroupBox so the existing ``ModernTheme`` QGroupBox card style applies
without hardcoded QSS.
"""

from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.ui.design_system.tokens import (
    MARGIN_CARD,
    MARGIN_PAGE,
    SPACING_LG,
    SPACING_MD,
    SPACING_SM,
)


def create_section(title: str, parent: QWidget | None = None) -> tuple[QGroupBox, QVBoxLayout]:
    """Create a titled card section and return (group, body_layout)."""
    group = QGroupBox(title, parent)
    body = QVBoxLayout(group)
    body.setContentsMargins(MARGIN_CARD, MARGIN_CARD, MARGIN_CARD, MARGIN_CARD)
    body.setSpacing(SPACING_MD)
    return group, body


def create_section_header(
    title: str,
    hint: str = "",
    parent: QWidget | None = None,
) -> tuple[QWidget, QHBoxLayout, QLabel]:
    """Create a card-title row (title + stretch + hint), srtgo headerLayout style."""
    wrap = QWidget(parent)
    row = QHBoxLayout(wrap)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(SPACING_SM)
    title_label = QLabel(title, wrap)
    title_label.setObjectName("card_title")
    row.addWidget(title_label)
    row.addStretch()
    hint_label = QLabel(hint, wrap)
    hint_label.setObjectName("results_meta")
    row.addWidget(hint_label)
    return wrap, row, hint_label


def create_card(parent: QWidget | None = None) -> tuple[QWidget, QVBoxLayout]:
    """Standard content card (``folder_card`` surface, uniform padding).

    Replaces the ad-hoc ``QWidget`` + ``setContentsMargins(20, 16, ...)``
    boilerplate repeated across pages.
    """
    card = QWidget(parent)
    card.setObjectName("folder_card")
    body = QVBoxLayout(card)
    body.setContentsMargins(MARGIN_PAGE, MARGIN_CARD, MARGIN_PAGE, MARGIN_CARD)
    body.setSpacing(SPACING_LG)
    return card, body


__all__ = ["create_card", "create_section", "create_section_header"]
