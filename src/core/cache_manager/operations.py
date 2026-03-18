from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CacheOperationMixin:
    def create_operation(self, op_type: str, options: Optional[dict[str, Any]] = None, status: str = "running") -> int:
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
        except Exception:
            logger.exception("Create operation error")
            return 0

    def append_operation_items(self, op_id: int, items_batch):
        if not op_id or not items_batch:
            return
        try:
            now = time.time()
            rows = []
            for idx, (path, action, result, detail, size, mtime, quarantine_path) in enumerate(items_batch):
                created_at = now + (idx * 1e-6)
                rows.append((op_id, path, action, result, detail, size, mtime, quarantine_path, created_at))
            conn = self._get_conn()
            has_id = self._foi_has_id
            if has_id is None:
                has_id = self._file_operation_items_has_surrogate_id(conn)
                self._foi_has_id = has_id
            with conn:
                conn.executemany(
                    """
                    INSERT INTO file_operation_items
                    (op_id, path, action, result, detail, size, mtime, quarantine_path, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
        except Exception:
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
        except Exception:
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
        except Exception:
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
        except Exception:
            logger.exception("Get operation items error")
            return []
