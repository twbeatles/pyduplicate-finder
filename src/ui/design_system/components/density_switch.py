"""Segmented density switch (srtgo rail-toggle pattern on pure PySide6).

Two exclusive options — Comfortable vs Compact — rendered with the existing
``btn_primary`` (selected) / ``btn_secondary`` (unselected) roles so the
control stays theme-aware without hardcoded QSS.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from src.ui.design_system.tokens import SPACING_MD
from src.utils.i18n import strings

COMFORTABLE = "comfortable"
COMPACT = "compact"
PRESETS = (COMFORTABLE, COMPACT)


class DensitySwitch(QWidget):
    """Two-button segmented control emitting ``density_changed``."""

    density_changed = Signal(str)

    def __init__(self, current: str = COMFORTABLE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING_MD)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for preset in PRESETS:
            btn = QPushButton(self._label(preset), self)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, p=preset: self._select(p))
            self._group.addButton(btn)
            self._buttons[preset] = btn
            row.addWidget(btn)
        row.addStretch()
        self.set_density(current)

    @staticmethod
    def _label(preset: str) -> str:
        if preset == COMPACT:
            return strings.tr("opt_density_compact")
        return strings.tr("opt_density_comfortable")

    def _select(self, preset: str) -> None:
        self.set_density(preset)
        self.density_changed.emit(preset)

    def set_density(self, preset: str) -> None:
        """Reflect ``preset`` visually without emitting (programmatic sync)."""
        if preset not in PRESETS:
            preset = COMFORTABLE
        for key, btn in self._buttons.items():
            selected = key == preset
            btn.blockSignals(True)
            btn.setChecked(selected)
            btn.blockSignals(False)
            btn.setObjectName("btn_primary" if selected else "btn_secondary")
            style = btn.style()
            if style is not None:
                try:
                    style.unpolish(btn)
                    style.polish(btn)
                except Exception:
                    pass

    def current_density(self) -> str:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return COMFORTABLE

    def retranslate(self) -> None:
        for key, btn in self._buttons.items():
            btn.setText(self._label(key))


__all__ = ["COMFORTABLE", "COMPACT", "PRESETS", "DensitySwitch"]
