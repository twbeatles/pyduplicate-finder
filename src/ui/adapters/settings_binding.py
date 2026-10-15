"""QSettings 키 바인딩 (경로 B).

조직/앱 식별자 ``("MySoft", "PyDuplicateFinderPro")`` 와 기존 키 호환성을
고정한다. 마이그레이션은 빠진 키에 기본값을 채우는 것만 수행하고,
기존 값을 초기화·제거하지 않는다.
"""

from __future__ import annotations

from typing import Any

ORG_NAME = "MySoft"
APP_NAME = "PyDuplicateFinderPro"

KEY_THEME = "app/theme"
KEY_FOLLOW_SYSTEM = "app/follow_system_theme"
KEY_DENSITY = "app/density"
KEY_LANGUAGE = "app/language"

#: 본 바인딩이 소유하는 키와 기본값. 이 외의 키는 건드리지 않는다.
DEFAULTS: dict[str, Any] = {
    KEY_THEME: "light",
    KEY_FOLLOW_SYSTEM: True,
    KEY_DENSITY: "comfortable",
    KEY_LANGUAGE: "ko",
}


def read_setting(settings: Any, key: str, default: Any = None) -> Any:
    try:
        value = settings.value(key, default)
        return default if value is None else value
    except Exception:
        return default


def write_setting(settings: Any, key: str, value: Any) -> None:
    settings.setValue(key, value)


def migrate_settings(settings: Any) -> dict[str, Any]:
    """빠진 소유 키에 기본값을 채우고, 채운 항목만 반환한다.

    기존 값은 절대 덮어쓰지 않는다. ``settings`` 가 없어도 예외를 내지 않는다.
    """
    added: dict[str, Any] = {}
    if settings is None:
        return added
    for key, default in DEFAULTS.items():
        try:
            if settings.value(key, None) is None:
                settings.setValue(key, default)
                added[key] = default
        except Exception:
            continue
    return added


__all__ = [
    "APP_NAME",
    "DEFAULTS",
    "KEY_DENSITY",
    "KEY_FOLLOW_SYSTEM",
    "KEY_LANGUAGE",
    "KEY_THEME",
    "ORG_NAME",
    "migrate_settings",
    "read_setting",
    "write_setting",
]
