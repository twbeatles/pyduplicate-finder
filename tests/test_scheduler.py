from datetime import datetime

from src.core.scheduler import ScheduleConfig, compute_next_run, is_due


def test_compute_next_run_daily_rolls_forward():
    cfg = ScheduleConfig(enabled=True, schedule_type="daily", time_hhmm="03:00")
    now = datetime(2026, 2, 18, 4, 30, 0)
    nxt = compute_next_run(cfg, now=now)
    assert nxt is not None
    assert (nxt.year, nxt.month, nxt.day, nxt.hour, nxt.minute) == (2026, 2, 19, 3, 0)


def test_compute_next_run_weekly_targets_weekday():
    cfg = ScheduleConfig(enabled=True, schedule_type="weekly", weekday=4, time_hhmm="10:15")  # Friday
    now = datetime(2026, 2, 18, 9, 0, 0)  # Wednesday
    nxt = compute_next_run(cfg, now=now)
    assert nxt is not None
    assert nxt.weekday() == 4
    assert (nxt.hour, nxt.minute) == (10, 15)


def test_is_due_daily_compares_with_last_run():
    cfg = ScheduleConfig(enabled=True, schedule_type="daily", time_hhmm="03:00")
    now = datetime(2026, 2, 18, 4, 0, 0).timestamp()
    # Last run before today's slot -> due.
    assert is_due(cfg, last_run_at=datetime(2026, 2, 17, 3, 0, 0).timestamp(), now_ts=now)
    # Last run at/after today's slot -> not due.
    assert not is_due(cfg, last_run_at=datetime(2026, 2, 18, 3, 0, 0).timestamp(), now_ts=now)

