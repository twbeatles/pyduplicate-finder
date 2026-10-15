"""Fluent shell tests (Path A, Phase 1-3).

MSFluentWindow shell registers 5 interfaces and performs page switching,
theme round-trip, in-scan guard bypass (internal nav) and close path
equivalently to the legacy shell.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

qfluentwidgets = pytest.importorskip("qfluentwidgets")

from src.ui.shell.fluent_window import (
    INTERFACE_NAMES,
    FluentDuplicateFinderApp,
)
from src.ui.shell.navigation import ALL_PAGES, can_switch_page


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _setup_window(tmp_path, monkeypatch):
    monkeypatch.setenv("PYDUPLICATEFINDER_DB_PATH", str(tmp_path / "scan_cache.db"))
    w = FluentDuplicateFinderApp()
    try:
        w._scheduler_timer.stop()
    except Exception:
        pass
    return w


def test_fluent_shell_registers_five_interfaces(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        assert set(w._fluent_interfaces) == set(ALL_PAGES)
        for key, object_name in INTERFACE_NAMES.items():
            assert w._fluent_interfaces[key].objectName() == object_name
        assert w.minimumWidth() <= 640
        assert w.minimumHeight() <= 560
        # Legacy widget contract is also satisfied in the Fluent shell.
        assert hasattr(w, "btn_start_scan")
        assert hasattr(w, "tree_widget")
        assert hasattr(w, "status_label")
        assert hasattr(w, "progress_bar")
    finally:
        w.close()


def test_fluent_navigation_switches_pages(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        for page in ALL_PAGES:
            w._navigate_to(page)
            qapp.processEvents()
            assert w.stackedWidget.currentWidget() is w._fluent_interfaces[page]
    finally:
        w.close()


def test_fluent_internal_nav_bypasses_scan_guard(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        w.btn_stop_scan.setEnabled(True)  # simulate running scan
        assert can_switch_page("scan", "results", scan_running=True) is False
        # Internal moves (e.g. show results after scan) must not be blocked.
        w._navigate_to("results")
        qapp.processEvents()
        assert w.stackedWidget.currentWidget() is w._fluent_interfaces["results"]
    finally:
        w.btn_stop_scan.setEnabled(False)
        w.close()


def test_fluent_theme_round_trip(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        w.apply_theme("dark")
        assert w.settings.value("app/theme", "") == "dark"
        w.apply_theme("light")
        assert w.settings.value("app/theme", "") == "light"
    finally:
        w.close()


def _settle_orientation(qapp, w, timeout_ms=2000):
    """Poll until the splitter orientation stabilizes (async layout safe)."""
    import time

    from PySide6.QtCore import Qt

    from src.ui.shell.view_state import (
        needed_horizontal_width,
        orientation_for_width,
    )

    deadline = time.monotonic() + timeout_ms / 1000.0
    last = None
    stable = 0
    while time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
        qapp.processEvents()
        current = w.splitter.orientation()
        if current == last:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
            last = current
    width = w._fluent_interfaces["results"].width()
    want = orientation_for_width(width, needed_horizontal_width())
    expected = (
        Qt.Orientation.Horizontal if want == "horizontal" else Qt.Orientation.Vertical
    )
    return w.splitter.orientation(), expected, width


def test_fluent_results_splitter_is_responsive(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        w._navigate_to("results")
        w.resize(1100, 800)
        w.show()
        actual, expected, width = _settle_orientation(qapp, w)
        assert actual == expected, f"width={width}"
        w.resize(640, 800)
        actual, expected, width = _settle_orientation(qapp, w)
        assert actual == expected, f"width={width}"
        # 640px 창에서는 결과 폭이 필요폭(808)보다 항상 좁으므로 세로 배치여야 한다.
        from PySide6.QtCore import Qt

        assert actual == Qt.Orientation.Vertical
    finally:
        w.close()


def test_fluent_close_without_scan_accepts(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    w.show()
    qapp.processEvents()
    assert w.close() is True
