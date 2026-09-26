"""Metric card — promoted from the insights page local builder.

Title + large value + hint, on the standard ``folder_card`` surface.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from src.ui.design_system.tokens import MARGIN_CARD, MARGIN_PAGE, SPACING_SM


def create_metric_card(
    title: str,
    value_text: str = "0",
    hint: str = "",
    parent: QWidget | None = None,
) -> tuple[QFrame, QVBoxLayout, QLabel]:
    """Build a metric card and return (card, layout, value_label)."""
    card = QFrame(parent)
    card.setObjectName("folder_card")
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(MARGIN_PAGE, MARGIN_CARD, MARGIN_PAGE, MARGIN_CARD)
    layout.setSpacing(SPACING_SM)

    title_label = QLabel(title, card)
    title_label.setObjectName("card_desc")
    title_label.setWordWrap(True)
    layout.addWidget(title_label)

    value = QLabel(value_text, card)
    value.setObjectName("page_title")
    value.setWordWrap(True)
    layout.addWidget(value)

    if hint:
        hint_label = QLabel(hint, card)
        hint_label.setWordWrap(True)
        hint_label.setObjectName("card_desc")
        layout.addWidget(hint_label)

    return card, layout, value


__all__ = ["create_metric_card"]
