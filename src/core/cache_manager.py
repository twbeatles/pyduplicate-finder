import sqlite3
import os
import platform
import threading

import json
import hashlib
import time
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

class CacheManager:
    SCHEMA_VERSION = 5

    def __init__(self, db_path=None):
        # Default to a user-writable location. A relative path like "scan_cache.db"
        # is fragile after packaging (CWD might be read-only or unexpected).
        override = os.environ.get("PYDUPLICATEFINDER_DB_PATH")
        using_custom = bool(db_path or override)
        resolved = db_path or override or self._default_db_path()

        # Best-effort migration: if an older build created scan_cache.db in the working
        # directory, copy it into the new per-user cache location once.
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
        # Track all connections for proper cleanup
        self._connections_lock = threading.Lock()
        # NOTE: sqlite3.Connection is not weakref-able on some Python versions (e.g. 3.14).
        # Track strong refs and close them explicitly.
        self._connections = []
        self._foi_has_id: Optional[bool] = None
        # Initialize immediately (creation/migration)
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
            # Migration is a convenience, never a hard requirement.
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
        """Thread-local connection factory"""
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # Optimize for high concurrency
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA cache_size=-64000;") # 64MB cache
            self._local.conn = conn
            # Track this connection
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

    def _file_operation_items_has_surrogate_id(self, conn: sqlite3.Connection) -> bool:
        cols = self._get_table_columns(conn, "file_operation_items")
        return "id" in cols

    @staticmethod
    def _create_file_operation_items_v5(conn: sqlite3.Connection, table_name: str = "file_operation_items") -> None:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                op_id INTEGER NOT NULL,
                path TEXT,
                action TEXT,
                result TEXT,
                detail TEXT,
                size INTEGER,
                mtime REAL,
                quarantine_path TEXT,
                created_at REAL NOT NULL
            )
            """
        )

    def _migrate_file_operation_items_to_v5(self, conn: sqlite3.Connection) -> bool:
        cols = self._get_table_columns(conn, "file_operation_items")
        if not cols:
            self._create_file_operation_items_v5(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operation_items_op ON file_operation_items(op_id)")
            return True
        if "id" in cols:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operation_items_op ON file_operation_items(op_id)")
            return True

        savepoint = "sp_file_operation_items_v5"
        try:
            conn.execute(f"SAVEPOINT {savepoint}")
            self._create_file_operation_items_v5(conn, table_name="file_operation_items_v5")
            conn.execute(
                """
                INSERT INTO file_operation_items_v5
                (op_id, path, action, result, detail, size, mtime, quarantine_path, created_at)
                SELECT op_id, path, action, result, detail, size, mtime, quarantine_path, created_at
                FROM file_operation_items
                ORDER BY created_at ASC
                """
            )
            conn.execute("DROP TABLE file_operation_items")
            conn.execute("ALTER TABLE file_operation_items_v5 RENAME TO file_operation_items")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operation_items_op ON file_operation_items(op_id)")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            return True
        except Exception:
            logger.warning("DB schema v5 migration failed for file_operation_items; keeping legacy schema", exc_info=True)
            try:
                conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            except Exception:
                pass
            return False


    def _init_db(self):
        """Initialize SQLite table with generic hash columns"""
        try:
            # Shared connection for init (just to ensure WAL mode and table existence)
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                
                # Check if old table exists with old columns
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT md5_partial FROM file_hashes LIMIT 1")
                    # If successful, we might want to drop and recreate for clean slate given hashlib change
                    # or alter table. For simplicity in this optimization phase (changing hash algo),
                    # we will drop the table to force regeneration.
                    need_recreate = True
                except sqlite3.OperationalError:
                    # Column doesn't exist or table doesn't exist
                    try:
                        cursor.execute("SELECT hash_partial FROM file_hashes LIMIT 1")
                        need_recreate = False
                    except:
                         need_recreate = False # Table likely calculates or empty, we follow create logic below

                # Force recreate if we suspect old schema or just to be safe with blake2b switch
                # Actually, checking 'md5_partial' column existence is enough to trigger migration.
                try:
                    cursor.execute("SELECT md5_partial FROM file_hashes LIMIT 1")
                    # Old schema detected, drop it
                    conn.execute("DROP TABLE IF EXISTS file_hashes")
                except:
                    pass

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS file_hashes (
                        path TEXT PRIMARY KEY,
                        size INTEGER,
                        mtime REAL,
                        hash_partial TEXT,
                        hash_full TEXT,
                        last_seen REAL
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS meta (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                conn.execute(
                    f"INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '{self.SCHEMA_VERSION}')"
                )

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scan_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        status TEXT NOT NULL,
                        stage TEXT NOT NULL,
                        config_json TEXT NOT NULL,
                        config_hash TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        progress INTEGER DEFAULT 0,
                        progress_message TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_sessions_status ON scan_sessions(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_sessions_config ON scan_sessions(config_hash)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scan_files (
                        session_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        size INTEGER,
                        mtime REAL,
                        PRIMARY KEY (session_id, path)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_session ON scan_files(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_session_size ON scan_files(session_id, size)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scan_hashes (
                        session_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        size INTEGER,
                        mtime REAL,
                        hash_type TEXT NOT NULL,
                        hash_value TEXT NOT NULL,
                        PRIMARY KEY (session_id, path, hash_type)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_hashes_session ON scan_hashes(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_hashes_session_type ON scan_hashes(session_id, hash_type)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scan_dirs (
                        session_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        mtime REAL,
                        PRIMARY KEY (session_id, path)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_dirs_session ON scan_dirs(session_id)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scan_folder_sigs (
                        session_id INTEGER NOT NULL,
                        dir_path TEXT NOT NULL,
                        sig_quick TEXT,
                        sig_full TEXT,
                        bytes_total INTEGER DEFAULT 0,
                        file_count INTEGER DEFAULT 0,
                        PRIMARY KEY (session_id, dir_path)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_folder_sigs_session ON scan_folder_sigs(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_folder_sigs_full ON scan_folder_sigs(session_id, sig_full)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scan_results (
                        session_id INTEGER NOT NULL,
                        group_key TEXT NOT NULL,
                        path TEXT NOT NULL,
                        PRIMARY KEY (session_id, group_key, path)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_results_session ON scan_results(session_id)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS scan_selected (
                        session_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        selected INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY (session_id, path)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_selected_session ON scan_selected(session_id)")

                # === File operations / audit log (additive, backward compatible) ===
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS file_operations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at REAL NOT NULL,
                        op_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        options_json TEXT,
                        message TEXT,
                        bytes_total INTEGER DEFAULT 0,
                        bytes_saved_est INTEGER DEFAULT 0
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operations_created ON file_operations(created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operations_status ON file_operations(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operations_type ON file_operations(op_type)")

                self._create_file_operation_items_v5(conn)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operation_items_op ON file_operation_items(op_id)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS quarantine_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at REAL NOT NULL,
                        orig_path TEXT NOT NULL,
                        quarantine_path TEXT NOT NULL,
                        size INTEGER,
                        mtime REAL,
                        status TEXT NOT NULL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_quarantine_items_status ON quarantine_items(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_quarantine_items_created ON quarantine_items(created_at)")

                # === Scheduler jobs/runs (schema v4) ===
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_jobs (
                        name TEXT PRIMARY KEY,
                        enabled INTEGER NOT NULL DEFAULT 0,
                        schedule_type TEXT NOT NULL DEFAULT 'daily',
                        weekday INTEGER DEFAULT 0,
                        time_hhmm TEXT NOT NULL DEFAULT '03:00',
                        output_dir TEXT,
                        output_json INTEGER NOT NULL DEFAULT 1,
                        output_csv INTEGER NOT NULL DEFAULT 1,
                        config_json TEXT NOT NULL DEFAULT '{}',
                        last_run_at REAL,
                        next_run_at REAL,
                        last_status TEXT,
                        last_message TEXT,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_jobs_enabled ON scan_jobs(enabled)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_job_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_name TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        started_at REAL NOT NULL,
                        finished_at REAL,
                        status TEXT NOT NULL,
                        message TEXT,
                        session_id INTEGER,
                        groups_count INTEGER DEFAULT 0,
                        files_count INTEGER DEFAULT 0,
                        output_json_path TEXT,
                        output_csv_path TEXT
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_job_runs_job ON scan_job_runs(job_name, started_at DESC)")
                # Primary Key automatically indexes path, so no separate index is purely needed,
                # but explicit index doesn't hurt. We removed it as per plan.
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT value FROM meta WHERE key='schema_version'")
                    row = cur.fetchone()
                    current_version = int(row[0]) if row and str(row[0]).isdigit() else 0
                except Exception:
                    current_version = 0
                migration_ok = True
                if current_version < self.SCHEMA_VERSION:
                    migration_ok = self._migrate_file_operation_items_to_v5(conn)
                if current_version < self.SCHEMA_VERSION and migration_ok:
                    conn.execute(
                        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                        (str(self.SCHEMA_VERSION),),
                    )
                self._foi_has_id = self._file_operation_items_has_surrogate_id(conn)
        except Exception as e:
            logger.exception("DB Init Error")

    def _normalize_config(self, config: dict[str, Any]) -> str:
        try:
            return json.dumps(config, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return json.dumps(config, ensure_ascii=False, sort_keys=True, default=str)

    def _config_hash(self, config_json: str) -> str:
        return hashlib.sha256(config_json.encode("utf-8")).hexdigest()

    def get_config_hash(self, config: dict[str, Any]) -> str:
        return self._config_hash(self._normalize_config(config))

    def create_scan_session(
        self,
        config: dict[str, Any],
        status: str = "running",
        stage: str = "collecting",
        config_hash: Optional[str] = None,
    ) -> int:
        config_json = self._normalize_config(config)
        if not config_hash:
            config_hash = self._config_hash(config_json)
        now = time.time()
        try:
            conn = self._get_conn()
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO scan_sessions (status, stage, config_json, config_hash, created_at, updated_at, progress, progress_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (status, stage, config_json, config_hash, now, now, 0, ""))
                return int(cursor.lastrowid or 0)
        except Exception as e:
            logger.exception("Create session error")
            return 0

    def find_resumable_session(self, config: dict[str, Any]):
        config_hash = self.get_config_hash(config)
        return self.find_resumable_session_by_hash(config_hash)

    def find_resumable_session_by_hash(self, config_hash: str):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, status, stage, config_json, config_hash, updated_at, progress, progress_message
                FROM scan_sessions
                WHERE config_hash = ? AND status IN ('running', 'paused')
                ORDER BY updated_at DESC
                LIMIT 1
            """, (config_hash,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "status": row[1],
                    "stage": row[2],
                    "config_json": row[3],
                    "config_hash": row[4],
                    "updated_at": row[5],
                    "progress": row[6],
                    "progress_message": row[7],
                }
        except Exception as e:
            logger.exception("Find session error")
        return None

    def get_latest_completed_session_by_hash(self, config_hash: str):
        if not config_hash:
            return None
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, status, stage, config_json, config_hash, updated_at, progress, progress_message
                FROM scan_sessions
                WHERE config_hash = ? AND status = 'completed'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (config_hash,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "status": row[1],
                    "stage": row[2],
                    "config_json": row[3],
                    "config_hash": row[4],
                    "updated_at": row[5],
                    "progress": row[6],
                    "progress_message": row[7],
                }
        except Exception as e:
            logger.exception("Get latest completed session error")
        return None

    def list_completed_sessions_by_hash(self, config_hash: str, limit: int = 20):
        out = []
        if not config_hash:
            return out
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, status, stage, config_json, config_hash, updated_at, progress, progress_message
                FROM scan_sessions
                WHERE config_hash = ? AND status = 'completed'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (config_hash, max(1, int(limit or 20))),
            )
            rows = cursor.fetchall()
            for row in rows:
                out.append(
                    {
                        "id": row[0],
                        "status": row[1],
                        "stage": row[2],
                        "config_json": row[3],
                        "config_hash": row[4],
                        "updated_at": row[5],
                        "progress": row[6],
                        "progress_message": row[7],
                    }
                )
        except Exception as e:
            logger.exception("List completed sessions error")
        return out

    def get_latest_session(self):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, status, stage, config_json, config_hash, updated_at, progress, progress_message
                FROM scan_sessions
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "status": row[1],
                    "stage": row[2],
                    "config_json": row[3],
                    "config_hash": row[4],
                    "updated_at": row[5],
                    "progress": row[6],
                    "progress_message": row[7],
                }
        except Exception as e:
            logger.exception("Get latest session error")
        return None

    def cleanup_old_sessions(self, keep_latest: int = 20):
        if keep_latest <= 0:
            keep_latest = 1
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM scan_sessions
                ORDER BY updated_at DESC
                LIMIT ?
            """, (keep_latest,))
            keep_ids = [row[0] for row in cursor.fetchall()]
            if not keep_ids:
                return

            placeholders = ",".join(["?"] * len(keep_ids))
            with conn:
                conn.execute(f"DELETE FROM scan_files WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_hashes WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_dirs WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_folder_sigs WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_results WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_selected WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_sessions WHERE id NOT IN ({placeholders})", keep_ids)
        except Exception as e:
            logger.exception("Cleanup sessions error")

    def update_scan_session(self, session_id: int, **fields):
        if not session_id or not fields:
            return
        try:
            fields["updated_at"] = time.time()
            keys = []
            values = []
            for key, value in fields.items():
                keys.append(f"{key}=?")
                values.append(value)
            values.append(session_id)

            conn = self._get_conn()
            with conn:
                conn.execute(
                    f"UPDATE scan_sessions SET {', '.join(keys)} WHERE id=?",
                    values
                )
        except Exception as e:
            logger.exception("Update session error")

    def save_scan_files_batch(self, session_id: int, entries):
        if not session_id or not entries:
            return
        try:
            conn = self._get_conn()
            with conn:
                cursor = conn.cursor()
                cursor.executemany("""
                    INSERT OR REPLACE INTO scan_files (session_id, path, size, mtime)
                    VALUES (?, ?, ?, ?)
                """, [(session_id, p, s, m) for p, s, m in entries])
        except Exception as e:
            logger.exception("Save scan files error")

    def save_scan_dirs_batch(self, session_id: int, entries):
        if not session_id or not entries:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO scan_dirs (session_id, path, mtime)
                    VALUES (?, ?, ?)
                    """,
                    [(session_id, p, m) for p, m in entries if p],
                )
        except Exception as e:
            logger.exception("Save scan dirs error")

    def load_scan_dirs(self, session_id: int):
        out = {}
        if not session_id:
            return out
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT path, mtime FROM scan_dirs WHERE session_id=?", (session_id,))
            for p, m in cursor.fetchall():
                out[p] = m
        except Exception as e:
            logger.exception("Load scan dirs error")
        return out

    def clear_scan_dirs(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_dirs WHERE session_id=?", (session_id,))
        except Exception as e:
            logger.exception("Clear scan dirs error")

    def save_scan_folder_sigs_batch(self, session_id: int, entries):
        """
        entries: iterable of (dir_path, sig_quick, sig_full, bytes_total, file_count)
        """
        if not session_id or not entries:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO scan_folder_sigs
                    (session_id, dir_path, sig_quick, sig_full, bytes_total, file_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (session_id, d, sq, sf, bt, fc)
                        for d, sq, sf, bt, fc in entries
                        if d
                    ],
                )
        except Exception as e:
            logger.exception("Save scan folder sigs error")

    def load_scan_files(self, session_id: int):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT path, size, mtime FROM scan_files WHERE session_id=?
            """, (session_id,))
            return cursor.fetchall()
        except Exception as e:
            logger.exception("Load scan files error")
            return []

    def has_scan_files(self, session_id: int) -> bool:
        if not session_id:
            return False
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM scan_files WHERE session_id=? LIMIT 1", (session_id,))
            return cursor.fetchone() is not None
        except Exception:
            return False

    def iter_scan_files(self, session_id: int, batch_size: int = 5000):
        """Stream scan_files rows to avoid loading everything into memory at once."""
        if not session_id:
            return
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT path, size, mtime FROM scan_files WHERE session_id=?", (session_id,))
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    yield row
        except Exception as e:
            logger.exception("Iter scan files error")

    def load_scan_hashes_for_paths(self, session_id: int, paths, hash_type: Optional[str] = None):
        """
        Load scan_hashes only for the provided paths (chunked IN queries).
        Returns {(path, htype): (hash_value, size, mtime)}
        """
        result = {}
        if not session_id or not paths:
            return result

        # SQLite has a variable limit; keep chunks conservative.
        CHUNK_SIZE = 400
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            path_list = list(paths)
            for i in range(0, len(path_list), CHUNK_SIZE):
                chunk = path_list[i:i + CHUNK_SIZE]
                placeholders = ",".join(["?"] * len(chunk))
                if hash_type:
                    cursor.execute(
                        f"""
                        SELECT path, size, mtime, hash_type, hash_value
                        FROM scan_hashes
                        WHERE session_id=? AND hash_type=? AND path IN ({placeholders})
                        """,
                        [session_id, hash_type, *chunk],
                    )
                else:
                    cursor.execute(
                        f"""
                        SELECT path, size, mtime, hash_type, hash_value
                        FROM scan_hashes
                        WHERE session_id=? AND path IN ({placeholders})
                        """,
                        [session_id, *chunk],
                    )

                for path, size, mtime, htype, hval in cursor.fetchall():
                    result[(path, htype)] = (hval, size, mtime)
        except Exception as e:
            logger.exception("Load scan hashes for paths error")

        return result

    def clear_scan_files(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_files WHERE session_id=?", (session_id,))
        except Exception as e:
            logger.exception("Clear scan files error")

    def remove_scan_files(self, session_id: int, paths):
        if not session_id or not paths:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.executemany(
                    "DELETE FROM scan_files WHERE session_id=? AND path=?",
                    [(session_id, p) for p in paths]
                )
        except Exception as e:
            logger.exception("Remove scan files error")

    def save_scan_hashes_batch(self, session_id: int, entries):
        if not session_id or not entries:
            return
        try:
            conn = self._get_conn()
            with conn:
                cursor = conn.cursor()
                cursor.executemany("""
                    INSERT OR REPLACE INTO scan_hashes (session_id, path, size, mtime, hash_type, hash_value)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, [(session_id, p, s, m, t, v) for p, s, m, t, v in entries])
        except Exception as e:
            logger.exception("Save scan hashes error")

    def load_scan_hashes(self, session_id: int, hash_type: Optional[str] = None):
        result = {}
        if not session_id:
            return result
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            if hash_type:
                cursor.execute("""
                    SELECT path, size, mtime, hash_type, hash_value
                    FROM scan_hashes WHERE session_id=? AND hash_type=?
                """, (session_id, hash_type))
            else:
                cursor.execute("""
                    SELECT path, size, mtime, hash_type, hash_value
                    FROM scan_hashes WHERE session_id=?
                """, (session_id,))
            for path, size, mtime, htype, hval in cursor.fetchall():
                result[(path, htype)] = (hval, size, mtime)
        except Exception as e:
            logger.exception("Load scan hashes error")
        return result

    def clear_scan_hashes(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_hashes WHERE session_id=?", (session_id,))
        except Exception as e:
            logger.exception("Clear scan hashes error")

    def clear_scan_results(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_results WHERE session_id=?", (session_id,))
        except Exception as e:
            logger.exception("Clear scan results error")

    def save_scan_results(self, session_id: int, results: dict[Any, list[str]]):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_results WHERE session_id=?", (session_id,))
                entries = []
                for key, paths in results.items():
                    key_str = json.dumps(key, ensure_ascii=False)
                    for path in paths:
                        entries.append((session_id, key_str, path))
                if entries:
                    conn.executemany("""
                        INSERT OR REPLACE INTO scan_results (session_id, group_key, path)
                        VALUES (?, ?, ?)
                    """, entries)
        except Exception as e:
            logger.exception("Save scan results error")

    def load_scan_results(self, session_id: int):
        results = {}
        if not session_id:
            return results
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT group_key, path FROM scan_results
                WHERE session_id=?
                ORDER BY group_key
            """, (session_id,))
            for group_key, path in cursor.fetchall():
                try:
                    key = tuple(json.loads(group_key))
                except Exception:
                    key = (group_key,)
                results.setdefault(key, []).append(path)
        except Exception as e:
            logger.exception("Load scan results error")
        return results

    def save_selected_paths(self, session_id: int, paths):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_selected WHERE session_id=?", (session_id,))
                if paths:
                    conn.executemany("""
                        INSERT OR REPLACE INTO scan_selected (session_id, path, selected)
                        VALUES (?, ?, 1)
                    """, [(session_id, p) for p in paths])
        except Exception as e:
            logger.exception("Save selected paths error")

    def save_selected_paths_delta(self, session_id: int, add_paths=None, remove_paths=None):
        if not session_id:
            return
        add_values = [p for p in (add_paths or []) if p]
        remove_values = [p for p in (remove_paths or []) if p]
        if not add_values and not remove_values:
            return
        try:
            conn = self._get_conn()
            with conn:
                if add_values:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO scan_selected (session_id, path, selected)
                        VALUES (?, ?, 1)
                        """,
                        [(session_id, p) for p in add_values],
                    )
                if remove_values:
                    conn.executemany(
                        "DELETE FROM scan_selected WHERE session_id=? AND path=?",
                        [(session_id, p) for p in remove_values],
                    )
        except Exception as e:
            logger.exception("Save selected delta error")

    def load_selected_paths(self, session_id: int):
        if not session_id:
            return set()
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT path FROM scan_selected
                WHERE session_id=? AND selected=1
            """, (session_id,))
            return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.exception("Load selected paths error")
            return set()

    def clear_selected_paths(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_selected WHERE session_id=?", (session_id,))
        except Exception as e:
            logger.exception("Clear selected paths error")

    # === Operations / Quarantine APIs ===

    def create_operation(self, op_type: str, options: Optional[dict[str, Any]] = None, status: str = "running") -> int:
        """Create an operation log row and return op_id."""
        try:
            now = time.time()
            options_json = self._normalize_config(options or {})
            conn = self._get_conn()
            with conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO file_operations (created_at, op_type, status, options_json, message, bytes_total, bytes_saved_est)
                    VALUES (?, ?, ?, ?, ?, 0, 0)
                    """,
                    (now, op_type, status, options_json, ""),
                )
                return int(cur.lastrowid or 0)
        except Exception as e:
            logger.exception("Create operation error")
            return 0

    def append_operation_items(self, op_id: int, items_batch):
        """
        Append item rows.
        items_batch: iterable of tuples (path, action, result, detail, size, mtime, quarantine_path)
        """
        if not op_id or not items_batch:
            return
        try:
            now = time.time()
            rows = []
            for idx, (path, action, result, detail, size, mtime, quarantine_path) in enumerate(items_batch):
                # Keep created_at strictly increasing within a single batch so legacy schemas
                # (without surrogate id) do not collapse rows by composite PK collisions.
                created_at = now + (idx * 1e-6)
                rows.append((op_id, path, action, result, detail, size, mtime, quarantine_path, created_at))
            conn = self._get_conn()
            has_id = self._foi_has_id
            if has_id is None:
                has_id = self._file_operation_items_has_surrogate_id(conn)
                self._foi_has_id = has_id
            with conn:
                if has_id:
                    conn.executemany(
                        """
                        INSERT INTO file_operation_items
                        (op_id, path, action, result, detail, size, mtime, quarantine_path, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
                else:
                    conn.executemany(
                        """
                        INSERT INTO file_operation_items
                        (op_id, path, action, result, detail, size, mtime, quarantine_path, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
        except Exception as e:
            logger.exception("Append operation items error")

    def finish_operation(
        self,
        op_id: int,
        status: str,
        message: str = "",
        bytes_total: int = 0,
        bytes_saved_est: int = 0,
    ) -> None:
        if not op_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    """
                    UPDATE file_operations
                    SET status=?, message=?, bytes_total=?, bytes_saved_est=?
                    WHERE id=?
                    """,
                    (status, message or "", int(bytes_total or 0), int(bytes_saved_est or 0), op_id),
                )
        except Exception as e:
            logger.exception("Finish operation error")

    def list_operations(self, limit: int = 50, offset: int = 0):
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, created_at, op_type, status, options_json, message, bytes_total, bytes_saved_est
                FROM file_operations
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (int(limit), int(offset)),
            )
            out = []
            for row in cur.fetchall():
                out.append(
                    {
                        "id": row[0],
                        "created_at": row[1],
                        "op_type": row[2],
                        "status": row[3],
                        "options_json": row[4] or "",
                        "message": row[5] or "",
                        "bytes_total": row[6] or 0,
                        "bytes_saved_est": row[7] or 0,
                    }
                )
            return out
        except Exception as e:
            logger.exception("List operations error")
            return []

    def get_operation_items(self, op_id: int):
        if not op_id:
            return []
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            has_id = self._foi_has_id
            if has_id is None:
                has_id = self._file_operation_items_has_surrogate_id(conn)
                self._foi_has_id = has_id
            order_by = "id ASC" if has_id else "created_at ASC"
            cur.execute(
                f"""
                SELECT path, action, result, detail, size, mtime, quarantine_path, created_at
                FROM file_operation_items
                WHERE op_id=?
                ORDER BY {order_by}
                """,
                (int(op_id),),
            )
            out = []
            for row in cur.fetchall():
                out.append(
                    {
                        "path": row[0] or "",
                        "action": row[1] or "",
                        "result": row[2] or "",
                        "detail": row[3] or "",
                        "size": row[4],
                        "mtime": row[5],
                        "quarantine_path": row[6] or "",
                        "created_at": row[7],
                    }
                )
            return out
        except Exception as e:
            logger.exception("Get operation items error")
            return []

    def insert_quarantine_item(
        self,
        orig_path: str,
        quarantine_path: str,
        size: Optional[int] = None,
        mtime: Optional[float] = None,
        status: str = "quarantined",
    ) -> int:
        try:
            now = time.time()
            conn = self._get_conn()
            with conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO quarantine_items (created_at, orig_path, quarantine_path, size, mtime, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (now, orig_path, quarantine_path, size, mtime, status),
                )
                return int(cur.lastrowid or 0)
        except Exception as e:
            logger.exception("Insert quarantine item error")
            return 0

    def list_quarantine_items(
        self,
        limit: int = 200,
        offset: int = 0,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
    ):
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            where = []
            params = []
            if status_filter:
                where.append("status=?")
                params.append(status_filter)
            if search:
                where.append("orig_path LIKE ?")
                params.append(f"%{search}%")
            where_sql = ("WHERE " + " AND ".join(where)) if where else ""
            cur.execute(
                f"""
                SELECT id, created_at, orig_path, quarantine_path, size, mtime, status
                FROM quarantine_items
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            )
            out = []
            for row in cur.fetchall():
                out.append(
                    {
                        "id": row[0],
                        "created_at": row[1],
                        "orig_path": row[2],
                        "quarantine_path": row[3],
                        "size": row[4] or 0,
                        "mtime": row[5] or 0.0,
                        "status": row[6],
                    }
                )
            return out
        except Exception as e:
            logger.exception("List quarantine items error")
            return []

    def update_quarantine_item_status(self, item_id: int, status: str) -> None:
        if not item_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("UPDATE quarantine_items SET status=? WHERE id=?", (status, int(item_id)))
        except Exception as e:
            logger.exception("Update quarantine status error")

    def get_quarantine_item(self, item_id: int):
        if not item_id:
            return None
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, created_at, orig_path, quarantine_path, size, mtime, status
                FROM quarantine_items
                WHERE id=?
                """,
                (int(item_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "created_at": row[1],
                "orig_path": row[2],
                "quarantine_path": row[3],
                "size": row[4] or 0,
                "mtime": row[5] or 0.0,
                "status": row[6],
            }
        except Exception as e:
            logger.exception("Get quarantine item error")
            return None

    def get_quarantine_item_by_path(self, quarantine_path: str):
        if not quarantine_path:
            return None
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, created_at, orig_path, quarantine_path, size, mtime, status
                FROM quarantine_items
                WHERE quarantine_path=?
                """,
                (str(quarantine_path),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "created_at": row[1],
                "orig_path": row[2],
                "quarantine_path": row[3],
                "size": row[4] or 0,
                "mtime": row[5] or 0.0,
                "status": row[6],
            }
        except Exception as e:
            logger.exception("Get quarantine item by path error")
            return None

    def get_quarantine_items_by_ids(self, item_ids: list[int]):
        out = {}
        ids = [int(i) for i in (item_ids or []) if i]
        if not ids:
            return out
        CHUNK_SIZE = 300
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            for i in range(0, len(ids), CHUNK_SIZE):
                chunk = ids[i:i + CHUNK_SIZE]
                placeholders = ",".join(["?"] * len(chunk))
                cur.execute(
                    f"""
                    SELECT id, created_at, orig_path, quarantine_path, size, mtime, status
                    FROM quarantine_items
                    WHERE id IN ({placeholders})
                    """,
                    chunk,
                )
                for row in cur.fetchall():
                    out[int(row[0])] = {
                        "id": row[0],
                        "created_at": row[1],
                        "orig_path": row[2],
                        "quarantine_path": row[3],
                        "size": row[4] or 0,
                        "mtime": row[5] or 0.0,
                        "status": row[6],
                    }
        except Exception as e:
            logger.exception("Get quarantine items by ids error")
        return out

    def get_cached_hash(self, path, size, mtime):
        """
        Returns (partial, full) hash if path match AND size match AND mtime match.
        Otherwise Returns None.
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT hash_partial, hash_full FROM file_hashes WHERE path=? AND size=? AND mtime=?", 
                (path, size, mtime)
            )
            row = cursor.fetchone()
            if row:
                return row # (partial, full)
        except:
            pass
        return None

    def update_cache(self, path, size, mtime, partial=None, full=None):
        """Update or Insert hash record (Single)"""
        try:
            conn = self._get_conn()
            with conn: 
                # UPSERT logic optimization: direct insert or replace
                # We need to preserve existing values if new ones are None
                # BUT, checking existence adds a read. 
                # For maximum speed, we assume the caller provides what they have.
                # However, to support 'update partial only' or 'update full only' without overwriting the other with NULL,
                # we still need to read or use ON CONFLICT (which is standard SQL).
                # SQLite 'ON CONFLICT DO UPDATE' is available in newer versions.
                # Let's stick to Read-Modify-Write for safety if we can't guarantee SQLite version,
                # OR if we know usage pattern. 
                # Usage: `get_file_hash` calculates, then updates. It might calculate partial, return, then later full.
                
                cursor = conn.cursor()
                cursor.execute("SELECT hash_partial, hash_full FROM file_hashes WHERE path=?", (path,))
                row = cursor.fetchone()
                
                current_partial = partial
                current_full = full
                
                if row:
                    if current_partial is None: current_partial = row[0]
                    if current_full is None: current_full = row[1]

                cursor.execute("""
                    INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash_partial, hash_full, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (path, size, mtime, current_partial, current_full, time.time()))
                
        except Exception as e:
            logger.exception("Cache Update Error")

    def update_cache_batch(self, entries):
        """
        Batch update cache entries.
        entries: list of (path, size, mtime, partial, full) tuples
        """
        if not entries: return
        
        try:
            conn = self._get_conn()
            now = time.time()
            rows = [(p, s, m, par, ful, now) for p, s, m, par, ful in entries]
            with conn: # Transaction
                cursor = conn.cursor()
                try:
                    cursor.executemany(
                        """
                        INSERT INTO file_hashes (path, size, mtime, hash_partial, hash_full, last_seen)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(path) DO UPDATE SET
                            size=excluded.size,
                            mtime=excluded.mtime,
                            hash_partial=COALESCE(excluded.hash_partial, file_hashes.hash_partial),
                            hash_full=COALESCE(excluded.hash_full, file_hashes.hash_full),
                            last_seen=excluded.last_seen
                        """,
                        rows,
                    )
                except sqlite3.OperationalError:
                    # Conservative fallback for older SQLite builds.
                    cursor.executemany(
                        """
                        INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash_partial, hash_full, last_seen)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
        except Exception as e:
            logger.exception("Batch Update Error")

    def cleanup_old_entries(self, days_old: int = 30) -> int:
        """
        Issue #F2: Remove cache entries older than specified days.
        
        Args:
            days_old: Number of days after which entries are considered stale (default: 30)
            
        Returns:
            Number of deleted entries
        """
        import time
        cutoff_time = time.time() - (days_old * 24 * 60 * 60)
        
        try:
            conn = self._get_conn()
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM file_hashes WHERE last_seen < ?", (cutoff_time,))
                count = cursor.fetchone()[0]
                
                if count > 0:
                    cursor.execute("DELETE FROM file_hashes WHERE last_seen < ?", (cutoff_time,))
                    conn.commit()
                    logger.info("Cache cleanup: removed %s entries older than %s days", count, days_old)
                    
                return count
        except Exception as e:
            logger.exception("Cache cleanup error")
            return 0

    # === Scheduler jobs / runs ===

    def upsert_scan_job(
        self,
        *,
        name: str,
        enabled: bool,
        schedule_type: str,
        weekday: int,
        time_hhmm: str,
        output_dir: str,
        output_json: bool,
        output_csv: bool,
        config_json: str,
        next_run_at: Optional[float] = None,
    ) -> None:
        if not name:
            return
        now = time.time()
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    """
                    INSERT INTO scan_jobs (
                        name, enabled, schedule_type, weekday, time_hhmm, output_dir,
                        output_json, output_csv, config_json, next_run_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        enabled=excluded.enabled,
                        schedule_type=excluded.schedule_type,
                        weekday=excluded.weekday,
                        time_hhmm=excluded.time_hhmm,
                        output_dir=excluded.output_dir,
                        output_json=excluded.output_json,
                        output_csv=excluded.output_csv,
                        config_json=excluded.config_json,
                        next_run_at=excluded.next_run_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        str(name),
                        1 if enabled else 0,
                        str(schedule_type or "daily"),
                        int(weekday or 0),
                        str(time_hhmm or "03:00"),
                        str(output_dir or ""),
                        1 if output_json else 0,
                        1 if output_csv else 0,
                        str(config_json or "{}"),
                        float(next_run_at) if next_run_at is not None else None,
                        now,
                    ),
                )
        except Exception as e:
            logger.exception("Upsert scan job error")

    def get_scan_job(self, name: str):
        if not name:
            return None
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, enabled, schedule_type, weekday, time_hhmm, output_dir, output_json, output_csv,
                       config_json, last_run_at, next_run_at, last_status, last_message, updated_at
                FROM scan_jobs
                WHERE name=?
                LIMIT 1
                """,
                (str(name),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "name": row[0],
                "enabled": bool(row[1]),
                "schedule_type": row[2],
                "weekday": int(row[3] or 0),
                "time_hhmm": row[4],
                "output_dir": row[5] or "",
                "output_json": bool(row[6]),
                "output_csv": bool(row[7]),
                "config_json": row[8] or "{}",
                "last_run_at": row[9],
                "next_run_at": row[10],
                "last_status": row[11],
                "last_message": row[12],
                "updated_at": row[13],
            }
        except Exception as e:
            logger.exception("Get scan job error")
        return None

    def update_scan_job_runtime(
        self,
        name: str,
        *,
        last_run_at: Optional[float] = None,
        next_run_at: Optional[float] = None,
        last_status: Optional[str] = None,
        last_message: Optional[str] = None,
    ) -> None:
        if not name:
            return
        fields = []
        values = []
        if last_run_at is not None:
            fields.append("last_run_at=?")
            values.append(float(last_run_at))
        if next_run_at is not None:
            fields.append("next_run_at=?")
            values.append(float(next_run_at))
        if last_status is not None:
            fields.append("last_status=?")
            values.append(str(last_status))
        if last_message is not None:
            fields.append("last_message=?")
            values.append(str(last_message))
        fields.append("updated_at=?")
        values.append(time.time())
        values.append(str(name))
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(f"UPDATE scan_jobs SET {', '.join(fields)} WHERE name=?", values)
        except Exception as e:
            logger.exception("Update scan job runtime error")

    def create_scan_job_run(self, job_name: str, *, session_id: Optional[int] = None, status: str = "running") -> int:
        if not job_name:
            return 0
        now = time.time()
        try:
            conn = self._get_conn()
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO scan_job_runs (job_name, created_at, started_at, status, session_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(job_name), now, now, str(status or "running"), int(session_id or 0)),
                )
                return int(cursor.lastrowid or 0)
        except Exception as e:
            logger.exception("Create scan job run error")
            return 0

    def update_scan_job_run_session(self, run_id: int, *, session_id: Optional[int]) -> None:
        if not run_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    "UPDATE scan_job_runs SET session_id=? WHERE id=?",
                    (int(session_id or 0), int(run_id)),
                )
        except Exception as e:
            logger.exception("Update scan job run session error")

    def finish_scan_job_run(
        self,
        run_id: int,
        *,
        status: str,
        message: str = "",
        groups_count: int = 0,
        files_count: int = 0,
        output_json_path: str = "",
        output_csv_path: str = "",
    ) -> None:
        if not run_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    """
                    UPDATE scan_job_runs
                    SET finished_at=?, status=?, message=?, groups_count=?, files_count=?,
                        output_json_path=?, output_csv_path=?
                    WHERE id=?
                    """,
                    (
                        time.time(),
                        str(status or "completed"),
                        str(message or ""),
                        int(groups_count or 0),
                        int(files_count or 0),
                        str(output_json_path or ""),
                        str(output_csv_path or ""),
                        int(run_id),
                    ),
                )
        except Exception as e:
            logger.exception("Finish scan job run error")

    def close(self):
        """Close the current thread's database connection."""
        if hasattr(self._local, "conn"):
            try:
                self._local.conn.close()
                del self._local.conn
            except:
                pass
    
    def close_all(self):
        """Close ALL tracked database connections (from all threads)."""
        # First close current thread's connection
        self.close()
        
        # Close all tracked connections
        with self._connections_lock:
            for conn in list(self._connections or []):
                try:
                    conn.close()
                except:
                    pass
            self._connections = []
    
    def __del__(self):
        """Destructor to clean up all connections on garbage collection."""
        try:
            self.close_all()
        except:
            pass


