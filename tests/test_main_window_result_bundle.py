from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

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


def test_load_scan_results_restores_selected_meta_and_missing_state(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        payload_path = tmp_path / "saved_results.json"
        payload_path.write_text(
            """
{
  "version": 2,
  "meta": {
    "scan_status": "partial",
    "metrics": {"errors_total": 2},
    "warnings": ["strict_mode_threshold_exceeded"],
    "selected_paths": ["C:/saved/b.txt"],
    "file_meta": {
      "C:/saved/a.txt": {"size": 10, "mtime": 100.0, "exists": true},
      "C:/saved/b.txt": {"size": 10, "mtime": 200.0, "exists": false}
    },
    "baseline_delta_map": {
      "C:/saved/a.txt": "new",
      "C:/saved/b.txt": "changed"
    }
  },
  "results": {
    "('hash_x', 10)": ["C:/saved/a.txt", "C:/saved/b.txt"]
  }
}
            """.strip(),
            encoding="utf-8",
        )

        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(payload_path), "JSON Files (*.json)"))

        w.load_scan_results()
        qapp.processEvents()

        assert w._last_scan_status == "partial"
        assert w._last_scan_metrics == {"errors_total": 2}
        assert w._last_scan_warnings == ["strict_mode_threshold_exceeded"]
        assert w._current_result_meta["C:/saved/a.txt"] == (10, 100.0)
        assert w._current_result_existence_map["C:/saved/b.txt"] is False
        assert w._current_baseline_delta_map == {
            "C:/saved/a.txt": "new",
            "C:/saved/b.txt": "changed",
        }
        assert set(w.tree_widget.get_checked_files()) == {"C:/saved/b.txt"}
        group = w.tree_widget.invisibleRootItem().child(0)
        assert "[Missing]" in group.child(1).text(0) or "[누락]" in group.child(1).text(0)
    finally:
        w.close()


def test_scan_cancelled_restores_previous_result_metadata(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        rendered = {}

        def fake_render(results, *, selected_paths=None, file_meta=None, existence_map=None, selected_count=None):
            rendered["results"] = results
            rendered["selected_paths"] = list(selected_paths or [])
            rendered["file_meta"] = dict(file_meta or {})
            rendered["existence_map"] = dict(existence_map or {})
            rendered["selected_count"] = selected_count
            w._current_result_meta = dict(file_meta or {})
            w._current_result_existence_map = dict(existence_map or {})

        w._render_results = fake_render
        w._previous_results = {("hash_prev", 1): ["a", "b"]}
        w._previous_selected_paths = ["b"]
        w._previous_result_meta = {"a": (1, 10.0), "b": (1, 11.0)}
        w._previous_result_existence_map = {"a": True, "b": False}
        w._previous_baseline_delta_map = {"a": "new", "b": "changed"}

        w.on_scan_cancelled()

        assert rendered["results"] == {("hash_prev", 1): ["a", "b"]}
        assert rendered["selected_paths"] == ["b"]
        assert rendered["file_meta"] == {"a": (1, 10.0), "b": (1, 11.0)}
        assert rendered["existence_map"] == {"a": True, "b": False}
        assert w._current_baseline_delta_map == {"a": "new", "b": "changed"}
    finally:
        w.close()


def test_scan_failed_restores_previous_result_metadata(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        rendered = {}

        def fake_render(results, *, selected_paths=None, file_meta=None, existence_map=None, selected_count=None):
            rendered["results"] = results
            rendered["selected_paths"] = list(selected_paths or [])
            rendered["file_meta"] = dict(file_meta or {})
            rendered["existence_map"] = dict(existence_map or {})
            rendered["selected_count"] = selected_count
            w._current_result_meta = dict(file_meta or {})
            w._current_result_existence_map = dict(existence_map or {})

        monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
        w._render_results = fake_render
        w._previous_results = {("hash_prev", 1): ["x", "y"]}
        w._previous_selected_paths = ["x"]
        w._previous_result_meta = {"x": (2, 20.0), "y": (2, 21.0)}
        w._previous_result_existence_map = {"x": True, "y": True}
        w._previous_baseline_delta_map = {"x": "revalidated"}

        w.on_scan_failed("boom")

        assert rendered["results"] == {("hash_prev", 1): ["x", "y"]}
        assert rendered["selected_paths"] == ["x"]
        assert rendered["file_meta"] == {"x": (2, 20.0), "y": (2, 21.0)}
        assert rendered["existence_map"] == {"x": True, "y": True}
        assert w._current_baseline_delta_map == {"x": "revalidated"}
    finally:
        w.close()
