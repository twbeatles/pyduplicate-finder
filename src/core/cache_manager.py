import sqlite3
import os
import platform
import threading

class CacheManager:
    def __init__(self, db_path="scan_cache.db"):
        self.db_path = db_path
        self._local = threading.local()
        # Initialize immediately (creation/migration)
        self._init_db()

    def _get_conn(self):
        """Thread-local connection factory"""
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # Optimize for high concurrency
            self._local.conn.execute("PRAGMA synchronous=NORMAL;")
            self._local.conn.execute("PRAGMA cache_size=-64000;") # 64MB cache
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
                # Primary Key automatically indexes path, so no separate index is purely needed,
                # but explicit index doesn't hurt. We removed it as per plan.
        except Exception as e:
            print(f"DB Init Error: {e}")

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
                """, (path, size, mtime, current_partial, current_full, mtime))
                
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
                # 1. Select all paths in this batch to find existing.
                paths = [e[0] for e in entries]
                placeholders = ','.join(['?'] * len(paths))
                query = f"SELECT path, hash_partial, hash_full FROM file_hashes WHERE path IN ({placeholders})"
                
                existing_map = {} # path -> (partial, full)
                try:
                    cursor.execute(query, paths)
                    for row in cursor.fetchall():
                        existing_map[row[0]] = (row[1], row[2])
                except:
                    # Fallback if too many variables for SQL
                    pass

                final_values = []
                for p, s, m, par, ful in entries:
                     curr_par, curr_ful = par, ful
                     if p in existing_map:
                         old_par, old_ful = existing_map[p]
                         if curr_par is None: curr_par = old_par
                         if curr_ful is None: curr_ful = old_ful
                     final_values.append((p, s, m, curr_par, curr_ful, m))

                cursor.executemany("""
                    INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash_partial, hash_full, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, final_values)
                
        except Exception as e:
            print(f"Batch Update Error: {e}")

    def close(self):
        if hasattr(self._local, "conn"):
            try:
                self._local.conn.close()
                del self._local.conn
            except:
                pass
