from __future__ import annotations

import logging
import time

from .contracts import CacheManagerHost

logger = logging.getLogger(__name__)


class CacheSignatureMixin(CacheManagerHost):
    def get_cached_signature(self, path: str, size: int, mtime: float, sig_type: str):
        if not path or not sig_type:
            return None
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT sig_value FROM file_signatures
                WHERE path=? AND size=? AND mtime=? AND sig_type=?
                LIMIT 1
                """,
                (str(path), int(size or 0), float(mtime or 0.0), str(sig_type)),
            )
            row = cursor.fetchone()
            if row:
                return str(row[0] or "")
        except Exception:
            logger.exception("Get cached signature error")
        return None

    def update_signature_batch(self, entries) -> None:
        rows = []
        for entry in entries or []:
            try:
                path, size, mtime, sig_type, sig_value = entry
                if path and sig_type and sig_value:
                    rows.append((str(path), int(size or 0), float(mtime or 0.0), str(sig_type), str(sig_value), time.time()))
            except Exception:
                continue
        if not rows:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO file_signatures (path, size, mtime, sig_type, sig_value, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
        except Exception:
            logger.exception("Update signature batch error")
