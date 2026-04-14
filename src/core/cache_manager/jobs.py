from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class CacheJobMixin:
    def list_scan_jobs(self):
        out = []
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, enabled, schedule_type, weekday, time_hhmm, output_dir, output_json, output_csv,
                       config_json, last_run_at, next_run_at, last_status, last_message, updated_at
                FROM scan_jobs
                ORDER BY name ASC
                """
            )
            for row in cursor.fetchall():
                out.append(
                    {
                        "name": str(row[0] or ""),
                        "enabled": bool(row[1]),
                        "schedule_type": str(row[2] or "daily"),
                        "weekday": int(row[3] or 0),
                        "time_hhmm": str(row[4] or "03:00"),
                        "output_dir": str(row[5] or ""),
                        "output_json": bool(row[6]),
                        "output_csv": bool(row[7]),
                        "config_json": str(row[8] or "{}"),
                        "last_run_at": row[9],
                        "next_run_at": row[10],
                        "last_status": row[11],
                        "last_message": row[12],
                        "updated_at": row[13],
                    }
                )
        except Exception:
            logger.exception("List scan jobs error")
        return out

    def upsert_scan_job(
        self,
        *,
        name: str,
        enabled: bool,
        schedule_type: str,
        weekday: int,
        time_hhmm: str,
        output_dir: str,
        output_json: bool,
        output_csv: bool,
        config_json: str,
        next_run_at: Optional[float] = None,
    ) -> None:
        if not name:
            return
        now = time.time()
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    """
                    INSERT INTO scan_jobs (
                        name, enabled, schedule_type, weekday, time_hhmm, output_dir,
                        output_json, output_csv, config_json, next_run_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        enabled=excluded.enabled,
                        schedule_type=excluded.schedule_type,
                        weekday=excluded.weekday,
                        time_hhmm=excluded.time_hhmm,
                        output_dir=excluded.output_dir,
                        output_json=excluded.output_json,
                        output_csv=excluded.output_csv,
                        config_json=excluded.config_json,
                        next_run_at=excluded.next_run_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        str(name),
                        1 if enabled else 0,
                        str(schedule_type or "daily"),
                        int(weekday or 0),
                        str(time_hhmm or "03:00"),
                        str(output_dir or ""),
                        1 if output_json else 0,
                        1 if output_csv else 0,
                        str(config_json or "{}"),
                        float(next_run_at) if next_run_at is not None else None,
                        now,
                    ),
                )
        except Exception:
            logger.exception("Upsert scan job error")

    def delete_scan_job(self, name: str) -> None:
        if not name:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_jobs WHERE name=?", (str(name),))
        except Exception:
            logger.exception("Delete scan job error")

    def list_scan_job_runs(self, job_name: str | None = None, limit: int = 50):
        out = []
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            if job_name:
                cursor.execute(
                    """
                    SELECT id, job_name, created_at, started_at, finished_at, status, message, session_id,
                           groups_count, files_count, output_json_path, output_csv_path
                    FROM scan_job_runs
                    WHERE job_name=?
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (str(job_name), max(1, int(limit or 50))),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, job_name, created_at, started_at, finished_at, status, message, session_id,
                           groups_count, files_count, output_json_path, output_csv_path
                    FROM scan_job_runs
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (max(1, int(limit or 50)),),
                )
            for row in cursor.fetchall():
                out.append(
                    {
                        "id": int(row[0] or 0),
                        "job_name": str(row[1] or ""),
                        "created_at": float(row[2] or 0.0),
                        "started_at": float(row[3] or 0.0),
                        "finished_at": row[4],
                        "status": str(row[5] or ""),
                        "message": str(row[6] or ""),
                        "session_id": int(row[7] or 0),
                        "groups_count": int(row[8] or 0),
                        "files_count": int(row[9] or 0),
                        "output_json_path": str(row[10] or ""),
                        "output_csv_path": str(row[11] or ""),
                    }
                )
        except Exception:
            logger.exception("List scan job runs error")
        return out

    def get_scan_job(self, name: str):
        if not name:
            return None
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT name, enabled, schedule_type, weekday, time_hhmm, output_dir, output_json, output_csv,
                       config_json, last_run_at, next_run_at, last_status, last_message, updated_at
                FROM scan_jobs
                WHERE name=?
                LIMIT 1
                """,
                (str(name),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "name": row[0],
                "enabled": bool(row[1]),
                "schedule_type": row[2],
                "weekday": int(row[3] or 0),
                "time_hhmm": row[4],
                "output_dir": row[5] or "",
                "output_json": bool(row[6]),
                "output_csv": bool(row[7]),
                "config_json": row[8] or "{}",
                "last_run_at": row[9],
                "next_run_at": row[10],
                "last_status": row[11],
                "last_message": row[12],
                "updated_at": row[13],
            }
        except Exception:
            logger.exception("Get scan job error")
        return None

    def update_scan_job_runtime(
        self,
        name: str,
        *,
        last_run_at: Optional[float] = None,
        next_run_at: Optional[float] = None,
        last_status: Optional[str] = None,
        last_message: Optional[str] = None,
    ) -> None:
        if not name:
            return
        fields = []
        values = []
        if last_run_at is not None:
            fields.append("last_run_at=?")
            values.append(float(last_run_at))
        if next_run_at is not None:
            fields.append("next_run_at=?")
            values.append(float(next_run_at))
        if last_status is not None:
            fields.append("last_status=?")
            values.append(str(last_status))
        if last_message is not None:
            fields.append("last_message=?")
            values.append(str(last_message))
        fields.append("updated_at=?")
        values.append(time.time())
        values.append(str(name))
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(f"UPDATE scan_jobs SET {', '.join(fields)} WHERE name=?", values)
        except Exception:
            logger.exception("Update scan job runtime error")

    def create_scan_job_run(self, job_name: str, *, session_id: Optional[int] = None, status: str = "running") -> int:
        if not job_name:
            return 0
        now = time.time()
        try:
            conn = self._get_conn()
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO scan_job_runs (job_name, created_at, started_at, status, session_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(job_name), now, now, str(status or "running"), int(session_id or 0)),
                )
                return int(cursor.lastrowid or 0)
        except Exception:
            logger.exception("Create scan job run error")
            return 0

    def update_scan_job_run_session(self, run_id: int, *, session_id: Optional[int]) -> None:
        if not run_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("UPDATE scan_job_runs SET session_id=? WHERE id=?", (int(session_id or 0), int(run_id)))
        except Exception:
            logger.exception("Update scan job run session error")

    def finish_scan_job_run(
        self,
        run_id: int,
        *,
        status: str,
        message: str = "",
        groups_count: int = 0,
        files_count: int = 0,
        output_json_path: str = "",
        output_csv_path: str = "",
    ) -> None:
        if not run_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    """
                    UPDATE scan_job_runs
                    SET finished_at=?, status=?, message=?, groups_count=?, files_count=?,
                        output_json_path=?, output_csv_path=?
                    WHERE id=?
                    """,
                    (
                        time.time(),
                        str(status or "completed"),
                        str(message or ""),
                        int(groups_count or 0),
                        int(files_count or 0),
                        str(output_json_path or ""),
                        str(output_csv_path or ""),
                        int(run_id),
                    ),
                )
        except Exception:
            logger.exception("Finish scan job run error")
