"""단일 테마 상태 관리자 (경로 B).

``app/theme`` + ``app/follow_system_theme`` + ``app/density`` 키를 한 곳에서
다루며, 실제 QSS 생성·OS 감시는 기존 ``ModernTheme`` /
``design_system.system_theme`` 에 위임한다. 동작 변경 없이 계약만 고정한다.
"""

from __future__ import annotations

from typing import Any

from src.ui.adapters.settings_binding import (
    DEFAULTS,
    KEY_DENSITY,
    KEY_FOLLOW_SYSTEM,
    KEY_THEME,
    read_setting,
    write_setting,
)
from src.ui.design_system.system_theme import normalize_bool, resolve_startup_theme

VALID_THEMES = ("light", "dark")
VALID_DENSITIES = ("comfortable", "compact")


class FluentThemeManager:
    """QSettings 기반 테마·밀도 상태의 단일 소유자."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    def startup_mode(self) -> str:
        """시작 테마 (추종 켜짐 → OS, 꺼짐 → 저장값). 저장값을 초기화하지 않는다."""
        try:
            return resolve_startup_theme(self._settings)
        except Exception:
            return str(DEFAULTS[KEY_THEME])

    def current_mode(self) -> str:
        mode = read_setting(self._settings, KEY_THEME, DEFAULTS[KEY_THEME])
        return mode if mode in VALID_THEMES else str(DEFAULTS[KEY_THEME])

    def set_mode(self, mode: str) -> str:
        mode = mode if mode in VALID_THEMES else str(DEFAULTS[KEY_THEME])
        write_setting(self._settings, KEY_THEME, mode)
        return mode

    def follow_system(self) -> bool:
        return normalize_bool(
            read_setting(self._settings, KEY_FOLLOW_SYSTEM, DEFAULTS[KEY_FOLLOW_SYSTEM]),
            True,
        )

    def set_follow_system(self, enabled: bool) -> bool:
        write_setting(self._settings, KEY_FOLLOW_SYSTEM, bool(enabled))
        return bool(enabled)

    def density(self) -> str:
        preset = read_setting(self._settings, KEY_DENSITY, DEFAULTS[KEY_DENSITY])
        return preset if preset in VALID_DENSITIES else str(DEFAULTS[KEY_DENSITY])

    def set_density(self, preset: str) -> str:
        preset = preset if preset in VALID_DENSITIES else str(DEFAULTS[KEY_DENSITY])
        write_setting(self._settings, KEY_DENSITY, preset)
        return preset


__all__ = ["VALID_DENSITIES", "VALID_THEMES", "FluentThemeManager"]
