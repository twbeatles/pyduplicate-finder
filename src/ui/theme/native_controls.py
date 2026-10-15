"""네이티브 Qt 위젯 최소 보정 (경로 B).

KTrain ``apply_native_widget_style`` 과 같은 위치의 대책이다:
다크 모드에서 기본 ``QTreeWidget`` / ``QTableWidget`` / ``QHeaderView`` /
``QCheckBox`` 의 가독성만 보정하고, 라이트 모드에서는 플랫폼 기본을 쓴다.
광역 ``ModernTheme`` QSS와 중복 적용하지 않으며, 대상 위젯에만
``setStyleSheet`` 로 직접 적용하는 것을 전제로 문자열만 제공한다.
"""

from __future__ import annotations

from src.ui.design_system.tokens import (
    DARK_BG,
    DARK_BORDER,
    DARK_HEADER_BG,
    DARK_SELECTED_ROW,
    DARK_TEXT,
)


def native_tree_table_qss(mode: str = "light") -> str:
    """다크 모드용 최소 보정 QSS. 라이트 모드에서는 빈 문자열을 반환한다."""
    if str(mode or "light").lower() != "dark":
        return ""
    return f"""
        QTreeWidget, QTableWidget {{
            color: {DARK_TEXT};
            background-color: {DARK_BG};
            gridline-color: {DARK_BORDER};
        }}
        QTreeWidget::item:selected, QTableWidget::item:selected {{
            background-color: {DARK_SELECTED_ROW};
        }}
        QHeaderView::section {{
            color: {DARK_TEXT};
            background-color: {DARK_HEADER_BG};
            border: none;
        }}
        QCheckBox, QLabel {{
            color: {DARK_TEXT};
        }}
        QCheckBox::indicator {{
            width: 15px;
            height: 15px;
            border: 1px solid #8A8A8A;
            border-radius: 3px;
            background-color: {DARK_BG};
        }}
        QCheckBox::indicator:checked {{
            border-color: #4CC2FF;
            background-color: #4CC2FF;
        }}
        QCheckBox::indicator:disabled {{
            border-color: #4A4A4A;
            background-color: #252525;
        }}
    """


def apply_native_controls(widget, mode: str = "light") -> None:
    """대상 위젯에만 보정 QSS를 적용한다 (이미 있으면 덧붙이지 않는다)."""
    try:
        current = widget.styleSheet() or ""
        if "QHeaderView::section" in current:
            return
        fragment = native_tree_table_qss(mode)
        if fragment:
            widget.setStyleSheet(current + fragment)
    except Exception:
        pass


__all__ = ["apply_native_controls", "native_tree_table_qss"]
