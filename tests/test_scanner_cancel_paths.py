from src.core.scanner import ScanWorker


def _connect_signals(worker: ScanWorker):
    state = {"cancelled": False, "finished": False}
    worker.scan_cancelled.connect(lambda: state.__setitem__("cancelled", True))
    worker.scan_finished.connect(lambda _results: state.__setitem__("finished", True))
    return state


def _base_worker(**kwargs) -> ScanWorker:
    worker = ScanWorker(["C:/dummy"], protect_system=False, max_workers=1, **kwargs)

    def fake_scan_files():
        worker._file_meta = {
            "a.bin": (1, 1.0),
            "b.bin": (1, 1.0),
        }
        return {1: ["a.bin", "b.bin"]}

    worker._scan_files = fake_scan_files
    return worker


def test_cancel_during_full_hash_emits_cancel_only():
    worker = _base_worker()
    state = _connect_signals(worker)

    def fake_hashes(_candidates, is_quick_scan=True, seed_session_id=None):
        _ = seed_session_id
        if is_quick_scan:
            return {(1, "quick", "PARTIAL"): ["a.bin", "b.bin"]}
        worker.stop()
        return {}

    worker._calculate_hashes_parallel = fake_hashes
    worker.run()

    assert state["cancelled"] is True
    assert state["finished"] is False


def test_cancel_during_folder_dup_emits_cancel_only():
    worker = _base_worker(detect_duplicate_folders=True)
    state = _connect_signals(worker)
    worker._calculate_hashes_parallel = (
        lambda _candidates, is_quick_scan=True, seed_session_id=None: {(1, "full", "FULL"): ["a.bin", "b.bin"]}
    )

    def fake_detect_folder_dup():
        worker.stop()
        return {}

    worker._detect_duplicate_folders = fake_detect_folder_dup
    worker.run()

    assert state["cancelled"] is True
    assert state["finished"] is False


def test_cancel_during_mixed_mode_emits_cancel_only():
    worker = _base_worker(use_similar_image=True, use_mixed_mode=True)
    # Ensure mixed branch runs even if optional image backend is unavailable in test env.
    worker.use_similar_image = True
    state = _connect_signals(worker)
    worker._calculate_hashes_parallel = (
        lambda _candidates, is_quick_scan=True, seed_session_id=None: {(1, "full", "FULL"): ["a.bin", "b.bin"]}
    )

    def fake_mixed_similar_scan(image_files=None, emit_result=True):
        _ = (image_files, emit_result)
        worker.stop()
        return {}

    worker._run_similar_image_scan = fake_mixed_similar_scan
    worker.run()

    assert state["cancelled"] is True
    assert state["finished"] is False
