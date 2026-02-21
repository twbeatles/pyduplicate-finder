import pytest
from PySide6.QtWidgets import QApplication

from src.ui.main_window import DuplicateFinderApp
import src.ui.main_window as mw_module


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


def test_selection_methods_do_not_requery_fs_mtime(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    try:
        p1 = str(tmp_path / "a.txt")
        p2 = str(tmp_path / "b.txt")
        results = {("hash_x", 10): [p1, p2]}
        file_meta = {p1: (10, 100.0), p2: (10, 200.0)}
        exists = {p1: True, p2: True}
        w.scan_results = results
        w._render_results(results, selected_paths=[], file_meta=file_meta, existence_map=exists, selected_count=0)

        def fail_getmtime(_path):
            raise AssertionError("os.path.getmtime should not be called by selection methods")

        monkeypatch.setattr(mw_module.os.path, "getmtime", fail_getmtime)

        w.select_duplicates_smart()
        w.select_duplicates_newest()
        w.select_duplicates_oldest()
    finally:
        w.close()
