from __future__ import annotations

import os
import platform
import sqlite3
import threading
from typing import Optional


class CacheDatabaseMixin:
    def __init__(self, db_path=None):
        override = os.environ.get("PYDUPLICATEFINDER_DB_PATH")
        using_custom = bool(db_path or override)
        resolved = db_path or override or self._default_db_path()

        if not using_custom:
            self._migrate_legacy_db_if_needed(resolved)

        self.db_path = resolved
        try:
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
        except Exception:
            pass
        self._local = threading.local()
        self._connections_lock = threading.Lock()
        self._connections = []
        self._foi_has_id: Optional[bool] = None
        self._init_db()

    @staticmethod
    def _migrate_legacy_db_if_needed(target_path: str) -> None:
        legacy_path = os.path.abspath(os.path.join(os.getcwd(), "scan_cache.db"))
        target_abs = os.path.abspath(target_path)
        if legacy_path == target_abs:
            return
        if not os.path.exists(legacy_path):
            return
        if os.path.exists(target_abs):
            return

        try:
            os.makedirs(os.path.dirname(target_abs), exist_ok=True)
            with sqlite3.connect(legacy_path, check_same_thread=False) as src:
                with sqlite3.connect(target_abs, check_same_thread=False) as dst:
                    src.backup(dst)
        except Exception:
            return

    @staticmethod
    def _default_db_path() -> str:
        override = os.environ.get("PYDUPLICATEFINDER_DB_PATH")
        if override:
            os.makedirs(os.path.dirname(os.path.abspath(override)), exist_ok=True)
            return override

        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
            base = os.path.join(base, "PyDuplicateFinderPro")
        elif platform.system() == "Darwin":
            base = os.path.join(os.path.expanduser("~"), "Library", "Caches", "PyDuplicateFinderPro")
        else:
            base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
            base = os.path.join(base, "pyduplicatefinderpro")

        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "scan_cache.db")

    def _get_conn(self):
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA cache_size=-64000;")
            self._local.conn = conn
            with self._connections_lock:
                try:
                    self._connections.append(conn)
                except Exception:
                    pass
        return self._local.conn

    @staticmethod
    def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
        try:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table_name})")
            return [str(row[1]) for row in (cur.fetchall() or []) if len(row) > 1]
        except Exception:
            return []

    def close(self):
        if hasattr(self._local, "conn"):
            try:
                self._local.conn.close()
                del self._local.conn
            except Exception:
                pass

    def close_all(self):
        self.close()
        with self._connections_lock:
            for conn in list(self._connections or []):
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections = []

    def __del__(self):
        try:
            self.close_all()
        except Exception:
            pass
