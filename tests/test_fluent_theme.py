"""Regression tests for the Fluent redesign (pure-PySide6 WinUI port)."""

from __future__ import annotations

from contextlib import suppress

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.design_system import fluent
from src.ui.design_system.components.info_bar import InfoBar, create_info_bar
from src.ui.theme import ModernTheme
from src.utils.i18n import strings


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_fluent_token_tables_cover_both_modes():
    for mode in ("light", "dark"):
        accent = fluent.accent_for(mode)
        assert {"rest", "hover", "pressed", "subtle_fill", "focus_ring"} <= set(accent)
        surface = fluent.surface_for(mode)
        assert {"nav_hover", "nav_selected", "stroke"} <= set(surface)
        for severity in fluent.VALID_SEVERITIES:
            colors = fluent.info_colors(severity, mode)
            assert {"bg", "border", "fg", "icon"} <= set(colors)
            assert colors["bg"] != colors["fg"]


def test_fluent_normalization_fallbacks():
    assert fluent.normalize_mode("dark") == "dark"
    assert fluent.normalize_mode("DARK") == "dark"
    assert fluent.normalize_mode("bogus") == "light"
    assert fluent.normalize_mode(None) == "light"
    assert fluent.info_colors("bogus", "light") == fluent.info_colors("info", "light")
    assert fluent.accent_for("bogus") == fluent.accent_for("light")


def test_apply_fluent_button_tags_kind(qapp):
    from PySide6.QtWidgets import QPushButton

    btn = QPushButton("x")
    fluent.apply_fluent_button(btn, "accent")
    assert btn.property("fluent_button") is True
    assert btn.property("fluent_kind") == "accent"
    fluent.apply_fluent_button(btn, "bogus")
    assert btn.property("fluent_kind") == "standard"


def test_fluent_fragment_selectors_and_token_scale():
    for mode, accent in (("light", "#0F6CBD"), ("dark", "#4CC2FF")):
        frag = fluent.build_fluent_fragment(mode)
        assert accent in frag
        assert 'QPushButton[fluent_kind="accent"]' in frag
        assert 'QFrame#InfoBar[severity="warning"]' in frag
        assert 'QFrame#InfoBar[severity="error"]' in frag
        assert "QPushButton#InfoBarClose" in frag
    # Shared token-scale guard also holds for the Fluent fragment.
    assert "border-radius: 4px" not in fluent.build_fluent_fragment("light")
    assert "border-radius: 5px" not in fluent.build_fluent_fragment("dark")
    assert "border-radius: 10px" not in fluent.build_fluent_fragment("light")


def test_stylesheet_embeds_fluent_fragment():
    light = ModernTheme.get_stylesheet("light")
    dark = ModernTheme.get_stylesheet("dark")
    assert "FLUENT: INFOBAR" in light
    assert "#0F6CBD" in light
    assert "#4CC2FF" in dark
    compact = ModernTheme.get_stylesheet("light", density="compact")
    assert "DENSITY: COMPACT" in compact
    assert "FLUENT: INFOBAR" in compact


def test_info_bar_lifecycle(qapp):
    bar = create_info_bar("warning", "Title", "Body")
    try:
        assert bar.objectName() == "InfoBar"
        assert not bar.isVisible()
        assert bar.severity == "warning"
        assert bar.title_label.text() == "Title"
        assert bar.message_label.text() == "Body"
        closed: list[bool] = []
        bar.closed.connect(lambda: closed.append(True))
        bar.show_notice("error", "E", "boom")
        assert bar.severity == "error"
        assert bar.isVisible()
        assert bar.property("severity") == "error"
        bar.dismiss()
        assert not bar.isVisible()
        assert closed == [True]
    finally:
        bar.close()


def test_info_bar_severity_fallback_and_mode(qapp):
    bar = InfoBar(severity="bogus", mode="dark")
    try:
        assert bar.severity == "info"
        assert "color:" in bar.message_label.styleSheet()
        bar.set_severity("bogus")
        assert bar.severity == "info"
        bar.apply_mode("dark")
        dark_style = bar.message_label.styleSheet()
        bar.apply_mode("light")
        assert bar.message_label.styleSheet() != dark_style
        bar.retranslate()
        assert bar.close_button.toolTip() == strings.tr("infobar_close")
    finally:
        bar.close()


def test_infobar_close_i18n():
    strings.set_language("ko")
    assert strings.tr("infobar_close") == "알림 닫기"
    strings.set_language("en")
    assert strings.tr("infobar_close") == "Close notification"
    strings.set_language("ko")


def test_sidebar_fluent_pill(qapp):
    from src.ui.components.sidebar import Sidebar

    sidebar = Sidebar()
    try:
        sidebar.apply_theme("light")
        assert sidebar.buttons["scan"]._accent_pill == fluent.accent_for("light")["rest"]
        sidebar.apply_theme("dark")
        assert sidebar.buttons["scan"]._accent_pill == fluent.accent_for("dark")["rest"]
    finally:
        sidebar.close()


def test_toast_fluent_colors(qapp):
    from PySide6.QtWidgets import QWidget

    from src.ui.components.toast import ToastManager, ToastNotification

    toast = ToastNotification("hello", "warning", parent=None)
    try:
        expected = fluent.info_colors("warning", "light")
        assert toast.style_config["bg"] == expected["bg"]
        assert toast.style_config["fg"] == expected["fg"]
    finally:
        toast.close()
    host = QWidget()
    try:
        mgr = ToastManager(parent=host)
        mgr.set_theme_mode("dark")
        assert mgr.theme_mode == "dark"
        mgr.set_theme_mode("bogus")
        assert mgr.theme_mode == "light"
    finally:
        host.close()


def test_main_window_fluent_wiring(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("PYDUPLICATEFINDER_DB_PATH", str(tmp_path / "scan_cache.db"))
    from src.ui.main_window import DuplicateFinderApp

    w = DuplicateFinderApp()
    try:
        with suppress(Exception):
            w._scheduler_timer.stop()
        assert w.lbl_scan_title.text() == strings.tr("nav_scan")
        assert w.scan_notice_bar.isHidden()
        w.scan_notice_bar.show_notice("warning", "T", "M")
        assert not w.scan_notice_bar.isHidden()
        w.apply_theme("dark")
        w.scan_notice_bar.dismiss()
        assert w.scan_notice_bar.isHidden()
        assert "FLUENT: INFOBAR" in w.styleSheet()
    finally:
        w.close()


def test_spec_registers_fluent_modules():
    import pathlib

    spec = pathlib.Path(__file__).resolve().parent.parent / "PyDuplicateFinder.spec"
    text = spec.read_text(encoding="utf-8")
    assert "src.ui.design_system.fluent" in text
    assert "src.ui.design_system.components.info_bar" in text
