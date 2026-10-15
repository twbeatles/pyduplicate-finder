"""설정 바인딩·테마 상태 관리자 테스트 (경로 B, Phase 1).

- 조직/앱 ID 고정, 기존 값 초기화·덮어쓰기 금지
- 빠진 키만 기본값으로 채움 (False 같은 유효값 보존)
- 테마/밀도/추종 round-trip + 잘못된 값 clamp
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from src.ui.adapters.settings_binding import (
    APP_NAME,
    DEFAULTS,
    KEY_DENSITY,
    KEY_FOLLOW_SYSTEM,
    KEY_LANGUAGE,
    KEY_THEME,
    ORG_NAME,
    migrate_settings,
    read_setting,
    write_setting,
)
from src.ui.theme.fluent_theme import FluentThemeManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def ini_settings(tmp_path):
    return QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat)


def test_org_and_app_identity(qapp):
    assert ORG_NAME == "MySoft"
    assert APP_NAME == "PyDuplicateFinderPro"


def test_migrate_fills_only_missing_keys(ini_settings):
    write_setting(ini_settings, KEY_THEME, "dark")
    write_setting(ini_settings, KEY_FOLLOW_SYSTEM, False)
    added = migrate_settings(ini_settings)
    assert KEY_THEME not in added
    assert KEY_FOLLOW_SYSTEM not in added
    assert added[KEY_DENSITY] == DEFAULTS[KEY_DENSITY]
    assert added[KEY_LANGUAGE] == DEFAULTS[KEY_LANGUAGE]
    # 기존 값은 그대로 보존된다.
    assert read_setting(ini_settings, KEY_THEME, None) == "dark"
    assert read_setting(ini_settings, KEY_FOLLOW_SYSTEM, None) is False


def test_migrate_on_empty_settings_adds_all_defaults(ini_settings):
    added = migrate_settings(ini_settings)
    assert added == dict(DEFAULTS)


def test_migrate_tolerates_missing_settings_object():
    assert migrate_settings(None) == {}


def test_theme_manager_round_trip(ini_settings):
    manager = FluentThemeManager(ini_settings)
    assert manager.set_mode("dark") == "dark"
    assert manager.current_mode() == "dark"
    assert manager.set_density("compact") == "compact"
    assert manager.density() == "compact"
    assert manager.set_follow_system(False) is False
    assert manager.follow_system() is False


def test_theme_manager_clamps_invalid_values(ini_settings):
    manager = FluentThemeManager(ini_settings)
    assert manager.set_mode("neon") == "light"
    assert manager.set_density("wide") == "comfortable"


def test_startup_mode_prefers_stored_when_not_following(ini_settings):
    write_setting(ini_settings, KEY_FOLLOW_SYSTEM, False)
    write_setting(ini_settings, KEY_THEME, "dark")
    assert FluentThemeManager(ini_settings).startup_mode() == "dark"
