from datetime import datetime
import json

from src.ui.controllers.scheduler_controller import SchedulerController


class _FakeCache:
    def __init__(self):
        self.job = None
        self.upsert_calls = []
        self.runtime_calls = []
        self.create_run_calls = []
        self.finish_run_calls = []

    def upsert_scan_job(self, **kwargs):
        self.upsert_calls.append(kwargs)
        self.job = {
            "name": kwargs.get("name"),
            "enabled": bool(kwargs.get("enabled")),
            "schedule_type": kwargs.get("schedule_type"),
            "weekday": int(kwargs.get("weekday") or 0),
            "time_hhmm": kwargs.get("time_hhmm"),
            "output_dir": kwargs.get("output_dir") or "",
            "output_json": bool(kwargs.get("output_json")),
            "output_csv": bool(kwargs.get("output_csv")),
            "config_json": kwargs.get("config_json") or "{}",
            "last_run_at": None,
            "next_run_at": kwargs.get("next_run_at"),
            "last_status": None,
            "last_message": None,
            "updated_at": 0,
        }

    def get_scan_job(self, _name):
        return dict(self.job or {})

    def update_scan_job_runtime(self, name, **kwargs):
        self.runtime_calls.append((name, kwargs))
        if self.job:
            self.job.update(kwargs)

    def create_scan_job_run(self, _name, *, session_id=None, status="running"):
        self.create_run_calls.append({"session_id": int(session_id or 0), "status": status})
        return 17

    def finish_scan_job_run(self, run_id, **kwargs):
        self.finish_run_calls.append((int(run_id), kwargs))


def test_scheduler_controller_persist_and_get_due_job():
    c = SchedulerController()
    cache = _FakeCache()
    cfg = c.build_config(enabled=True, schedule_type="daily", weekday=0, time_hhmm="03:00")
    c.persist_job(
        cache_manager=cache,
        cfg=cfg,
        scan_config={"folders": ["D:/Data"]},
        output_dir="D:/out",
        output_json=True,
        output_csv=False,
    )
    assert cache.upsert_calls

    # After scheduled slot and before any run -> due.
    now_ts = datetime(2026, 2, 20, 10, 0, 0).timestamp()
    job, due_cfg = c.get_due_job(cache_manager=cache, is_scanning=False, now_ts=now_ts)
    assert job is not None
    assert due_cfg is not None
    assert due_cfg.enabled is True


def test_scheduler_controller_not_due_before_daily_slot():
    c = SchedulerController()
    cache = _FakeCache()
    cache.job = {
        "enabled": True,
        "schedule_type": "daily",
        "weekday": 0,
        "time_hhmm": "23:00",
        "last_run_at": None,
        "output_dir": "",
        "output_json": True,
        "output_csv": True,
    }
    now_ts = datetime(2026, 2, 20, 10, 0, 0).timestamp()
    job, cfg = c.get_due_job(cache_manager=cache, is_scanning=False, now_ts=now_ts)
    assert job is None
    assert cfg is None


def test_scheduler_controller_skip_no_folders_records_runtime():
    c = SchedulerController()
    cache = _FakeCache()
    cfg = c.build_config(enabled=True, schedule_type="daily", weekday=0, time_hhmm="03:00")
    now_ts = datetime(2026, 2, 20, 10, 0, 0).timestamp()
    c.record_skip_no_folders(cache_manager=cache, cfg=cfg, now_ts=now_ts)

    assert cache.runtime_calls
    _name, payload = cache.runtime_calls[-1]
    assert payload["last_status"] == "skipped"
    assert payload["last_message"] == "no_folders"
    assert float(payload["last_run_at"]) == float(now_ts)


def test_scheduler_controller_skip_no_valid_folders_records_runtime():
    c = SchedulerController()
    cache = _FakeCache()
    cfg = c.build_config(enabled=True, schedule_type="daily", weekday=0, time_hhmm="03:00")
    now_ts = datetime(2026, 2, 20, 10, 0, 0).timestamp()
    c.record_skip_no_valid_folders(cache_manager=cache, cfg=cfg, now_ts=now_ts)

    assert cache.runtime_calls
    _name, payload = cache.runtime_calls[-1]
    assert payload["last_status"] == "skipped"
    assert payload["last_message"] == "no_valid_folders"
    assert float(payload["last_run_at"]) == float(now_ts)


def test_scheduler_controller_parse_scan_config_handles_invalid_json():
    c = SchedulerController()
    assert c.parse_scan_config({"config_json": "{oops"}) == {}
    assert c.parse_scan_config({"config_json": ""}) == {}
    assert c.parse_scan_config({"config_json": []}) == {}


def test_scheduler_controller_parse_and_resolve_snapshot_folders(tmp_path):
    c = SchedulerController()
    valid = tmp_path / "valid"
    valid.mkdir()
    missing = tmp_path / "missing"
    cfg = {
        "folders": [str(valid), str(missing), str(valid)],
        "min_size_kb": 10,
    }
    job = {"config_json": json.dumps(cfg)}
    parsed = c.parse_scan_config(job)
    got_valid, got_missing = c.resolve_snapshot_folders(parsed)

    assert parsed.get("min_size_kb") == 10
    assert got_valid == [str(valid.resolve())]
    assert got_missing == [str(missing.resolve())]


def test_scheduler_controller_finalize_run_updates_both_tables():
    c = SchedulerController()
    cache = _FakeCache()
    cfg = c.build_config(enabled=True, schedule_type="daily", weekday=0, time_hhmm="03:00")
    now_ts = datetime(2026, 2, 20, 10, 0, 0).timestamp()
    c.finalize_run(
        cache_manager=cache,
        run_id=21,
        cfg=cfg,
        status="completed",
        message="completed",
        groups_count=3,
        files_count=10,
        output_json_path="D:/out/scan.json",
        output_csv_path="D:/out/scan.csv",
        now_ts=now_ts,
    )

    assert cache.finish_run_calls
    assert cache.finish_run_calls[-1][0] == 21
    assert cache.runtime_calls
    _name, payload = cache.runtime_calls[-1]
    assert payload["last_status"] == "completed"
    assert payload["last_message"] == "completed"
