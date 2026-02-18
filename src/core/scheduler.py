from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class ScheduleConfig:
    enabled: bool = False
    schedule_type: str = "daily"  # daily|weekly
    weekday: int = 0  # 0=Monday .. 6=Sunday
    time_hhmm: str = "03:00"


def _parse_hhmm(value: str) -> tuple[int, int]:
    raw = str(value or "03:00").strip()
    try:
        hh, mm = raw.split(":", 1)
        h = max(0, min(23, int(hh)))
        m = max(0, min(59, int(mm)))
        return h, m
    except Exception:
        return (3, 0)


def compute_next_run(cfg: ScheduleConfig, *, now: Optional[datetime] = None) -> Optional[datetime]:
    if not cfg.enabled:
        return None
    ref = now or datetime.now()
    h, m = _parse_hhmm(cfg.time_hhmm)
    target = ref.replace(hour=h, minute=m, second=0, microsecond=0)

    if str(cfg.schedule_type or "daily") == "weekly":
        weekday = max(0, min(6, int(cfg.weekday or 0)))
        days_ahead = (weekday - target.weekday()) % 7
        target = target + timedelta(days=days_ahead)
        if target <= ref:
            target = target + timedelta(days=7)
        return target

    # daily
    if target <= ref:
        target = target + timedelta(days=1)
    return target


def is_due(cfg: ScheduleConfig, *, last_run_at: Optional[float], now_ts: Optional[float] = None) -> bool:
    if not cfg.enabled:
        return False
    now = datetime.fromtimestamp(now_ts) if now_ts is not None else datetime.now()
    # Compute the most recent scheduled point and compare with last_run_at.
    h, m = _parse_hhmm(cfg.time_hhmm)
    slot = now.replace(hour=h, minute=m, second=0, microsecond=0)

    if str(cfg.schedule_type or "daily") == "weekly":
        weekday = max(0, min(6, int(cfg.weekday or 0)))
        days_back = (slot.weekday() - weekday) % 7
        slot = slot - timedelta(days=days_back)
        if slot > now:
            slot = slot - timedelta(days=7)
    else:
        if slot > now:
            slot = slot - timedelta(days=1)

    slot_ts = slot.timestamp()
    if not last_run_at:
        return now.timestamp() >= slot_ts
    return float(last_run_at) < slot_ts <= now.timestamp()

