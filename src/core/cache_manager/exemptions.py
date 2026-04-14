from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class CacheExemptionMixin:
    def list_scan_exemptions(self, *, action_filter: str | None = None):
        out = []
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            if action_filter:
                cursor.execute(
                    """
                    SELECT id, kind, value, action, note, created_at
                    FROM scan_exemptions
                    WHERE action=?
                    ORDER BY created_at ASC, id ASC
                    """,
                    (str(action_filter),),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, kind, value, action, note, created_at
                    FROM scan_exemptions
                    ORDER BY created_at ASC, id ASC
                    """
                )
            for row in cursor.fetchall():
                out.append(
                    {
                        "id": int(row[0] or 0),
                        "kind": str(row[1] or ""),
                        "value": str(row[2] or ""),
                        "action": str(row[3] or ""),
                        "note": str(row[4] or ""),
                        "created_at": float(row[5] or 0.0),
                    }
                )
        except Exception:
            logger.exception("List scan exemptions error")
        return out

    def add_scan_exemption(self, *, kind: str, value: str, action: str, note: str = "") -> int:
        if not kind or not value or not action:
            return 0
        try:
            conn = self._get_conn()
            now = time.time()
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO scan_exemptions (kind, value, action, note, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(kind, value, action) DO UPDATE SET
                        note=excluded.note
                    """,
                    (str(kind), str(value), str(action), str(note or ""), now),
                )
                if cursor.lastrowid:
                    return int(cursor.lastrowid)
                cursor.execute(
                    "SELECT id FROM scan_exemptions WHERE kind=? AND value=? AND action=? LIMIT 1",
                    (str(kind), str(value), str(action)),
                )
                row = cursor.fetchone()
                return int(row[0] or 0) if row else 0
        except Exception:
            logger.exception("Add scan exemption error")
            return 0

    def delete_scan_exemption(self, exemption_id: int) -> None:
        if not exemption_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_exemptions WHERE id=?", (int(exemption_id),))
        except Exception:
            logger.exception("Delete scan exemption error")

    def replace_scan_exemptions(self, items) -> None:
        normalized = []
        for item in items or []:
            try:
                kind = str(item.get("kind") or "")
                value = str(item.get("value") or "")
                action = str(item.get("action") or "")
                note = str(item.get("note") or "")
                if kind and value and action:
                    normalized.append((kind, value, action, note))
            except Exception:
                continue
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_exemptions")
                if normalized:
                    now = time.time()
                    conn.executemany(
                        """
                        INSERT INTO scan_exemptions (kind, value, action, note, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        [(k, v, a, n, now) for k, v, a, n in normalized],
                    )
        except Exception:
            logger.exception("Replace scan exemptions error")
