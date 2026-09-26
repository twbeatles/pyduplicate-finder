"""Metric card — promoted from the insights page local builder.

Title + large value + hint, on the standard ``folder_card`` surface.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from src.ui.design_system.tokens import SPACING_SM


def create_metric_card(
    title: str,
    value_text: str = "0",
    hint: str = "",
    parent: QWidget | None = None,
) -> tuple[QFrame, QVBoxLayout, QLabel]:
    """Build a metric card and return (card, layout, value_label)."""
    card = QFrame(parent)
    card.setObjectName("folder_card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(SPACING_SM)

    title_label = QLabel(title, card)
    title_label.setObjectName("card_desc")
    layout.addWidget(title_label)

    value = QLabel(value_text, card)
    value.setObjectName("page_title")
    layout.addWidget(value)

    if hint:
        hint_label = QLabel(hint, card)
        hint_label.setWordWrap(True)
        hint_label.setObjectName("card_desc")
        layout.addWidget(hint_label)

    return card, layout, value


__all__ = ["create_metric_card"]
