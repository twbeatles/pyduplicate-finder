from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

from .models import NativeHashResult

logger = logging.getLogger(__name__)

_pydup_core = None
try:
    import pydup_core as _pydup_core
except ImportError:
    _pydup_core = None


class RustCoreUnavailable(RuntimeError):
    pass


class RustCancellationToken:
    """Wrapper around Rust CancellationToken with fallback support."""

    def __init__(self) -> None:
        if _pydup_core is not None and hasattr(_pydup_core, "CancellationToken"):
            self._native = _pydup_core.CancellationToken()
        else:
            self._native = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        if self._native is not None:
            self._native.cancel()

    def is_cancelled(self) -> bool:
        if self._native is not None:
            return bool(self._native.is_cancelled())
        return self._cancelled

    def reset(self) -> None:
        self._cancelled = False
        if self._native is not None:
            self._native.reset()

    @property
    def native(self):
        return self._native


def is_rust_available() -> bool:
    """Check whether native Rust extension pydup_core is compiled and loadable."""
    if _pydup_core is None:
        return False
    try:
        return bool(_pydup_core.is_available())
    except Exception:
        return False


def get_backend_name(requested_backend: str = "auto") -> str:
    """Resolve effective backend ("rust" or "python")."""
    env_backend = os.environ.get("PYDUP_SCAN_BACKEND", "").strip().lower()
    pref = env_backend or requested_backend or "auto"
    if pref == "rust":
        if not is_rust_available():
            raise RustCoreUnavailable("Rust scan backend requested, but pydup_core is not available.")
        return "rust"
    if pref == "python":
        return "python"
    return "rust" if is_rust_available() else "python"


def hash_file(
    filepath: str,
    partial: bool = False,
    size: Optional[int] = None,
    block_size: Optional[int] = None,
    cancel_token: Optional[RustCancellationToken] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Hash single file using Rust core."""
    if not is_rust_available() or _pydup_core is None:
        raise RustCoreUnavailable("pydup_core is unavailable")

    native_token = cancel_token.native if cancel_token else None
    digest, err = _pydup_core.hash_file(
        filepath,
        partial=bool(partial),
        size=int(size) if size is not None else None,
        block_size=int(block_size) if block_size is not None else None,
        cancel_token=native_token,
    )
    return digest, err


def hash_files_batch(
    items: List[Tuple[str, int, float]],
    partial: bool = False,
    max_workers: Optional[int] = None,
    cancel_token: Optional[RustCancellationToken] = None,
) -> List[NativeHashResult]:
    """Calculate BLAKE2b hashes for multiple files in parallel using Rust Rayon pool."""
    if not is_rust_available() or _pydup_core is None:
        raise RustCoreUnavailable("pydup_core is unavailable")

    if not items:
        return []

    native_token = cancel_token.native if cancel_token else None
    results = _pydup_core.hash_files_batch(
        items,
        partial=bool(partial),
        max_workers=int(max_workers) if max_workers is not None else None,
        cancel_token=native_token,
    )

    out: List[NativeHashResult] = []
    for r in results:
        out.append(
            NativeHashResult(
                path=str(getattr(r, "path", "")),
                size=int(getattr(r, "size", 0)),
                mtime=float(getattr(r, "mtime", 0.0)),
                digest=getattr(r, "digest", None),
                status=str(getattr(r, "status", "ok")),
                error=getattr(r, "error", None),
            )
        )
    return out


def compare_files_byte_by_byte(
    path_a: str,
    path_b: str,
    cancel_token: Optional[RustCancellationToken] = None,
) -> bool:
    """Compare two files byte-by-byte using Rust 1 MiB streaming buffer."""
    if not is_rust_available() or _pydup_core is None:
        raise RustCoreUnavailable("pydup_core is unavailable")

    native_token = cancel_token.native if cancel_token else None
    return bool(_pydup_core.files_equal(path_a, path_b, cancel_token=native_token))


def discover_files(
    folders: List[str],
    extensions: Optional[List[str]] = None,
    min_size: int = 0,
    skip_hidden: bool = False,
    follow_symlinks: bool = False,
    protect_system: bool = True,
    protected_paths: Optional[List[str]] = None,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    cancel_token: Optional[RustCancellationToken] = None,
):
    """Discover files recursively using native Rust filesystem traversal."""
    if not is_rust_available() or _pydup_core is None:
        raise RustCoreUnavailable("pydup_core is unavailable")

    native_token = cancel_token.native if cancel_token else None
    return _pydup_core.discover_files(
        [str(f) for f in folders],
        extensions=[str(e) for e in extensions] if extensions else None,
        min_size=max(0, int(min_size or 0)),
        skip_hidden=bool(skip_hidden),
        follow_symlinks=bool(follow_symlinks),
        protect_system=bool(protect_system),
        protected_paths=[str(p) for p in (protected_paths or [])],
        include_patterns=[str(p) for p in (include_patterns or [])],
        exclude_patterns=[str(p) for p in (exclude_patterns or [])],
        cancel_token=native_token,
    )
