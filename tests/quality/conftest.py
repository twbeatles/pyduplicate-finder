"""Shared fixtures for tests/quality: isolated roots, DB isolation, worker factory."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.quality.safety import assert_inside_root  # noqa: E402


@pytest.fixture()
def quality_root(tmp_path, monkeypatch):
    """Fresh isolated test root; ScanWorker DB redirected inside it.

    ScanWorker builds its own CacheManager which honours
    PYDUPLICATEFINDER_DB_PATH, so point that at the isolated root to avoid
    touching the real user cache.
    """
    root = tmp_path / "quality_case"
    root.mkdir(parents=True, exist_ok=True)
    data = root / "data"
    data.mkdir(exist_ok=True)
    monkeypatch.setenv("PYDUPLICATEFINDER_DB_PATH", str(root / "scan_cache.db"))
    yield root
    # tmp_path cleanup is automatic; nothing outside the root is ever touched.


@pytest.fixture()
def worker_factory():
    """Create ScanWorker instances bound to folders inside the test root."""
    workers = []

    def _make(folders, root: Path, **kwargs):
        from src.core.scanner import ScanWorker

        for f in folders:
            assert_inside_root(f, str(root))
        kwargs.setdefault("max_workers", 2)
        # Never let quality scans escape the harness via symlink following.
        kwargs.setdefault("follow_symlinks", False)
        w = ScanWorker([str(f) for f in folders], **kwargs)
        workers.append(w)
        return w

    yield _make

    for w in workers:
        try:
            w.cache_manager.close_all()
        except Exception:
            pass


@pytest.fixture()
def quarantine_pair(tmp_path):
    """Isolated (CacheManager, QuarantineManager, quarantine_dir) triple."""
    from src.core.cache_manager import CacheManager
    from src.core.quarantine_manager import QuarantineManager

    root = tmp_path / "qcase"
    root.mkdir(parents=True, exist_ok=True)
    qdir = root / "quarantine"
    qdir.mkdir(exist_ok=True)
    cache = CacheManager(db_path=str(root / "scan_cache.db"))
    qm = QuarantineManager(cache, quarantine_dir=str(qdir))
    yield {"root": root, "cache": cache, "qm": qm, "qdir": qdir}
    try:
        cache.close_all()
    except Exception:
        pass
