from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class CacheQuarantineMixin:
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
        except Exception:
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
        except Exception:
            logger.exception("List quarantine items error")
            return []

    def update_quarantine_item_status(self, item_id: int, status: str) -> None:
        if not item_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("UPDATE quarantine_items SET status=? WHERE id=?", (status, int(item_id)))
        except Exception:
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
        except Exception:
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
        except Exception:
            logger.exception("Get quarantine item by path error")
            return None

    def get_quarantine_items_by_ids(self, item_ids: list[int]):
        out = {}
        ids = [int(i) for i in (item_ids or []) if i]
        if not ids:
            return out
        chunk_size = 300
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            for i in range(0, len(ids), chunk_size):
                chunk = ids[i:i + chunk_size]
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
        except Exception:
            logger.exception("Get quarantine items by ids error")
        return out
