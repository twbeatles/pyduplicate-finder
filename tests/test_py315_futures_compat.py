"""Python 3.15 lazy-stdlib compatibility for scanner thread pools.

Python 3.15 declares ``ThreadPoolExecutor``/``ProcessPoolExecutor`` as lazy
imports in ``concurrent.futures``. Accessing them through the
``import concurrent.futures`` + attribute style can stay an un-callable
``lazy_import`` placeholder once the Qt bindings are loaded, so the scanner
must bind the executor names eagerly with ``from ... import``.
"""

import os

from src.core.scanner import ScanWorker


def test_hash_parallel_path_resolves_thread_pool(tmp_path, monkeypatch):
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"same-content")
    second.write_bytes(b"same-content")

    candidates = []
    for path in (first, second):
        stat = os.stat(path)
        candidates.append((str(path), int(stat.st_size), float(stat.st_mtime)))

    worker = ScanWorker([str(tmp_path)], protect_system=False, max_workers=1)
    try:

        def fake_get_file_hash(filepath, size=None, mtime=None, block_size=0, partial=False):
            _ = (size, mtime, block_size, partial)
            return ("digest-same", True)

        monkeypatch.setattr(worker, "get_file_hash", fake_get_file_hash)
        hash_map = worker._calculate_hashes_parallel(candidates, is_quick_scan=True)

        assert len(hash_map) == 1
        grouped = next(iter(hash_map.values()))
        assert sorted(grouped) == sorted([str(first), str(second)])
    finally:
        worker.cache_manager.close_all()
