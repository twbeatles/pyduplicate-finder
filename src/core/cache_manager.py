import sqlite3
import os
import platform
import threading
import weakref
import json
import hashlib
import time

class CacheManager:
    def __init__(self, db_path="scan_cache.db"):
        self.db_path = db_path
        self._local = threading.local()
        # Track all connections for proper cleanup
        self._connections_lock = threading.Lock()
        self._connections = weakref.WeakSet()
        # Initialize immediately (creation/migration)
        self._init_db()

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
                self._connections.add(conn)
        return self._local.conn


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
                    "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '2')"
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
                # Primary Key automatically indexes path, so no separate index is purely needed,
                # but explicit index doesn't hurt. We removed it as per plan.
        except Exception as e:
            print(f"DB Init Error: {e}")

    def _normalize_config(self, config: dict) -> str:
        try:
            return json.dumps(config, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return json.dumps(config, ensure_ascii=False, sort_keys=True, default=str)

    def _config_hash(self, config_json: str) -> str:
        return hashlib.sha256(config_json.encode("utf-8")).hexdigest()

    def get_config_hash(self, config: dict) -> str:
        return self._config_hash(self._normalize_config(config))

    def create_scan_session(self, config: dict, status: str = "running", stage: str = "collecting", config_hash: str = None) -> int:
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
                return cursor.lastrowid
        except Exception as e:
            print(f"Create session error: {e}")
            return 0

    def find_resumable_session(self, config: dict):
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
            print(f"Find session error: {e}")
        return None

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
            print(f"Get latest session error: {e}")
        return None

    def cleanup_old_sessions(self, keep_latest: int = 5):
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
                conn.execute(f"DELETE FROM scan_results WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_selected WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_sessions WHERE id NOT IN ({placeholders})", keep_ids)
        except Exception as e:
            print(f"Cleanup sessions error: {e}")

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
            print(f"Update session error: {e}")

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
            print(f"Save scan files error: {e}")

    def load_scan_files(self, session_id: int):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT path, size, mtime FROM scan_files WHERE session_id=?
            """, (session_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"Load scan files error: {e}")
            return []

    def clear_scan_files(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_files WHERE session_id=?", (session_id,))
        except Exception as e:
            print(f"Clear scan files error: {e}")

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
            print(f"Remove scan files error: {e}")

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
            print(f"Save scan hashes error: {e}")

    def load_scan_hashes(self, session_id: int, hash_type: str = None):
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
            print(f"Load scan hashes error: {e}")
        return result

    def clear_scan_hashes(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_hashes WHERE session_id=?", (session_id,))
        except Exception as e:
            print(f"Clear scan hashes error: {e}")

    def clear_scan_results(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_results WHERE session_id=?", (session_id,))
        except Exception as e:
            print(f"Clear scan results error: {e}")

    def save_scan_results(self, session_id: int, results: dict):
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
            print(f"Save scan results error: {e}")

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
            print(f"Load scan results error: {e}")
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
            print(f"Save selected paths error: {e}")

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
            print(f"Load selected paths error: {e}")
            return set()

    def clear_selected_paths(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_selected WHERE session_id=?", (session_id,))
        except Exception as e:
            print(f"Clear selected paths error: {e}")

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
            print(f"Cache Update Error: {e}")

    def update_cache_batch(self, entries):
        """
        Batch update cache entries.
        entries: list of (path, size, mtime, partial, full) tuples
        """
        if not entries: return
        
        try:
            conn = self._get_conn()
            with conn: # Transaction
                cursor = conn.cursor()
                
                # For batching, we might still have the "preserve existing" issue.
                # If we assume batch updates are coming from fresh calculations where we know what we have,
                # we can try to optimize. 
                # However, generic upsert logic for a batch of mixed updates is complex in SQL without Upsert syntax.
                # Given this is "PyDuplicate Finder", we usually add NEW entries or COMPLETE existing entries.
                
                # To be safe and fast:
                # Issue #4: SQLite has a limit of ~999 variables. Chunk queries.
                paths = [e[0] for e in entries]
                CHUNK_SIZE = 500
                existing_map = {}  # path -> (partial, full)
                
                for i in range(0, len(paths), CHUNK_SIZE):
                    chunk = paths[i:i + CHUNK_SIZE]
                    placeholders = ','.join(['?'] * len(chunk))
                    query = f"SELECT path, hash_partial, hash_full FROM file_hashes WHERE path IN ({placeholders})"
                    try:
                        cursor.execute(query, chunk)
                        for row in cursor.fetchall():
                            existing_map[row[0]] = (row[1], row[2])
                    except Exception as e:
                        print(f"Chunk query error: {e}")

                final_values = []
                for p, s, m, par, ful in entries:
                     curr_par, curr_ful = par, ful
                     if p in existing_map:
                         old_par, old_ful = existing_map[p]
                         if curr_par is None: curr_par = old_par
                         if curr_ful is None: curr_ful = old_ful
                     final_values.append((p, s, m, curr_par, curr_ful, time.time()))

                cursor.executemany("""
                    INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash_partial, hash_full, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, final_values)
                
        except Exception as e:
            print(f"Batch Update Error: {e}")

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
                    print(f"Cache cleanup: Removed {count} entries older than {days_old} days")
                    
                return count
        except Exception as e:
            print(f"Cache cleanup error: {e}")
            return 0

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
            for conn in list(self._connections):
                try:
                    conn.close()
                except:
                    pass
            # WeakSet will auto-clean, but clear explicitly
            self._connections = weakref.WeakSet()
    
    def __del__(self):
        """Destructor to clean up all connections on garbage collection."""
        try:
            self.close_all()
        except:
            pass

