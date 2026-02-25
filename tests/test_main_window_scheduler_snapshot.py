import json

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.main_window import DuplicateFinderApp


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _setup_window(tmp_path, monkeypatch):
    monkeypatch.setenv("PYDUPLICATEFINDER_DB_PATH", str(tmp_path / "scan_cache.db"))
    w = DuplicateFinderApp()
    try:
        w._scheduler_timer.stop()
    except Exception:
        pass
    return w


def test_scheduler_tick_uses_snapshot_config_not_ui_state(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        valid = tmp_path / "valid"
        valid.mkdir()
        missing = tmp_path / "missing"

        w.selected_folders = [str(tmp_path / "ui_only")]
        due_cfg = w.scheduler_controller.build_config(
            enabled=True,
            schedule_type="daily",
            weekday=0,
            time_hhmm="03:00",
        )
        job = {
            "enabled": True,
            "schedule_type": "daily",
            "weekday": 0,
            "time_hhmm": "03:00",
            "output_dir": str(tmp_path),
            "output_json": True,
            "output_csv": True,
            "config_json": json.dumps(
                {
                    "folders": [str(valid), str(missing)],
                    "extensions": "jpg,png",
                    "min_size_kb": 123,
                    "protect_system": True,
                    "byte_compare": False,
                    "same_name": False,
                    "name_only": False,
                    "skip_hidden": True,
                    "follow_symlinks": False,
                    "include_patterns": [],
                    "exclude_patterns": [],
                    "use_trash": False,
                    "use_similar_image": False,
                    "use_mixed_mode": False,
                    "detect_duplicate_folders": False,
                    "incremental_rescan": False,
                    "baseline_session_id": 0,
                    "similarity_threshold": 0.9,
                }
            ),
        }

        def fake_get_due_job(*, cache_manager, is_scanning, now_ts=None):
            return job, due_cfg

        monkeypatch.setattr(w.scheduler_controller, "get_due_job", fake_get_due_job)

        captured = {}

        def fake_start_scan(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(w, "start_scan", fake_start_scan)

        w._scheduler_tick()

        assert captured
        assert captured["force_new"] is False
        assert captured["folders_override"] == [str(valid.resolve())]
        assert captured["config_override"]["folders"] == [str(valid.resolve())]
        assert captured["config_override"]["extensions"] == "jpg,png"

        ctx = captured["scheduled_context"]
        assert ctx["snapshot_folders"] == [str(valid.resolve())]
        assert ctx["missing_folders"] == [str(missing.resolve())]
    finally:
        w.close()


def test_scheduler_tick_skips_when_snapshot_folders_all_missing(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        missing = tmp_path / "missing_only"
        due_cfg = w.scheduler_controller.build_config(
            enabled=True,
            schedule_type="daily",
            weekday=0,
            time_hhmm="03:00",
        )
        job = {
            "enabled": True,
            "schedule_type": "daily",
            "weekday": 0,
            "time_hhmm": "03:00",
            "output_dir": str(tmp_path),
            "output_json": True,
            "output_csv": False,
            "config_json": json.dumps({"folders": [str(missing)]}),
        }

        def fake_get_due_job(*, cache_manager, is_scanning, now_ts=None):
            return job, due_cfg

        monkeypatch.setattr(w.scheduler_controller, "get_due_job", fake_get_due_job)

        called = {"n": 0}

        def fake_skip(*, cache_manager, cfg, now_ts=None):
            called["n"] += 1

        monkeypatch.setattr(w.scheduler_controller, "record_skip_no_valid_folders", fake_skip)

        def fail_start_scan(**_kwargs):
            raise AssertionError("start_scan should not be called when all snapshot folders are missing")

        monkeypatch.setattr(w, "start_scan", fail_start_scan)

        w._scheduler_tick()
        assert called["n"] == 1
        assert w._scheduled_run_context is None
        assert w._scheduled_job_run_id == 0
    finally:
        w.close()
