"""Regression tests for the shared UI design system (srtgo port)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QFrame

from src.ui.design_system import tokens
from src.ui.design_system.components import (
    create_empty_state,
    create_filter_row,
    create_hseparator,
    create_page_header,
    create_section,
    create_section_header,
    create_status_row,
    create_vseparator,
)
from src.ui.design_system.layouts import (
    apply_page_margins,
    create_master_detail,
    create_scroll_with_action_bar,
)
from src.ui.theme import ModernTheme


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_font_scale_is_strictly_increasing():
    sizes = [int(v) for v in tokens.FONT_SCALE_PTS]
    assert sizes == sorted(sizes)
    assert len(set(sizes)) == len(sizes)


def test_stylesheet_font_hierarchy_restored():
    base = int(ModernTheme.FONT_SIZE_BASE.replace("pt", ""))
    md = int(ModernTheme.FONT_SIZE_MD.replace("pt", ""))
    lg = int(ModernTheme.FONT_SIZE_LG.replace("pt", ""))
    assert base < md <= lg


def test_density_presets_share_keys():
    assert set(tokens.DENSITY_COMPACT) == set(tokens.DENSITY_COMFORTABLE)
    assert tokens.DENSITY_COMPACT["row_height"] <= tokens.DENSITY_COMFORTABLE["row_height"]


def test_separators(qapp):
    v = create_vseparator()
    h = create_hseparator()
    assert isinstance(v, QFrame)
    assert v.frameShape() == QFrame.Shape.VLine
    assert h.frameShape() == QFrame.Shape.HLine


def test_section_card(qapp):
    group, body = create_section("Advanced")
    assert group.title() == "Advanced"
    assert body.count() == 0


def test_section_header_hint(qapp):
    _wrap, _row, hint = create_section_header("Title", "hint text")
    assert hint.text() == "hint text"


def test_page_header_and_filter_row(qapp):
    _wrap, row, title = create_page_header("Results")
    assert title.text() == "Results"
    assert row.count() >= 2  # title + stretch
    filter_row = create_filter_row()
    assert filter_row.count() == 0


def test_empty_state_and_status_row(qapp):
    _wrap, label = create_empty_state("No results", icon="X")
    assert "No results" in label.text()
    _wrap2, _row, status = create_status_row()
    assert status.objectName() == "stage_badge"


def test_layout_helpers(qapp):
    splitter, master, detail = create_master_detail()
    assert splitter.indexOf(master) == 0
    assert splitter.indexOf(detail) == 1
    body, body_layout, scroll, _bar, _row = create_scroll_with_action_bar()
    assert scroll.widgetResizable()
    apply_page_margins(body_layout)
    assert body_layout.contentsMargins().left() == tokens.MARGIN_PAGE
    assert body is not None


def test_scan_page_separator_delegates_to_shared(qapp):
    from src.ui.pages import scan_page

    sep = scan_page._create_separator()
    assert isinstance(sep, QFrame)
    assert sep.frameShape() == QFrame.Shape.VLine


def test_density_stylesheet_overrides():
    comfortable = ModernTheme.get_stylesheet("light")
    compact = ModernTheme.get_stylesheet("light", density="compact")
    assert "DENSITY: COMPACT" not in comfortable
    assert "DENSITY: COMPACT" in compact
    assert "QTreeWidget::item" in compact
    # Backward-compatible default.
    assert ModernTheme.get_stylesheet("dark") == ModernTheme.get_stylesheet("dark", density="comfortable")


def test_system_theme_helpers():
    from src.ui.design_system.system_theme import (
        normalize_bool,
        resolve_startup_theme,
        system_theme,
    )

    assert system_theme() in ("dark", "light")
    assert normalize_bool(True) is True
    assert normalize_bool("false", True) is False
    assert normalize_bool(None, False) is False

    class _FakeSettings:
        def __init__(self, values):
            self._values = dict(values)

        def value(self, key, default=None):
            return self._values.get(key, default)

        def setValue(self, key, value):
            self._values[key] = value

    follow = _FakeSettings({"app/follow_system_theme": True})
    assert resolve_startup_theme(follow) == system_theme()
    pinned = _FakeSettings({"app/follow_system_theme": False, "app/theme": "dark"})
    assert resolve_startup_theme(pinned) == "dark"


def test_system_theme_watcher_lifecycle(qapp):
    from src.ui.design_system.system_theme import SystemThemeWatcher

    watcher = SystemThemeWatcher()
    watcher.start()
    watcher.stop()


def test_metric_card_and_create_card(qapp):
    from src.ui.design_system.components import create_card, create_metric_card

    card, _layout, value = create_metric_card("Scans", "7", "hint")
    assert card.objectName() == "folder_card"
    assert value.text() == "7"

    plain, body = create_card()
    assert plain.objectName() == "folder_card"
    assert body.count() == 0


def test_density_switch_emits(qapp):
    from src.ui.design_system.components import COMFORTABLE, COMPACT, DensitySwitch

    received: list[str] = []
    switch = DensitySwitch(current=COMFORTABLE)
    switch.density_changed.connect(received.append)
    assert switch.current_density() == COMFORTABLE
    switch._select(COMPACT)
    assert received == [COMPACT]
    assert switch.current_density() == COMPACT
    switch.set_density("bogus")
    assert switch.current_density() == COMFORTABLE


def test_main_window_density_flow(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("PYDUPLICATEFINDER_DB_PATH", str(tmp_path / "scan_cache.db"))
    from src.ui.main_window import DuplicateFinderApp

    w = DuplicateFinderApp()
    try:
        try:
            w._scheduler_timer.stop()
        except Exception:
            pass
        assert hasattr(w, "density_switch")
        assert hasattr(w, "chk_follow_system_theme")
        w.apply_density("compact")
        assert w.settings.value("app/density") == "compact"
        assert "DENSITY: COMPACT" in w.styleSheet()
        w.apply_density("comfortable")
        assert "DENSITY: COMPACT" not in w.styleSheet()
    finally:
        w.close()
