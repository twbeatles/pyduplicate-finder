from __future__ import annotations

import logging
import sqlite3
import time

from .contracts import CacheManagerHost

logger = logging.getLogger(__name__)


class CacheHashMixin(CacheManagerHost):
    def get_cached_hash(self, path, size, mtime):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT hash_partial, hash_full FROM file_hashes WHERE path=? AND size=? AND mtime=?",
                (path, size, mtime),
            )
            row = cursor.fetchone()
            if row:
                return row
        except Exception:
            pass
        return None

    def update_cache(self, path, size, mtime, partial=None, full=None):
        try:
            conn = self._get_conn()
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT hash_partial, hash_full FROM file_hashes WHERE path=?", (path,))
                row = cursor.fetchone()

                current_partial = partial
                current_full = full
                if row:
                    if current_partial is None:
                        current_partial = row[0]
                    if current_full is None:
                        current_full = row[1]

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash_partial, hash_full, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (path, size, mtime, current_partial, current_full, time.time()),
                )
        except Exception:
            logger.exception("Cache Update Error")

    def update_cache_batch(self, entries):
        if not entries:
            return
        try:
            conn = self._get_conn()
            now = time.time()
            rows = [(p, s, m, par, ful, now) for p, s, m, par, ful in entries]
            with conn:
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
                    cursor.executemany(
                        """
                        INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash_partial, hash_full, last_seen)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
        except Exception:
            logger.exception("Batch Update Error")

    def cleanup_old_entries(self, days_old: int = 30) -> int:
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
        except Exception:
            logger.exception("Cache cleanup error")
            return 0
