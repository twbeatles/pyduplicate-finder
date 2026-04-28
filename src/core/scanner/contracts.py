from __future__ import annotations

from typing import Any


class ScanWorkerHost:
    """Typing bridge for ScanWorker mixins."""

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)

