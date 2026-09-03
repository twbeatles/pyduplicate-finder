from __future__ import annotations

import hashlib
import os
import pytest
from src.core.native.bridge import hash_file, hash_files_batch, is_rust_available
from src.core.scanner.hashing import ScanHashingMixin


class DummyCacheManager:
    def get_cached_hash(self, filepath, size, mtime):
        return None


class DummyWorker(ScanHashingMixin):
    def __init__(self):
        import threading
        self.cache_manager = DummyCacheManager()
        self._stop_event = threading.Event()
        self.scan_backend = "python"
        self._rust_cancel_token = None

    def _record_scan_error(self, *args, **kwargs):
        pass


@pytest.fixture
def python_worker():
    return DummyWorker()


@pytest.mark.skipif(not is_rust_available(), reason="pydup_core is not compiled")
class TestHashParity:
    @pytest.mark.parametrize(
        "file_size,name",
        [
            (0, "zero.bin"),
            (100, "small.bin"),
            (4096, "4k.bin"),
            (8192, "8k_exact.bin"),
            (8193, "8k_plus1.bin"),
            (16384, "16k.bin"),
            (10 * 1024 * 1024 - 1024, "just_under_10m.bin"),
            (10 * 1024 * 1024 + 1024, "just_over_10m.bin"),
            (100, "한글_파일명_테스트.bin"),
            (100, "unicode_🚀_test.bin"),
        ],
    )
    def test_full_and_partial_hash_parity(self, tmp_path, python_worker, file_size, name):
        fp = tmp_path / name
        data = bytearray(os.urandom(file_size)) if file_size > 0 else b""
        fp.write_bytes(data)
        filepath = str(fp)

        # 1. Full hash parity
        py_full, _ = python_worker.get_file_hash(filepath, partial=False)
        rust_full, err = hash_file(filepath, partial=False)
        assert err is None
        assert py_full == rust_full, f"Full hash mismatch for size {file_size}: {py_full} != {rust_full}"

        # 2. Partial hash parity
        py_partial, _ = python_worker.get_file_hash(filepath, partial=True)
        rust_partial, err = hash_file(filepath, partial=True)
        assert err is None
        assert py_partial == rust_partial, f"Partial hash mismatch for size {file_size}: {py_partial} != {rust_partial}"

    def test_partial_collision_full_mismatch(self, tmp_path, python_worker):
        """Two files with identical head 4096 and tail 4096, but different middle bytes."""
        size = 20 * 1024  # 20 KB
        head = os.urandom(4096)
        tail = os.urandom(4096)
        mid_a = b"\x00" * (size - 8192)
        mid_b = b"\xff" * (size - 8192)

        fa = tmp_path / "a.bin"
        fb = tmp_path / "b.bin"
        fa.write_bytes(head + mid_a + tail)
        fb.write_bytes(head + mid_b + tail)

        py_part_a, _ = python_worker.get_file_hash(str(fa), partial=True)
        py_part_b, _ = python_worker.get_file_hash(str(fb), partial=True)
        assert py_part_a == py_part_b, "Partial hashes should collide"

        rust_part_a, _ = hash_file(str(fa), partial=True)
        rust_part_b, _ = hash_file(str(fb), partial=True)
        assert rust_part_a == rust_part_b, "Rust partial hashes should collide"
        assert py_part_a == rust_part_a
        assert py_part_b == rust_part_b

        # Full hashes must differ
        py_full_a, _ = python_worker.get_file_hash(str(fa), partial=False)
        py_full_b, _ = python_worker.get_file_hash(str(fb), partial=False)
        rust_full_a, _ = hash_file(str(fa), partial=False)
        rust_full_b, _ = hash_file(str(fb), partial=False)
        assert py_full_a != py_full_b
        assert rust_full_a != rust_full_b
        assert py_full_a == rust_full_a
        assert py_full_b == rust_full_b

    def test_batch_hashing_parity(self, tmp_path, python_worker):
        """Verify hash_files_batch against python get_file_hash."""
        items = []
        expected = []
        for i in range(20):
            fp = tmp_path / f"batch_{i}.bin"
            data = f"batch-data-{i}".encode("utf-8") * 500
            fp.write_bytes(data)
            stat = fp.stat()
            items.append((str(fp), stat.st_size, stat.st_mtime))
            py_h, _ = python_worker.get_file_hash(str(fp), size=stat.st_size, mtime=stat.st_mtime, partial=False)
            expected.append(py_h)

        results = hash_files_batch(items, partial=False, max_workers=4)
        assert len(results) == len(items)
        for r, exp in zip(results, expected):
            assert r.status == "ok"
            assert r.digest == exp
