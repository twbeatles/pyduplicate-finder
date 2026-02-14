import os

from src.core.cache_manager import CacheManager


def test_cache_manager_uses_user_writable_absolute_path(monkeypatch):
    monkeypatch.delenv("PYDUPLICATEFINDER_DB_PATH", raising=False)
    cm = CacheManager(db_path=None)
    try:
        assert os.path.isabs(cm.db_path)
        assert os.path.basename(cm.db_path) == "scan_cache.db"
        # Should not default to CWD (fragile after packaging).
        assert os.path.abspath(os.path.dirname(cm.db_path)) != os.path.abspath(os.getcwd())
    finally:
        try:
            cm.close_all()
        except Exception:
            pass

