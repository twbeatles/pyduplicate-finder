from __future__ import annotations

import logging
import sqlite3

from .contracts import CacheManagerHost

logger = logging.getLogger(__name__)


class CacheSchemaMixin(CacheManagerHost):
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
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")

                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT md5_partial FROM file_hashes LIMIT 1")
                except sqlite3.OperationalError:
                    try:
                        cursor.execute("SELECT hash_partial FROM file_hashes LIMIT 1")
                    except Exception:
                        pass

                try:
                    cursor.execute("SELECT md5_partial FROM file_hashes LIMIT 1")
                    conn.execute("DROP TABLE IF EXISTS file_hashes")
                except Exception:
                    pass

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS file_hashes (
                        path TEXT PRIMARY KEY,
                        size INTEGER,
                        mtime REAL,
                        hash_partial TEXT,
                        hash_full TEXT,
                        last_seen REAL
                    )
                    """
                )

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS meta (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                    """
                )
                conn.execute(
                    f"INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '{self.SCHEMA_VERSION}')"
                )

                conn.execute(
                    """
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
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_sessions_status ON scan_sessions(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_sessions_config ON scan_sessions(config_hash)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_files (
                        session_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        size INTEGER,
                        mtime REAL,
                        PRIMARY KEY (session_id, path)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_session ON scan_files(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_files_session_size ON scan_files(session_id, size)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_hashes (
                        session_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        size INTEGER,
                        mtime REAL,
                        hash_type TEXT NOT NULL,
                        hash_value TEXT NOT NULL,
                        PRIMARY KEY (session_id, path, hash_type)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_hashes_session ON scan_hashes(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_hashes_session_type ON scan_hashes(session_id, hash_type)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_dirs (
                        session_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        mtime REAL,
                        PRIMARY KEY (session_id, path)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_dirs_session ON scan_dirs(session_id)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_folder_sigs (
                        session_id INTEGER NOT NULL,
                        dir_path TEXT NOT NULL,
                        sig_quick TEXT,
                        sig_full TEXT,
                        bytes_total INTEGER DEFAULT 0,
                        file_count INTEGER DEFAULT 0,
                        PRIMARY KEY (session_id, dir_path)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_folder_sigs_session ON scan_folder_sigs(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_folder_sigs_full ON scan_folder_sigs(session_id, sig_full)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_results (
                        session_id INTEGER NOT NULL,
                        group_key TEXT NOT NULL,
                        path TEXT NOT NULL,
                        PRIMARY KEY (session_id, group_key, path)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_results_session ON scan_results(session_id)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_selected (
                        session_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        selected INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY (session_id, path)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_selected_session ON scan_selected(session_id)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_file_state (
                        session_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        size INTEGER,
                        mtime REAL,
                        file_exists INTEGER,
                        selection_reason TEXT,
                        exemption_status TEXT,
                        review_state TEXT,
                        collection_role TEXT,
                        baseline_delta TEXT,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (session_id, path)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_file_state_session ON scan_file_state(session_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_file_state_delta ON scan_file_state(session_id, baseline_delta)")

                conn.execute(
                    """
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
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operations_created ON file_operations(created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operations_status ON file_operations(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operations_type ON file_operations(op_type)")

                self._create_file_operation_items_v5(conn)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_file_operation_items_op ON file_operation_items(op_id)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS quarantine_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at REAL NOT NULL,
                        orig_path TEXT NOT NULL,
                        quarantine_path TEXT NOT NULL,
                        size INTEGER,
                        mtime REAL,
                        status TEXT NOT NULL
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_quarantine_items_status ON quarantine_items(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_quarantine_items_created ON quarantine_items(created_at)")

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
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_jobs_next_run ON scan_jobs(enabled, next_run_at)")

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

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scan_exemptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind TEXT NOT NULL,
                        value TEXT NOT NULL,
                        action TEXT NOT NULL,
                        note TEXT NOT NULL DEFAULT '',
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_scan_exemptions_unique ON scan_exemptions(kind, value, action)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_exemptions_action ON scan_exemptions(action)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS review_marks (
                        session_id INTEGER NOT NULL,
                        target_type TEXT NOT NULL,
                        target_key TEXT NOT NULL,
                        state TEXT NOT NULL,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (session_id, target_type, target_key)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_review_marks_session ON review_marks(session_id, updated_at DESC)")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS file_signatures (
                        path TEXT NOT NULL,
                        size INTEGER NOT NULL,
                        mtime REAL NOT NULL,
                        sig_type TEXT NOT NULL,
                        sig_value TEXT NOT NULL,
                        last_seen REAL NOT NULL,
                        PRIMARY KEY (path, sig_type)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_file_signatures_type ON file_signatures(sig_type, last_seen DESC)")
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
        except Exception:
            logger.exception("DB Init Error")
