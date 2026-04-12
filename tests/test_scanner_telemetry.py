import errno
import os

from src.core.scanner import ScanWorker


def test_hash_errors_are_counted_in_telemetry(tmp_path, monkeypatch):
    good = tmp_path / "good.bin"
    locked = tmp_path / "locked.bin"
    bad = tmp_path / "bad.bin"
    good.write_bytes(b"good")
    locked.write_bytes(b"locked")
    bad.write_bytes(b"bad")

    worker = ScanWorker([str(tmp_path)], protect_system=False, max_workers=1)
    try:
        candidates = []
        for path in (good, locked, bad):
            st = os.stat(path)
            candidates.append((str(path), int(st.st_size), float(st.st_mtime)))

        def fake_get_file_hash(filepath, size=None, mtime=None, block_size=0, partial=False):
            _ = (size, mtime, block_size, partial)
            if filepath.endswith("locked.bin"):
                raise PermissionError("locked")
            if filepath.endswith("bad.bin"):
                raise OSError(errno.EIO, "io error")
            return ("digest", True)

        monkeypatch.setattr(worker, "get_file_hash", fake_get_file_hash)
        worker._calculate_hashes_parallel(candidates, is_quick_scan=True)

        metrics = worker._snapshot_metrics()
        assert int(metrics.get("files_hashed", 0)) == 1
        assert int(metrics.get("files_skipped_locked", 0)) == 1
        assert int(metrics.get("files_skipped_error", 0)) == 1
        assert int(metrics.get("errors_total", 0)) == 2
    finally:
        worker.cache_manager.close_all()


def test_similar_image_hash_errors_are_counted_in_telemetry(tmp_path):
    ok = tmp_path / "ok.jpg"
    bad = tmp_path / "bad.jpg"
    ok.write_bytes(b"ok")
    bad.write_bytes(b"bad")

    class DummyHasher:
        SUPPORTED_EXTENSIONS = {".jpg"}

        @staticmethod
        def calculate_phash(path: str):
            if path.endswith("bad.jpg"):
                raise PermissionError("locked image")
            return "abc123"

        @staticmethod
        def group_similar_images(hash_results, threshold=0.9, progress_callback=None, check_cancel=None):
            _ = (threshold, check_cancel)
            if progress_callback:
                progress_callback(1, max(1, len(hash_results)))
            return [list(hash_results.keys())] if len(hash_results) >= 2 else []

    worker = ScanWorker([str(tmp_path)], protect_system=False, max_workers=1)
    worker.use_similar_image = True
    setattr(worker, "image_hasher", DummyHasher())
    try:
        worker._run_similar_image_scan(image_files=[str(ok), str(bad)], emit_result=False)
        metrics = worker._snapshot_metrics()
        assert int(metrics.get("files_hashed", 0)) == 1
        assert int(metrics.get("files_skipped_locked", 0)) == 1
        assert int(metrics.get("errors_total", 0)) == 1
    finally:
        worker.cache_manager.close_all()


def test_zero_byte_duplicates_are_detected_when_min_size_is_zero(tmp_path):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_bytes(b"")
    right.write_bytes(b"")

    worker = ScanWorker([str(tmp_path)], protect_system=False, max_workers=1, min_size_kb=0)
    captured = {"results": None}
    worker.scan_finished.connect(lambda results: captured.__setitem__("results", results))
    try:
        worker.run()
        results = dict(captured["results"] or {})
        assert len(results) == 1
        paths = next(iter(results.values()))
        assert sorted(paths) == sorted([str(left), str(right)])
    finally:
        worker.cache_manager.close_all()


def test_zero_byte_duplicates_are_kept_in_cached_file_collection(tmp_path, monkeypatch):
    left = tmp_path / "left_cached.txt"
    right = tmp_path / "right_cached.txt"
    left.write_bytes(b"")
    right.write_bytes(b"")

    worker = ScanWorker([str(tmp_path)], protect_system=False, max_workers=1, min_size_kb=0)
    try:
        size_map = worker._scan_files_from_cache(
            [
                (str(left), 0, float(left.stat().st_mtime)),
                (str(right), 0, float(right.stat().st_mtime)),
            ]
        )
        assert 0 in size_map
        assert sorted(size_map[0]) == sorted([str(left), str(right)])
    finally:
        worker.cache_manager.close_all()
