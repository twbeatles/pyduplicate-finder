from __future__ import annotations

from typing import ClassVar, Optional, Set

from .catalog_en import CATALOG_EN
from .catalog_ko import CATALOG_KO
from .catalogs import DEBUG_I18N


class I18n:
    _instance: Optional["I18n"] = None
    _missing_keys: Set[str] = set()

    current_lang: ClassVar[str] = "ko"
    translations: ClassVar[dict[str, dict[str, str]]] = {
        "en": CATALOG_EN,
        "ko": CATALOG_KO,
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(I18n, cls).__new__(cls)
            cls.current_lang = "ko"
        return cls._instance

    def set_language(self, lang_code):
        if lang_code in type(self).translations:
            type(self).current_lang = lang_code
        else:
            type(self).current_lang = "en"

    def tr(self, key):
        result = type(self).translations.get(type(self).current_lang, {}).get(key)
        if result is None:
            result = type(self).translations.get("en", {}).get(key)
        if result is None:
            if DEBUG_I18N and key not in I18n._missing_keys:
                I18n._missing_keys.add(key)
                print(f"[i18n] Missing translation key: '{key}' (lang={self.current_lang})")
            return f"[{key}]" if DEBUG_I18N else key
        return result

    @classmethod
    def get_missing_keys(cls):
        return cls._missing_keys.copy()


strings = I18n()
