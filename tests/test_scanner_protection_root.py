from src.core.scanner import ScanWorker


def test_protected_root_folder_is_skipped(tmp_path, monkeypatch):
    (tmp_path / "inside.txt").write_text("x", encoding="utf-8")

    worker = ScanWorker([str(tmp_path)], protect_system=True, max_workers=1)
    try:
        monkeypatch.setattr(worker, "is_protected", lambda _path: True)
        size_map = worker._scan_files()

        assert not worker._file_meta
        assert sum(len(paths) for paths in size_map.values()) == 0
    finally:
        worker.cache_manager.close_all()
