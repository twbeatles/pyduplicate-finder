import os
import sqlite3
import time

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


def test_schema_version_migrates_to_v5(tmp_path):
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
            assert str(row[0]) == "5"
            # Scheduler tables should be present in v4+.
            t1 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scan_jobs'"
            ).fetchone()
            t2 = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scan_job_runs'"
            ).fetchone()
            cols = conn.execute("PRAGMA table_info(file_operation_items)").fetchall()
            col_names = [str(c[1]) for c in cols]
            assert t1 is not None
            assert t2 is not None
            assert "id" in col_names
        finally:
            conn.close()
    finally:
        try:
            cm.close_all()
        except Exception:
            pass


def test_file_operation_items_legacy_schema_auto_migrates_and_preserves_rows(tmp_path):
    db_path = tmp_path / "scan_cache.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', '4')")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_operation_items (
                op_id INTEGER NOT NULL,
                path TEXT,
                action TEXT,
                result TEXT,
                detail TEXT,
                size INTEGER,
                mtime REAL,
                quarantine_path TEXT,
                created_at REAL NOT NULL,
                PRIMARY KEY (op_id, created_at, path)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO file_operation_items
            (op_id, path, action, result, detail, size, mtime, quarantine_path, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (7, "a.txt", "moved", "ok", "", 1, 1.0, "q/a", 1000.0),
        )
        conn.execute(
            """
            INSERT INTO file_operation_items
            (op_id, path, action, result, detail, size, mtime, quarantine_path, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (7, "b.txt", "moved", "ok", "", 2, 2.0, "q/b", 1001.0),
        )
        conn.commit()
    finally:
        conn.close()

    cm = CacheManager(db_path=str(db_path))
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            assert row is not None
            assert str(row[0]) == "5"
            cols = conn.execute("PRAGMA table_info(file_operation_items)").fetchall()
            col_names = [str(c[1]) for c in cols]
            assert "id" in col_names
            count = conn.execute("SELECT COUNT(*) FROM file_operation_items").fetchone()
            assert int(count[0] or 0) == 2
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


def test_cleanup_old_entries_returns_deleted_count(tmp_path):
    db_path = tmp_path / "scan_cache.db"
    cm = CacheManager(db_path=str(db_path))
    try:
        conn = cm._get_conn()
        now = time.time()
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash_partial, hash_full, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("old.bin", 1, 1.0, "p1", "f1", now - (40 * 24 * 60 * 60)),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash_partial, hash_full, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("new.bin", 2, 2.0, "p2", "f2", now),
            )

        deleted = cm.cleanup_old_entries(days_old=30)
        assert deleted == 1

        row = conn.execute("SELECT COUNT(*) FROM file_hashes").fetchone()
        assert int(row[0] or 0) == 1
        remain = conn.execute("SELECT path FROM file_hashes").fetchone()
        assert str(remain[0]) == "new.bin"
    finally:
        try:
            cm.close_all()
        except Exception:
            pass


def test_cleanup_old_sessions_respects_keep_latest(tmp_path):
    db_path = tmp_path / "scan_cache.db"
    cm = CacheManager(db_path=str(db_path))
    try:
        sid1 = cm.create_scan_session({"folders": ["a"]})
        cm.save_scan_files_batch(sid1, [("a1.bin", 1, 1.0)])
        time.sleep(0.01)
        sid2 = cm.create_scan_session({"folders": ["b"]})
        cm.save_scan_files_batch(sid2, [("b1.bin", 1, 1.0)])
        time.sleep(0.01)
        sid3 = cm.create_scan_session({"folders": ["c"]})
        cm.save_scan_files_batch(sid3, [("c1.bin", 1, 1.0)])

        cm.cleanup_old_sessions(keep_latest=2)

        conn = cm._get_conn()
        kept = conn.execute("SELECT id FROM scan_sessions ORDER BY updated_at DESC").fetchall()
        kept_ids = [int(r[0]) for r in kept]
        assert sid1 not in kept_ids
        assert sid2 in kept_ids
        assert sid3 in kept_ids

        old_file_row = conn.execute("SELECT COUNT(*) FROM scan_files WHERE session_id=?", (sid1,)).fetchone()
        assert int(old_file_row[0] or 0) == 0
    finally:
        try:
            cm.close_all()
        except Exception:
            pass
