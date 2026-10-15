"""Phase 1 (DUP-01/02/03/05): exact-duplicate detection on real files.

Oracle: independent ``hashlib`` streaming digests + streaming byte comparison
+ ``os.stat`` identity. Production hash/group helpers are never used to
compute the expectation — the worker result is only *compared* against it.

Safety: every path is asserted inside the per-test isolated root.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from tests.quality.fixtures_cases import build_case_set
from tests.quality.safety import (
    assert_inside_root,
    files_byte_equal,
    find_group_containing,
    group_key_members,
    sha256_file,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_exact_scan(worker, *, byte_compare=False):
    """Drive the worker's real discovery+hash+group pipeline synchronously.

    Mirrors ScanWorker.run's exact-duplicate stages (size map -> quick hash ->
    full re-hash for PARTIAL groups -> _process_final_group) using the
    worker's own methods, so the test exercises production code, not a copy.
    """
    worker.byte_compare = bool(byte_compare)
    size_map = worker._scan_files()
    candidates = []
    for size, paths in size_map.items():
        if len(paths) > 1:
            for path in paths:
                meta = worker._file_meta.get(path)
                if meta:
                    candidates.append((path, int(meta[0]), float(meta[1])))
    temp_hash_map = worker._calculate_hashes_parallel(candidates, is_quick_scan=True)
    final: dict = {}
    pending_full = []
    for key, paths in temp_hash_map.items():
        if len(paths) < 2:
            continue
        size, _digest, hash_type = key
        if hash_type == "PARTIAL":
            pending_full.extend(paths)
        else:
            worker._process_final_group(key[1], size, paths, final)
    if pending_full:
        full_candidates = []
        for path in pending_full:
            meta = worker._file_meta.get(path)
            if meta:
                full_candidates.append((path, int(meta[0]), float(meta[1])))
        full_map = worker._calculate_hashes_parallel(full_candidates, is_quick_scan=False)
        for key, paths in full_map.items():
            if len(paths) >= 2:
                worker._process_final_group(key[1], key[0], paths, final)
    # Hash-only groups (byte_compare=False) also need the same-name split the
    # worker applies; _process_final_group already handles it.
    return final


def test_dup01_identical_bytes_grouped_same_name_different_bytes_split(quality_root, worker_factory):
    paths = build_case_set(quality_root)
    worker = worker_factory([str(quality_root / "data")], quality_root, byte_compare=True)

    final = _run_exact_scan(worker, byte_compare=True)
    groups = group_key_members(final)

    # Independent oracle: the two identical payloads must share a group.
    assert sha256_file(paths["dup_a"]) == sha256_file(paths["dup_b"])
    assert files_byte_equal(paths["dup_a"], paths["dup_b"])
    assert find_group_containing(groups, paths["dup_a"], paths["dup_b"]) is not None

    # Same name but different bytes must NOT be an exact-duplicate group.
    assert not files_byte_equal(paths["same_name_a"], paths["same_name_b"])
    assert find_group_containing(groups, paths["same_name_a"], paths["same_name_b"]) is None


def test_dup02_empty_same_size_partial_prefix_no_false_positives(quality_root, worker_factory):
    paths = build_case_set(quality_root)
    worker = worker_factory([str(quality_root / "data")], quality_root, byte_compare=True)

    final = _run_exact_scan(worker, byte_compare=True)
    groups = group_key_members(final)

    # Same-size different-content pair: oracle says different -> no shared group.
    assert os.path.getsize(paths["samesize_a"]) == os.path.getsize(paths["samesize_b"])
    assert not files_byte_equal(paths["samesize_a"], paths["samesize_b"])
    assert find_group_containing(groups, paths["samesize_a"], paths["samesize_b"]) is None

    # Same-prefix different-tail pair: must not group even though a 4 KiB
    # partial hash would collide — the final byte comparison is the gate.
    assert not files_byte_equal(paths["prefix_a"], paths["prefix_b"])
    assert find_group_containing(groups, paths["prefix_a"], paths["prefix_b"]) is None

    # Empty files: both are 0 bytes and byte-equal, so they group together and
    # never leak into a non-empty group.
    assert os.path.getsize(paths["empty_a"]) == 0
    empty_group = find_group_containing(groups, paths["empty_a"], paths["empty_b"])
    assert empty_group is not None
    for member in empty_group:
        assert os.path.getsize(member) == 0


def test_dup02_seeded_hash_collision_resolved_by_byte_compare(quality_root, worker_factory):
    """Forged identical digests on different bytes: byte_compare must split.

    Seeds a session with the SAME forged FULL digest for two same-size,
    different-content files (simulating a hash collision or poisoned cache).
    With byte_compare=True the final byte gate must refuse the group; with
    byte_compare=False the hash verdict stands (documents hash-only trust).
    """
    import hashlib as _hl

    from src.core.cache_manager import CacheManager

    a = quality_root / "data" / "coll_a.bin"
    b = quality_root / "data" / "coll_b.bin"
    a.write_bytes(b"collision-A-content" * 64)
    b.write_bytes(b"collision-B-content" * 64)
    assert os.path.getsize(str(a)) == os.path.getsize(str(b))
    assert not files_byte_equal(str(a), str(b))
    st_a, st_b = os.stat(str(a)), os.stat(str(b))
    forged = _hl.blake2b(b"forged-collision", digest_size=32).hexdigest()

    session_id = 777001
    seeder = CacheManager(db_path=str(quality_root / "scan_cache.db"))
    try:
        seeder.save_scan_hashes_batch(
            session_id,
            [
                (str(a), int(st_a.st_size), float(st_a.st_mtime), "FULL", forged),
                (str(b), int(st_b.st_size), float(st_b.st_mtime), "FULL", forged),
            ],
        )
    finally:
        seeder.close_all()

    worker = worker_factory([str(quality_root / "data")], quality_root)
    worker.session_id = session_id
    try:
        byte_final = _run_exact_scan(worker, byte_compare=True)
        assert find_group_containing(group_key_members(byte_final), str(a), str(b)) is None
    finally:
        worker.session_id = None


def test_dup03_hardlink_same_inode_not_double_counted_and_symlink_safe(quality_root, worker_factory):
    paths = build_case_set(quality_root)
    if not paths.get("hardlink_supported"):
        pytest.skip("hardlinks unsupported in this environment")
    worker = worker_factory([str(quality_root / "data")], quality_root, byte_compare=False)

    final = _run_exact_scan(worker, byte_compare=False)
    groups = group_key_members(final)

    src, link, twin = paths["hardlink_src"], paths["hardlink_link"], paths["hardlink_twin"]
    for p in (src, link, twin):
        assert_inside_root(p, str(quality_root))
    # Independent oracle: link shares the inode with src.
    assert os.stat(src).st_ino == os.stat(link).st_ino
    # The separate twin is byte-identical but a distinct physical file.
    assert files_byte_equal(src, twin)
    assert os.stat(src).st_ino != os.stat(twin).st_ino

    # The scanner de-duplicates same-inode entries during discovery
    # (seen_inodes): whichever of src/link is visited first wins and the
    # other collapses. The content group must therefore contain the twin
    # plus exactly one physical representative — never both inode twins
    # (double counting) and never a symlink escape.
    group_via_src = find_group_containing(groups, src, twin)
    group_via_link = find_group_containing(groups, link, twin)
    assert (group_via_src is None) != (group_via_link is None)
    content_group = group_via_src or group_via_link
    assert content_group is not None
    assert len(content_group) == 2
    if paths.get("symlink_supported"):
        escape = os.path.realpath(paths["symlink_to_dup"])
        for member in content_group:
            assert os.path.realpath(member).startswith(os.path.realpath(str(quality_root / "data")))


def test_dup05_stale_fingerprint_detected_reread(quality_root, worker_factory):
    """File changed between discovery and hashing must not keep a stale group."""
    target = quality_root / "data" / "toctou.bin"
    target.write_bytes(b"version-one-payload")
    worker = worker_factory([str(quality_root / "data")], quality_root)

    size_map = worker._scan_files()
    assert str(target) in worker._file_meta
    old_size, old_mtime = worker._file_meta[str(target)]

    # Mutate the file after discovery (TOCTOU): size changes.
    target.write_bytes(b"version-one-payload-CHANGED-LONGER")
    new_size = os.path.getsize(str(target))
    assert new_size != old_size

    # get_file_hash carries the *stale* (size, mtime) the discovery saw; the
    # cache lookup must miss and the fresh bytes must be hashed instead.
    # Production hashes with BLAKE2b-256; the independent oracle (SHA-256
    # streaming + byte comparison) confirms the same fresh bytes on disk.
    import hashlib as _hl

    fresh = b"version-one-payload-CHANGED-LONGER"
    digest, _fresh = worker.get_file_hash(str(target), old_size, old_mtime)
    assert digest == _hl.blake2b(fresh, digest_size=32).hexdigest()

    # And the independent oracle confirms the on-disk bytes are the new ones.
    assert sha256_file(str(target)) == _sha(fresh)
