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

    def get_quarantine_total_size(self, *, status_filter: Optional[str] = None) -> int:
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            if status_filter:
                cur.execute(
                    "SELECT COALESCE(SUM(size), 0) FROM quarantine_items WHERE status=?",
                    (str(status_filter),),
                )
            else:
                cur.execute("SELECT COALESCE(SUM(size), 0) FROM quarantine_items")
            row = cur.fetchone()
            return int((row or [0])[0] or 0)
        except Exception:
            logger.exception("Get quarantine total size error")
            return 0

    def iter_quarantine_items_oldest(
        self,
        *,
        status_filter: Optional[str] = None,
        batch_size: int = 500,
    ):
        last_created = None
        last_id = None
        size = max(1, int(batch_size or 500))
        while True:
            try:
                conn = self._get_conn()
                cur = conn.cursor()
                where = []
                params = []
                if status_filter:
                    where.append("status=?")
                    params.append(str(status_filter))
                if last_created is not None and last_id is not None:
                    where.append("(created_at > ? OR (created_at = ? AND id > ?))")
                    params.extend([float(last_created), float(last_created), int(last_id)])
                where_sql = f"WHERE {' AND '.join(where)}" if where else ""
                cur.execute(
                    f"""
                    SELECT id, created_at, orig_path, quarantine_path, size, mtime, status
                    FROM quarantine_items
                    {where_sql}
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                    """,
                    (*params, size),
                )
                rows = cur.fetchall()
                if not rows:
                    break
                for row in rows:
                    last_created = row[1]
                    last_id = row[0]
                    yield {
                        "id": row[0],
                        "created_at": row[1],
                        "orig_path": row[2],
                        "quarantine_path": row[3],
                        "size": row[4] or 0,
                        "mtime": row[5] or 0.0,
                        "status": row[6],
                    }
            except Exception:
                logger.exception("Iter quarantine items error")
                break

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
