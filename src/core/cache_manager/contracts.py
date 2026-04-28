from __future__ import annotations

from typing import Any


class CacheManagerHost:
    """Typing bridge for CacheManager mixins."""

    SCHEMA_VERSION: int
    db_path: str
    _foi_has_id: bool | None

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)

