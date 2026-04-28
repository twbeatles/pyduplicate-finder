from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

from .contracts import CacheManagerHost

logger = logging.getLogger(__name__)


class CacheSessionMixin(CacheManagerHost):
    def _normalize_config(self, config: dict[str, Any]) -> str:
        try:
            return json.dumps(config, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return json.dumps(config, ensure_ascii=False, sort_keys=True, default=str)

    def _config_hash(self, config_json: str) -> str:
        return hashlib.sha256(config_json.encode("utf-8")).hexdigest()

    def get_config_hash(self, config: dict[str, Any]) -> str:
        return self._config_hash(self._normalize_config(config))

    def create_scan_session(
        self,
        config: dict[str, Any],
        status: str = "running",
        stage: str = "collecting",
        config_hash: Optional[str] = None,
    ) -> int:
        config_json = self._normalize_config(config)
        if not config_hash:
            config_hash = self._config_hash(config_json)
        now = time.time()
        try:
            conn = self._get_conn()
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO scan_sessions (status, stage, config_json, config_hash, created_at, updated_at, progress, progress_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (status, stage, config_json, config_hash, now, now, 0, ""),
                )
                return int(cursor.lastrowid or 0)
        except Exception:
            logger.exception("Create session error")
            return 0

    def find_resumable_session(self, config: dict[str, Any]):
        config_hash = self.get_config_hash(config)
        return self.find_resumable_session_by_hash(config_hash)

    def find_resumable_session_by_hash(self, config_hash: str):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, status, stage, config_json, config_hash, updated_at, progress, progress_message
                FROM scan_sessions
                WHERE config_hash = ? AND status IN ('running', 'paused')
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (config_hash,),
            )
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
        except Exception:
            logger.exception("Find session error")
        return None

    def get_latest_completed_session_by_hash(self, config_hash: str):
        if not config_hash:
            return None
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, status, stage, config_json, config_hash, updated_at, progress, progress_message
                FROM scan_sessions
                WHERE config_hash = ? AND status = 'completed'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (config_hash,),
            )
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
        except Exception:
            logger.exception("Get latest completed session error")
        return None

    def list_completed_sessions_by_hash(self, config_hash: str, limit: int = 20):
        out = []
        if not config_hash:
            return out
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, status, stage, config_json, config_hash, updated_at, progress, progress_message
                FROM scan_sessions
                WHERE config_hash = ? AND status = 'completed'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (config_hash, max(1, int(limit or 20))),
            )
            rows = cursor.fetchall()
            for row in rows:
                out.append(
                    {
                        "id": row[0],
                        "status": row[1],
                        "stage": row[2],
                        "config_json": row[3],
                        "config_hash": row[4],
                        "updated_at": row[5],
                        "progress": row[6],
                        "progress_message": row[7],
                    }
                )
        except Exception:
            logger.exception("List completed sessions error")
        return out

    def get_latest_session(self):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, status, stage, config_json, config_hash, updated_at, progress, progress_message
                FROM scan_sessions
                ORDER BY updated_at DESC
                LIMIT 1
                """
            )
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
        except Exception:
            logger.exception("Get latest session error")
        return None

    def cleanup_old_sessions(self, keep_latest: int = 20):
        if keep_latest <= 0:
            keep_latest = 1
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id FROM scan_sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (keep_latest,),
            )
            keep_ids = [row[0] for row in cursor.fetchall()]
            if not keep_ids:
                return

            placeholders = ",".join(["?"] * len(keep_ids))
            with conn:
                conn.execute(f"DELETE FROM scan_files WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_hashes WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_dirs WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_folder_sigs WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_results WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_selected WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_file_state WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM review_marks WHERE session_id NOT IN ({placeholders})", keep_ids)
                conn.execute(f"DELETE FROM scan_sessions WHERE id NOT IN ({placeholders})", keep_ids)
        except Exception:
            logger.exception("Cleanup sessions error")

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
                conn.execute(f"UPDATE scan_sessions SET {', '.join(keys)} WHERE id=?", values)
        except Exception:
            logger.exception("Update session error")
