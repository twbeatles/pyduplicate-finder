"""Qt 바인딩 진단 테스트 (경로 B, Phase 1).

제품 코드는 ``qfluentwidgets`` 를 import하지 않으므로, 본 테스트도
해당 패키지를 import하지 않고 메타데이터·소스 판별만 검증한다.
"""

from __future__ import annotations

from src.ui.qt_binding import (
    binding_from_source,
    inspect_qt_bindings,
    installed_conflicting_dists,
    is_pyside6_binding,
)


def test_binding_from_source():
    assert binding_from_source("from PySide6.QtCore import Qt") == "PySide6"
    assert binding_from_source("import PySide6") == "PySide6"
    assert binding_from_source("from PyQt6.QtWidgets import X") == "PyQt6"
    assert binding_from_source("from PyQt5 import X") == "PyQt5"
    assert binding_from_source("from PySide2 import X") == "PySide2"
    assert binding_from_source("import os") == "unknown"
    assert is_pyside6_binding("PySide6")
    assert not is_pyside6_binding("PyQt6")
    assert not is_pyside6_binding(None)


def test_no_conflicting_dists_in_clean_env():
    # 충돌 패키지가 없는 환경에서는 빈 튜플이다. 있으면 테스트가 아니라
    # 환경 문제이므로, 여기서는 타입 계약만 고정한다.
    result = installed_conflicting_dists()
    assert isinstance(result, tuple)


def test_inspect_qt_bindings_report_shape():
    report = inspect_qt_bindings()
    assert isinstance(report.ok, bool)
    assert isinstance(report.errors, tuple)
    # 현재 개발 venv에는 PySide6 에디션이 설치되어 있어도 정상이어야 한다.
    # (경로 B 제품 코드는 qfluentwidgets를 import하지 않는다)
    assert report.ok
    assert report.conflicting_dists == ()
    assert report.fluent_binding in (None, "PySide6")
