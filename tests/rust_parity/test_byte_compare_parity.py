from __future__ import annotations

import os
import pytest
from src.core.native.bridge import compare_files_byte_by_byte, is_rust_available
from src.core.scanner.hashing import ScanHashingMixin


class DummyWorker(ScanHashingMixin):
    def __init__(self):
        import threading
        self._stop_event = threading.Event()
        self.scan_backend = "python"
        self._rust_cancel_token = None


@pytest.fixture
def python_worker():
    return DummyWorker()


@pytest.mark.skipif(not is_rust_available(), reason="pydup_core is not compiled")
class TestByteCompareParity:
    def test_identical_files(self, tmp_path, python_worker):
        fa = tmp_path / "a.bin"
        fb = tmp_path / "b.bin"
        data = os.urandom(1024 * 512)
        fa.write_bytes(data)
        fb.write_bytes(data)

        py_res = python_worker.compare_files_byte_by_byte(str(fa), str(fb))
        rust_res = compare_files_byte_by_byte(str(fa), str(fb))

        assert py_res is True
        assert rust_res is True
        assert py_res == rust_res

    def test_different_sizes(self, tmp_path, python_worker):
        fa = tmp_path / "a.bin"
        fb = tmp_path / "b.bin"
        fa.write_bytes(b"hello world")
        fb.write_bytes(b"hello world!")

        py_res = python_worker.compare_files_byte_by_byte(str(fa), str(fb))
        rust_res = compare_files_byte_by_byte(str(fa), str(fb))

        assert py_res is False
        assert rust_res is False

    def test_same_size_different_content(self, tmp_path, python_worker):
        fa = tmp_path / "a.bin"
        fb = tmp_path / "b.bin"
        fa.write_bytes(b"A" * 1000)
        fb.write_bytes(b"B" * 1000)

        py_res = python_worker.compare_files_byte_by_byte(str(fa), str(fb))
        rust_res = compare_files_byte_by_byte(str(fa), str(fb))

        assert py_res is False
        assert rust_res is False

    def test_large_file_single_byte_difference(self, tmp_path, python_worker):
        size = 2 * 1024 * 1024  # 2 MiB
        data_a = bytearray(b"X" * size)
        data_b = bytearray(b"X" * size)
        data_b[size // 2] = ord("Y")

        fa = tmp_path / "large_a.bin"
        fb = tmp_path / "large_b.bin"
        fa.write_bytes(data_a)
        fb.write_bytes(data_b)

        py_res = python_worker.compare_files_byte_by_byte(str(fa), str(fb))
        rust_res = compare_files_byte_by_byte(str(fa), str(fb))

        assert py_res is False
        assert rust_res is False
