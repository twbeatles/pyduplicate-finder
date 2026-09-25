from __future__ import annotations

import os
from pathlib import Path
import pytest

from src.core.scanner import ScanWorker
from src.core.native.bridge import is_rust_available


def _create_test_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    
    # 1. Exact duplicate group 1 (small files)
    d1 = root / "dir1"
    d1.mkdir(exist_ok=True)
    (d1 / "f1.txt").write_text("common content 1", encoding="utf-8")
    (d1 / "f2.txt").write_text("common content 1", encoding="utf-8")

    # 2. Exact duplicate group 2 (medium files, 16KB)
    d2 = root / "dir2"
    d2.mkdir(exist_ok=True)
    payload_16k = b"A" * 16384
    (d2 / "f16_a.bin").write_bytes(payload_16k)
    (d2 / "f16_b.bin").write_bytes(payload_16k)
    (d2 / "f16_c.bin").write_bytes(payload_16k)

    # 3. Same size, different content (should not group)
    (d2 / "diff_a.bin").write_bytes(b"B" * 16384)

    # 4. Unique file
    (root / "unique.txt").write_text("unique content", encoding="utf-8")

    # 5. Korean filename duplicate
    d3 = root / "한국어폴더"
    d3.mkdir(exist_ok=True)
    (d3 / "테스트1.txt").write_text("한글 중복 내용", encoding="utf-8")
    (d3 / "테스트2.txt").write_text("한글 중복 내용", encoding="utf-8")


@pytest.mark.skipif(not is_rust_available(), reason="pydup_core is not compiled")
class TestScanParity:
    def test_full_scan_parity(self, tmp_path):
        data_dir = tmp_path / "data"
        _create_test_dataset(data_dir)

        # 1. Run Python backend scan
        w_py = ScanWorker([str(data_dir)], scan_backend="python", max_workers=2)
        holder_py = {}
        w_py.scan_finished.connect(lambda r: holder_py.__setitem__("res", dict(r or {})))
        w_py.run()
        res_py = holder_py.get("res", {})

        # 2. Run Rust backend scan
        w_rust = ScanWorker([str(data_dir)], scan_backend="rust", max_workers=2)
        holder_rust = {}
        w_rust.scan_finished.connect(lambda r: holder_rust.__setitem__("res", dict(r or {})))
        w_rust.run()
        res_rust = holder_rust.get("res", {})

        # Canonicalize groups: sort paths in each group, sort groups by size/paths
        def canonicalize(res):
            canon = {}
            for (digest, size), paths in res.items():
                canon[(size, digest)] = sorted(paths)
            return canon

        c_py = canonicalize(res_py)
        c_rust = canonicalize(res_rust)

        assert c_py == c_rust, f"Scan result parity mismatch:\nPython: {c_py}\nRust:   {c_rust}"

    def test_byte_compare_scan_parity(self, tmp_path):
        data_dir = tmp_path / "data_bc"
        _create_test_dataset(data_dir)

        w_py = ScanWorker([str(data_dir)], scan_backend="python", byte_compare=True, max_workers=2)
        holder_py = {}
        w_py.scan_finished.connect(lambda r: holder_py.__setitem__("res", dict(r or {})))
        w_py.run()
        res_py = holder_py.get("res", {})

        w_rust = ScanWorker([str(data_dir)], scan_backend="rust", byte_compare=True, max_workers=2)
        holder_rust = {}
        w_rust.scan_finished.connect(lambda r: holder_rust.__setitem__("res", dict(r or {})))
        w_rust.run()
        res_rust = holder_rust.get("res", {})

        assert len(res_py) == len(res_rust)
        for k in res_py:
            assert sorted(res_py[k]) == sorted(res_rust[k])
