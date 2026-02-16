import os
import sqlite3

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


def test_update_cache_batch_preserves_existing_hashes(tmp_path):
    db_path = tmp_path / "scan_cache.db"
    cm = CacheManager(db_path=str(db_path))
    try:
        cm.update_cache_batch([("a.txt", 10, 1.0, "partial_a", None)])
        cm.update_cache_batch([("a.txt", 10, 1.0, None, "full_a")])
        row = cm.get_cached_hash("a.txt", 10, 1.0)
        assert row == ("partial_a", "full_a")
    finally:
        try:
            cm.close_all()
        except Exception:
            pass


def test_schema_version_migrates_to_v3(tmp_path):
    db_path = tmp_path / "scan_cache.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', '2')")
        conn.commit()
    finally:
        conn.close()

    cm = CacheManager(db_path=str(db_path))
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            assert row is not None
            assert str(row[0]) == "3"
        finally:
            conn.close()
    finally:
        try:
            cm.close_all()
        except Exception:
            pass


def test_save_selected_paths_delta_upsert_and_delete(tmp_path):
    db_path = tmp_path / "scan_cache.db"
    cm = CacheManager(db_path=str(db_path))
    try:
        sid = cm.create_scan_session({"folders": ["x"]})
        assert sid > 0
        cm.save_selected_paths_delta(sid, add_paths=["a", "b"], remove_paths=[])
        assert cm.load_selected_paths(sid) == {"a", "b"}
        cm.save_selected_paths_delta(sid, add_paths=["c"], remove_paths=["a"])
        assert cm.load_selected_paths(sid) == {"b", "c"}
    finally:
        try:
            cm.close_all()
        except Exception:
            pass
