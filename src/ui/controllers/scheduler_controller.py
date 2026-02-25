from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.core.scheduler import ScheduleConfig, compute_next_run, is_due

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduledRunContext:
    output_dir: str = ""
    output_json: bool = True
    output_csv: bool = True
    schedule_type: str = "daily"
    weekday: int = 0
    time_hhmm: str = "03:00"
    snapshot_config_hash: str = ""
    snapshot_folders: tuple[str, ...] = ()
    missing_folders: tuple[str, ...] = ()
    executed_config_hash: str = ""
    executed_folders: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "output_dir": self.output_dir,
            "output_json": self.output_json,
            "output_csv": self.output_csv,
            "schedule_type": self.schedule_type,
            "weekday": int(self.weekday),
            "time_hhmm": self.time_hhmm,
            "snapshot_config_hash": self.snapshot_config_hash,
            "snapshot_folders": list(self.snapshot_folders or ()),
            "missing_folders": list(self.missing_folders or ()),
            "executed_config_hash": self.executed_config_hash,
            "executed_folders": list(self.executed_folders or ()),
        }


class SchedulerController:
    @staticmethod
    def _normalize_for_hash(scan_config: dict) -> str:
        try:
            return json.dumps(scan_config or {}, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return "{}"

    def parse_scan_config(self, job: dict) -> dict:
        raw = (job or {}).get("config_json")
        if isinstance(raw, dict):
            return dict(raw)
        if raw is None:
            return {}
        text = str(raw).strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return dict(parsed)
            logger.warning("Scheduled scan config is not an object: %r", type(parsed).__name__)
            return {}
        except Exception:
            logger.warning("Failed to parse scheduled scan config_json", exc_info=True)
            return {}

    def resolve_snapshot_folders(self, scan_cfg: dict) -> tuple[list[str], list[str]]:
        raw = (scan_cfg or {}).get("folders")
        src = list(raw) if isinstance(raw, (list, tuple)) else []
        valid: list[str] = []
        missing: list[str] = []
        seen: set[str] = set()
        for p in src:
            if not p:
                continue
            path = os.path.abspath(str(p))
            norm = os.path.normcase(os.path.normpath(path))
            if norm in seen:
                continue
            seen.add(norm)
            if os.path.isdir(path):
                valid.append(path)
            else:
                missing.append(path)
        return valid, missing

    @staticmethod
    def build_config(
        *,
        enabled: bool,
        schedule_type: str,
        weekday: int,
        time_hhmm: str,
    ) -> ScheduleConfig:
        return ScheduleConfig(
            enabled=bool(enabled),
            schedule_type=str(schedule_type or "daily"),
            weekday=int(weekday or 0),
            time_hhmm=str(time_hhmm or "03:00").strip() or "03:00",
        )

    def persist_job(
        self,
        *,
        cache_manager,
        cfg: ScheduleConfig,
        scan_config: dict,
        output_dir: str,
        output_json: bool,
        output_csv: bool,
    ) -> None:
        next_dt = compute_next_run(cfg)
        next_ts = next_dt.timestamp() if next_dt else None
        cache_manager.upsert_scan_job(
            name="default",
            enabled=cfg.enabled,
            schedule_type=cfg.schedule_type,
            weekday=cfg.weekday,
            time_hhmm=cfg.time_hhmm,
            output_dir=str(output_dir or "").strip(),
            output_json=bool(output_json),
            output_csv=bool(output_csv),
            config_json=json.dumps(scan_config, ensure_ascii=False, sort_keys=True, default=str),
            next_run_at=next_ts,
        )

    def get_due_job(
        self,
        *,
        cache_manager,
        is_scanning: bool,
        now_ts: Optional[float] = None,
    ) -> tuple[Optional[dict], Optional[ScheduleConfig]]:
        if is_scanning:
            return None, None
        job = cache_manager.get_scan_job("default")
        if not job or not bool(job.get("enabled")):
            return None, None

        cfg = self.build_config(
            enabled=bool(job.get("enabled")),
            schedule_type=str(job.get("schedule_type") or "daily"),
            weekday=int(job.get("weekday") or 0),
            time_hhmm=str(job.get("time_hhmm") or "03:00"),
        )
        if not is_due(cfg, last_run_at=job.get("last_run_at"), now_ts=now_ts):
            return None, None
        return job, cfg

    def record_skip_no_folders(
        self,
        *,
        cache_manager,
        cfg: ScheduleConfig,
        now_ts: Optional[float] = None,
    ) -> None:
        now = float(now_ts) if now_ts is not None else datetime.now().timestamp()
        next_dt = compute_next_run(cfg, now=datetime.fromtimestamp(now))
        cache_manager.update_scan_job_runtime(
            "default",
            last_run_at=now,
            last_status="skipped",
            last_message="no_folders",
            next_run_at=(next_dt.timestamp() if next_dt else None),
        )

    def record_skip_no_valid_folders(
        self,
        *,
        cache_manager,
        cfg: ScheduleConfig,
        now_ts: Optional[float] = None,
    ) -> None:
        now = float(now_ts) if now_ts is not None else datetime.now().timestamp()
        next_dt = compute_next_run(cfg, now=datetime.fromtimestamp(now))
        cache_manager.update_scan_job_runtime(
            "default",
            last_run_at=now,
            last_status="skipped",
            last_message="no_valid_folders",
            next_run_at=(next_dt.timestamp() if next_dt else None),
        )

    def build_run_context(
        self,
        job: dict,
        *,
        cfg: ScheduleConfig,
        scan_config: dict,
        valid_folders: list[str],
        missing_folders: list[str],
    ) -> ScheduledRunContext:
        snap_cfg = dict(scan_config or {})
        return ScheduledRunContext(
            output_dir=str(job.get("output_dir") or "").strip(),
            output_json=bool(job.get("output_json")),
            output_csv=bool(job.get("output_csv")),
            schedule_type=str(cfg.schedule_type or "daily"),
            weekday=int(cfg.weekday or 0),
            time_hhmm=str(cfg.time_hhmm or "03:00"),
            snapshot_config_hash=self._normalize_for_hash(snap_cfg),
            snapshot_folders=tuple(valid_folders or []),
            missing_folders=tuple(missing_folders or []),
        )

    @staticmethod
    def create_job_run(*, cache_manager, session_id: Optional[int]) -> int:
        return int(
            cache_manager.create_scan_job_run(
                "default",
                session_id=int(session_id or 0),
                status="running",
            )
            or 0
        )

    def finalize_run(
        self,
        *,
        cache_manager,
        run_id: int,
        cfg: ScheduleConfig,
        status: str,
        message: str,
        groups_count: int,
        files_count: int,
        output_json_path: str = "",
        output_csv_path: str = "",
        now_ts: Optional[float] = None,
    ) -> None:
        now = float(now_ts) if now_ts is not None else datetime.now().timestamp()
        if run_id:
            cache_manager.finish_scan_job_run(
                int(run_id),
                status=status,
                message=message,
                groups_count=int(groups_count or 0),
                files_count=int(files_count or 0),
                output_json_path=str(output_json_path or ""),
                output_csv_path=str(output_csv_path or ""),
            )
        next_dt = compute_next_run(cfg, now=datetime.fromtimestamp(now))
        cache_manager.update_scan_job_runtime(
            "default",
            last_run_at=now,
            next_run_at=next_dt.timestamp() if next_dt else None,
            last_status=status,
            last_message=message,
        )
