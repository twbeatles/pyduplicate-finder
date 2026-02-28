import os

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.main_window import DuplicateFinderApp


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_scan_hash_config_canonicalization(tmp_path, monkeypatch, qapp):
    _ = qapp
    monkeypatch.setenv("PYDUPLICATEFINDER_DB_PATH", str(tmp_path / "scan_cache.db"))

    folder_a = tmp_path / "A"
    folder_b = tmp_path / "B"
    folder_a.mkdir()
    folder_b.mkdir()

    app = DuplicateFinderApp()
    try:
        try:
            app._scheduler_timer.stop()
        except Exception:
            pass

        config_a = {
            "folders": [str(folder_b), str(folder_a)],
            "extensions": " .txt, jpg, .TXT , .jpg ",
            "include_patterns": [" *.pdf ", "*.txt"],
            "exclude_patterns": ["  *.tmp", "node_modules "],
            "use_trash": True,
            "incremental_rescan": True,
            "baseline_session_id": 123,
            "name_only": False,
            "use_similar_image": False,
            "use_mixed_mode": False,
            "detect_duplicate_folders": True,
        }
        config_b = {
            "folders": [os.path.join(str(folder_a), "."), str(folder_b)],
            "extensions": ["jpg", "txt", ".jpg", ".txt"],
            "include_patterns": ["*.txt", "*.pdf"],
            "exclude_patterns": ["node_modules", "*.tmp"],
            "use_trash": False,
            "incremental_rescan": False,
            "baseline_session_id": 0,
            "name_only": False,
            "use_similar_image": False,
            "use_mixed_mode": True,
            "detect_duplicate_folders": True,
        }

        hash_cfg_a = app._get_scan_hash_config(config_a)
        hash_cfg_b = app._get_scan_hash_config(config_b)

        assert hash_cfg_a == hash_cfg_b
        assert app.cache_manager.get_config_hash(hash_cfg_a) == app.cache_manager.get_config_hash(hash_cfg_b)
    finally:
        app.close()
