from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class NativeHashResult:
    path: str
    size: int
    mtime: float
    digest: Optional[str]
    status: str  # "ok", "cancelled", "error"
    error: Optional[str] = None
