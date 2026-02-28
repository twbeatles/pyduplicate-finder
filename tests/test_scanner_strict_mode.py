import pytest

from src.core.cache_manager import CacheManager
from src.core.scanner import ScanWorker


@pytest.mark.parametrize(
    "strict_mode,strict_max_errors,errors_total,expected_status",
    [
        (False, 0, 2, "completed"),
        (True, 2, 2, "completed"),
        (True, 1, 2, "partial"),
    ],
)
def test_strict_mode_threshold_status_persisted(
    tmp_path,
    monkeypatch,
    strict_mode,
    strict_max_errors,
    errors_total,
    expected_status,
):
    db_path = tmp_path / "scan_cache.db"
    monkeypatch.setenv("PYDUPLICATEFINDER_DB_PATH", str(db_path))

    cm = CacheManager(db_path=str(db_path))
    try:
        sid = cm.create_scan_session({"folders": [str(tmp_path)]})
        worker = ScanWorker(
            [str(tmp_path)],
            session_id=sid,
            protect_system=False,
            max_workers=1,
            strict_mode=strict_mode,
            strict_max_errors=strict_max_errors,
        )

        def fake_scan_files():
            worker._file_meta = {
                "a.bin": (1, 1.0),
                "b.bin": (1, 1.0),
            }
            worker._metrics["errors_total"] = int(errors_total)
            worker._metrics["files_skipped_error"] = int(errors_total)
            return {1: ["a.bin", "b.bin"]}

        worker._scan_files = fake_scan_files
        worker._calculate_hashes_parallel = (
            lambda _candidates, is_quick_scan=True, seed_session_id=None: {(1, "full", "FULL"): ["a.bin", "b.bin"]}
        )

        finished = {"flag": False}
        worker.scan_finished.connect(lambda _results: finished.__setitem__("flag", True))
        worker.run()

        latest = cm.get_latest_session()
        assert finished["flag"] is True
        assert worker.latest_scan_status == expected_status
        assert latest is not None
        assert latest["status"] == expected_status
    finally:
        cm.close_all()
