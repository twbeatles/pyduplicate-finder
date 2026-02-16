import os

from src.core.cache_manager import CacheManager
from src.core.scanner import ScanWorker
import src.core.scanner as scanner_module


def test_hash_path_does_not_restat_candidates(tmp_path, monkeypatch):
    p = tmp_path / "a.bin"
    p.write_bytes(b"x" * 64)
    stat = p.stat()
    candidates = [(str(p), int(stat.st_size), float(stat.st_mtime))]

    target = os.path.normcase(str(p))
    real_stat = scanner_module.os.stat
    calls = {"count": 0}

    def tracked_stat(path, *args, **kwargs):
        if os.path.normcase(str(path)) == target:
            calls["count"] += 1
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(scanner_module.os, "stat", tracked_stat)

    worker = ScanWorker([str(tmp_path)], max_workers=1)
    out = worker._calculate_hashes_parallel(candidates, is_quick_scan=True)
    worker.cache_manager.close_all()

    assert calls["count"] == 0
    assert any(str(p) in paths for paths in out.values())


def test_cancelled_run_marks_session_paused(tmp_path, monkeypatch):
    db_path = tmp_path / "scan_cache.db"
    monkeypatch.setenv("PYDUPLICATEFINDER_DB_PATH", str(db_path))

    cm = CacheManager(db_path=str(db_path))
    try:
        sid = cm.create_scan_session({"folders": [str(tmp_path)]})
        worker = ScanWorker([str(tmp_path)], session_id=sid, max_workers=1)

        cancelled = {"flag": False}
        worker.scan_cancelled.connect(lambda: cancelled.__setitem__("flag", True))

        def fake_scan_files():
            worker.stop()
            return {}

        worker._scan_files = fake_scan_files
        worker.run()

        session = cm.get_latest_session()
        assert cancelled["flag"] is True
        assert session is not None
        assert int(session["id"]) == int(sid)
        assert session["status"] == "paused"
    finally:
        try:
            cm.close_all()
        except Exception:
            pass
