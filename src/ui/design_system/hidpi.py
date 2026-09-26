"""HiDPI helpers: app bootstrap + logical-pixel / font-relative sizing.

Qt6 scales logical pixels by the screen devicePixelRatio, but any size
derived from a hardcoded ``px`` constant chosen at 96 dpi still clips
larger fonts at 150-200% scale. Helpers here keep such sizes derived
from font metrics (so they grow with the scale factor) and snapped to
the 8pt grid defined in ``src.ui.design_system.tokens``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QWidget

_BASELINE_FONT_PX = 16.0  # approx. pixel height of the default 10pt font at 96 dpi.


def configure_high_dpi() -> None:
    """Enable HiDPI-safe application attributes (call before ``QApplication``)."""
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass


def ui_scale(widget: QWidget | None = None) -> float:
    """Scale factor of the active font vs the 96-dpi baseline (>= 1.0 logic)."""
    try:
        from PySide6.QtGui import QFontMetrics

        if widget is not None:
            height = float(widget.fontMetrics().height())
        else:
            app = QApplication.instance()
            if not isinstance(app, QApplication):
                return 1.0
            height = float(QFontMetrics(app.font()).height())
        if height <= 0:
            return 1.0
        return max(1.0, height / _BASELINE_FONT_PX)
    except Exception:
        return 1.0


def snap_to_grid(px: int, grid: int = 8) -> int:
    """Snap ``px`` to the design-system grid (8pt by default)."""
    try:
        return max(grid, int(round(float(px) / float(grid)) * grid))
    except Exception:
        return px


def scaled_px(px: int, widget: QWidget | None = None) -> int:
    """Scale a 96-dpi ``px`` constant by the font scale and snap to grid."""
    return snap_to_grid(round(float(px) * ui_scale(widget)))


def min_button_height(widget: QWidget | None = None, base: int = 32) -> int:
    """Font-relative minimum button height (never below ``base``)."""
    try:
        if widget is not None:
            needed = int(widget.fontMetrics().height() * 2.0 + 8)
        else:
            needed = base
        return snap_to_grid(max(base, needed), 4)
    except Exception:
        return base


def fit_column_to_header(table: QWidget, column: int, min_px: int) -> int:
    """Width for a fixed table column: ``min_px`` or header text + padding.

    Keeps translated/larger-font headers from clipping at high scale while
    never shrinking below the layout's designed minimum.
    """
    try:
        header_text = ""
        try:
            item = table.horizontalHeaderItem(column)  # type: ignore[attr-defined]
            if item is not None:
                header_text = str(item.text() or "")
        except Exception:
            header_text = ""
        fm = table.fontMetrics()
        needed = int(fm.horizontalAdvance(header_text)) + scaled_px(40, table)
        width = max(int(min_px), needed)
        try:
            table.setColumnWidth(column, width)  # type: ignore[attr-defined]
        except Exception:
            pass
        return width
    except Exception:
        return min_px


def scaled_preview_pixmap(pixmap: QPixmap, target: object, widget: QWidget) -> QPixmap:
    """Scale ``pixmap`` to ``target`` QSize honouring the screen pixel ratio.

    The returned pixmap carries ``devicePixelRatio`` so it stays sharp on
    HiDPI screens instead of rendering at 1x and upscaling blurred.
    """
    try:
        from PySide6.QtCore import QSize

        dpr = 1.0
        try:
            dpr = float(widget.devicePixelRatioF())
        except Exception:
            dpr = 1.0
        if dpr <= 0:
            dpr = 1.0
        size = target if isinstance(target, QSize) else QSize(400, 400)
        if size.width() <= 0 or size.height() <= 0:
            size = QSize(400, 400)
        hi = QSize(int(size.width() * dpr), int(size.height() * dpr))
        out = pixmap.scaled(
            hi,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        try:
            out.setDevicePixelRatio(dpr)
        except Exception:
            pass
        return out
    except Exception:
        return pixmap


__all__ = [
    "configure_high_dpi",
    "fit_column_to_header",
    "min_button_height",
    "scaled_preview_pixmap",
    "scaled_px",
    "snap_to_grid",
    "ui_scale",
]
