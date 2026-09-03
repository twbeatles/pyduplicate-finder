from __future__ import annotations

import os
from pathlib import Path
import pytest

from src.core.native.bridge import discover_files, is_rust_available
from src.core.scanner import ScanWorker


def _setup_discovery_fixtures(root: Path):
    root.mkdir(parents=True, exist_ok=True)

    # 1. Normal files
    (root / "file1.txt").write_text("content 1", encoding="utf-8")
    (root / "file2.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "file3.doc").write_text("doc content", encoding="utf-8")

    # 2. Nested directory
    sub = root / "sub_dir"
    sub.mkdir(exist_ok=True)
    (sub / "nested.txt").write_text("nested content", encoding="utf-8")
    (sub / "temp_file.tmp").write_text("temporary", encoding="utf-8")

    # 3. Hidden / system files
    (root / ".hidden_dot").write_text("hidden", encoding="utf-8")
    (root / "thumbs.db").write_text("thumbs", encoding="utf-8")
    (root / "desktop.ini").write_text("desktop", encoding="utf-8")
    (root / ".DS_Store").write_text("ds_store", encoding="utf-8")

    # 4. Korean path
    korean_dir = root / "한국어_디렉토리"
    korean_dir.mkdir(exist_ok=True)
    (korean_dir / "한글_문서.txt").write_text("한글 내용", encoding="utf-8")

    # 5. Hardlink (if supported by filesystem)
    src_file = root / "file1.txt"
    hardlink_file = root / "file1_hardlink.txt"
    try:
        os.link(str(src_file), str(hardlink_file))
    except (OSError, NotImplementedError):
        pass


@pytest.mark.skipif(not is_rust_available(), reason="pydup_core is not compiled")
class TestDiscoveryParity:
    def test_basic_discovery_parity(self, tmp_path):
        fixtures_dir = tmp_path / "fixtures"
        _setup_discovery_fixtures(fixtures_dir)

        w_py = ScanWorker([str(fixtures_dir)], scan_backend="python", skip_hidden=False)
        size_map_py = w_py._scan_files()
        meta_py = dict(w_py._file_meta)

        w_rust = ScanWorker([str(fixtures_dir)], scan_backend="rust", skip_hidden=False)
        size_map_rust = w_rust._scan_files()
        meta_rust = dict(w_rust._file_meta)

        # Normalize paths for platform comparison
        norm_meta_py = {os.path.normpath(p): (s, round(m, 3)) for p, (s, m) in meta_py.items()}
        norm_meta_rust = {os.path.normpath(p): (s, round(m, 3)) for p, (s, m) in meta_rust.items()}

        assert set(norm_meta_py.keys()) == set(norm_meta_rust.keys())
        for p in norm_meta_py:
            assert norm_meta_py[p][0] == norm_meta_rust[p][0], f"Size mismatch for {p}"
            assert abs(norm_meta_py[p][1] - norm_meta_rust[p][1]) <= 0.002, f"mtime mismatch for {p}"

        # Size maps must contain exact same paths
        norm_size_py = {s: sorted(os.path.normpath(p) for p in paths) for s, paths in size_map_py.items()}
        norm_size_rust = {s: sorted(os.path.normpath(p) for p in paths) for s, paths in size_map_rust.items()}
        assert norm_size_py == norm_size_rust

    def test_skip_hidden_parity(self, tmp_path):
        fixtures_dir = tmp_path / "fixtures_hidden"
        _setup_discovery_fixtures(fixtures_dir)

        w_py = ScanWorker([str(fixtures_dir)], scan_backend="python", skip_hidden=True)
        w_py._scan_files()
        files_py = {os.path.normpath(p) for p in w_py._file_meta}

        w_rust = ScanWorker([str(fixtures_dir)], scan_backend="rust", skip_hidden=True)
        w_rust._scan_files()
        files_rust = {os.path.normpath(p) for p in w_rust._file_meta}

        assert files_py == files_rust
        for p in files_rust:
            name = os.path.basename(p).lower()
            assert not name.startswith(".")
            assert name not in ("thumbs.db", "desktop.ini", ".ds_store")

    def test_extension_and_pattern_filtering_parity(self, tmp_path):
        fixtures_dir = tmp_path / "fixtures_filter"
        _setup_discovery_fixtures(fixtures_dir)

        # Filter txt files, exclude *temp*
        w_py = ScanWorker(
            [str(fixtures_dir)],
            scan_backend="python",
            extensions=["txt"],
            exclude_patterns=["*temp*"],
            skip_hidden=True,
        )
        w_py._scan_files()
        files_py = {os.path.normpath(p) for p in w_py._file_meta}

        w_rust = ScanWorker(
            [str(fixtures_dir)],
            scan_backend="rust",
            extensions=["txt"],
            exclude_patterns=["*temp*"],
            skip_hidden=True,
        )
        w_rust._scan_files()
        files_rust = {os.path.normpath(p) for p in w_rust._file_meta}

        assert files_py == files_rust
        for p in files_rust:
            assert p.endswith(".txt")
            assert "temp" not in p.lower()
