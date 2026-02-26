import pytest
from PySide6.QtWidgets import QApplication

import src.ui.main_window as main_window_module
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


def test_apply_schedule_settings_blocks_invalid_hhmm(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    warned = {"count": 0}
    persisted = {"count": 0}
    try:
        before = str(w.settings.value("schedule/time_hhmm", "03:00"))
        w.txt_schedule_time.setText("25:99")

        def _warn(*_args, **_kwargs):
            warned["count"] += 1
            return 0

        monkeypatch.setattr(main_window_module.QMessageBox, "warning", _warn)
        monkeypatch.setattr(
            w.scheduler_controller,
            "persist_job",
            lambda **_kwargs: persisted.__setitem__("count", persisted["count"] + 1),
        )

        w.apply_schedule_settings()

        assert warned["count"] == 1
        assert persisted["count"] == 0
        assert str(w.settings.value("schedule/time_hhmm", "03:00")) == before
    finally:
        w.close()


def test_apply_schedule_settings_persists_valid_hhmm(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    persisted = {"count": 0}
    try:
        w.txt_schedule_time.setText("09:30")
        monkeypatch.setattr(
            w.scheduler_controller,
            "persist_job",
            lambda **_kwargs: persisted.__setitem__("count", persisted["count"] + 1),
        )

        w.apply_schedule_settings()

        assert persisted["count"] == 1
        assert str(w.settings.value("schedule/time_hhmm", "")) == "09:30"
    finally:
        w.close()
