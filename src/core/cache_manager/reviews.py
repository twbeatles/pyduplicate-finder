from __future__ import annotations

import logging
import time

from .contracts import CacheManagerHost

logger = logging.getLogger(__name__)


class CacheReviewMixin(CacheManagerHost):
    def list_review_marks(self, session_id: int, *, target_type: str | None = None):
        out = []
        if not session_id:
            return out
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            if target_type:
                cursor.execute(
                    """
                    SELECT session_id, target_type, target_key, state, updated_at
                    FROM review_marks
                    WHERE session_id=? AND target_type=?
                    ORDER BY updated_at DESC
                    """,
                    (int(session_id), str(target_type)),
                )
            else:
                cursor.execute(
                    """
                    SELECT session_id, target_type, target_key, state, updated_at
                    FROM review_marks
                    WHERE session_id=?
                    ORDER BY updated_at DESC
                    """,
                    (int(session_id),),
                )
            for row in cursor.fetchall():
                out.append(
                    {
                        "session_id": int(row[0] or 0),
                        "target_type": str(row[1] or ""),
                        "target_key": str(row[2] or ""),
                        "state": str(row[3] or ""),
                        "updated_at": float(row[4] or 0.0),
                    }
                )
        except Exception:
            logger.exception("List review marks error")
        return out

    def save_review_mark(self, session_id: int, *, target_type: str, target_key: str, state: str) -> None:
        if not session_id or not target_type or not target_key or not state:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    """
                    INSERT INTO review_marks (session_id, target_type, target_key, state, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, target_type, target_key) DO UPDATE SET
                        state=excluded.state,
                        updated_at=excluded.updated_at
                    """,
                    (int(session_id), str(target_type), str(target_key), str(state), time.time()),
                )
        except Exception:
            logger.exception("Save review mark error")

    def clear_review_mark(self, session_id: int, *, target_type: str, target_key: str) -> None:
        if not session_id or not target_type or not target_key:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    "DELETE FROM review_marks WHERE session_id=? AND target_type=? AND target_key=?",
                    (int(session_id), str(target_type), str(target_key)),
                )
        except Exception:
            logger.exception("Clear review mark error")
