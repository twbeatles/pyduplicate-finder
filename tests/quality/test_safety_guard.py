"""Phase 0 safety-guard tests: the root boundary itself is under test.

Plan §0(2): junction / symlink / `..` / absolute-path escapes must be
refused BEFORE any destructive call. These tests attack assert_inside_root
directly — if the guard regresses, nothing below it may run.
"""

from __future__ import annotations

import os

import pytest

from tests.quality.safety import assert_all_inside_root, assert_inside_root


def test_root_guard_accepts_inside_paths(tmp_path):
    root = tmp_path / "root"
    (root / "sub" / "deep").mkdir(parents=True)
    target = root / "sub" / "deep" / "file.bin"
    target.write_bytes(b"x")
    assert assert_inside_root(str(target), str(root))


def test_root_guard_refuses_dotdot_and_absolute_outside(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"precious")
    with pytest.raises(AssertionError):
        assert_inside_root(str(root / ".." / "outside.bin"), str(root))
    with pytest.raises(AssertionError):
        assert_inside_root(str(outside), str(root))
    with pytest.raises(AssertionError):
        assert_inside_root(str(root), str(root))  # the root itself is not a target
    # Batch variant refuses atomically on first escape.
    with pytest.raises(AssertionError):
        assert_all_inside_root([str(root / "ok.bin"), str(outside)], str(root))


def test_root_guard_refuses_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "secret.bin"
    outside.write_bytes(b"secret")
    link = root / "evil_link.bin"
    try:
        os.symlink(str(outside), str(link))
    except OSError:
        pytest.skip("symlinks unavailable in this environment")
    # The link textually lives inside root but resolves outside: refuse.
    with pytest.raises(AssertionError):
        assert_inside_root(str(link), str(root))
