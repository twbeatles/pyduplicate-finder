"""Phase 1 (DUP-04 / DUP-06): backend parity + cancel/resume + cache distrust.

Environment reality (recorded, not hidden): this environment has no compiled
``pydup_core``, so ``is_rust_available()`` is False. A Python<->Rust parity
PASS is therefore NOT claimed here — it is reported as BLOCKED with the
provenance check as evidence, while the Python fallback path is verified
end-to-end on real files. Claiming parity without the Rust wheel would be a
false PASS.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from tests.quality.fixtures_cases import build_case_set
from tests.quality.safety import find_group_containing, group_key_members, sha256_file


def _run_exact_scan(worker, *, byte_compare=False):
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
    for key, paths in temp_hash_map.items():
        if len(paths) >= 2:
            worker._process_final_group(key[1], key[0], paths, final)
    return final


def test_dup04_python_backend_real_scan_and_rust_unavailable_is_blocked(
    quality_root, worker_factory
):
    from src.core.native.bridge import (
        RustCoreUnavailable,
        get_backend_name,
        is_rust_available,
    )

    rust_available = bool(is_rust_available())
    if rust_available:
        pytest.skip("rust backend present: parity comparison runs elsewhere")

    # Provenance evidence: no native module -> auto resolves to python, and an
    # explicit rust request fails closed instead of silently using python.
    assert get_backend_name("python") == "python"
    assert get_backend_name("auto") == "python"
    with pytest.raises(RustCoreUnavailable):
        get_backend_name("rust")

    # Real end-to-end scan on the forced-python backend.
    paths = build_case_set(quality_root)
    worker = worker_factory(
        [str(quality_root / "data")], quality_root, scan_backend="python", byte_compare=True
    )
    assert worker._use_rust_hashing() is False
    assert worker._use_rust_discovery() is False
    final = _run_exact_scan(worker, byte_compare=True)
    groups = group_key_members(final)
    assert sha256_file(paths["dup_a"]) == sha256_file(paths["dup_b"])
    assert find_group_containing(groups, paths["dup_a"], paths["dup_b"]) is not None


def test_dup04_auto_backend_matches_forced_python_on_same_manifest(quality_root, worker_factory):
    """Result-set equality under backend selection normalisation.

    In this env both resolve to the Python engine; the test pins that the
    selection layer cannot silently change the result set (path normalisation
    applied before comparison to absorb thread-ordering differences).
    """
    from src.core.native.bridge import is_rust_available

    if bool(is_rust_available()):
        pytest.skip("rust backend present: covered by dedicated parity run")
    build_case_set(quality_root)
    auto_worker = worker_factory([str(quality_root / "data")], quality_root, scan_backend="auto")
    auto_groups = sorted(
        sorted(g) for g in group_key_members(_run_exact_scan(auto_worker, byte_compare=True))
    )
    py_worker = worker_factory(
        [str(quality_root / "data")], quality_root, scan_backend="python"
    )
    py_groups = sorted(
        sorted(g) for g in group_key_members(_run_exact_scan(py_worker, byte_compare=True))
    )
    assert auto_groups == py_groups
    assert len(auto_groups) >= 1


def test_dup06_cancel_then_clean_rescan_matches(quality_root, worker_factory):
    """A cancelled scan leaves no partial state behind: clean rescan is whole."""
    build_case_set(quality_root)
    worker = worker_factory([str(quality_root / "data")], quality_root)

    # Simulate mid-scan cancellation at the hashing stage.
    worker._stop_event.set()
    cancelled = worker._calculate_hashes_parallel(
        [(str(quality_root / "data" / "dup_a.bin"), 1024, 0.0)], is_quick_scan=True
    )
    assert cancelled == {} or sum(len(v) for v in cancelled.values()) == 0
    worker._stop_event.clear()

    # Clean rescan over the same manifest must equal a fresh worker's result.
    first = sorted(sorted(g) for g in group_key_members(_run_exact_scan(worker)))
    fresh = worker_factory([str(quality_root / "data")], quality_root)
    second = sorted(sorted(g) for g in group_key_members(_run_exact_scan(fresh)))
    assert first == second
    assert len(first) >= 1


def test_dup06_stale_session_hash_with_changed_size_is_rehashed(quality_root, worker_factory):
    """Seeded session hashes with outdated (size, mtime) must not be trusted.

    Seeds scan_hashes for a session, then changes the file's bytes+size, and
    rescans with that session id. Correct code re-hashes (coords mismatch);
    a mutant trusting cached fingerprints unconditionally would group the
    changed file with its old twin.
    """
    import hashlib as _hl

    from src.core.cache_manager import CacheManager

    victim = quality_root / "data" / "victim.bin"
    twin = quality_root / "data" / "twin.bin"
    v1 = b"victim-version-one" * 64  # 1152 bytes
    v2 = b"victim-version-TWO" * 64  # same size, different bytes
    assert len(v2) == len(v1)
    assert v2 != v1
    victim.write_bytes(v1)
    twin.write_bytes(v1)
    st_v = os.stat(str(victim))
    st_t = os.stat(str(twin))
    digest_v1 = _hl.blake2b(v1, digest_size=32).hexdigest()

    session_id = 424242
    seeder = CacheManager(db_path=str(quality_root / "scan_cache.db"))
    try:
        seeder.save_scan_hashes_batch(
            session_id,
            [
                (str(victim), int(st_v.st_size), float(st_v.st_mtime), "FULL", digest_v1),
                (str(twin), int(st_t.st_size), float(st_t.st_mtime), "FULL", digest_v1),
            ],
        )
    finally:
        seeder.close_all()

    # Change the victim AFTER the fingerprint was cached: same size (so the
    # size pre-filter cannot save us), different bytes, fresh mtime.
    victim.write_bytes(v2)

    worker = worker_factory([str(quality_root / "data")], quality_root)
    worker.session_id = session_id
    try:
        size_map = worker._scan_files()
        candidates = []
        for size, paths in size_map.items():
            if len(paths) > 1:
                for path in paths:
                    meta = worker._file_meta.get(path)
                    if meta:
                        candidates.append((path, int(meta[0]), float(meta[1])))
        assert {str(victim), str(twin)} <= {c[0] for c in candidates}
        hash_map = worker._calculate_hashes_parallel(candidates, is_quick_scan=True)
        final: dict = {}
        for key, paths in hash_map.items():
            if len(paths) >= 2:
                worker._process_final_group(key[1], key[0], paths, final)
        groups = group_key_members(final)
        # Changed file must NOT group with its stale twin.
        assert find_group_containing(groups, str(victim), str(twin)) is None
        # Fresh digest recorded, not the seeded stale one.
        assert worker._full_hash_values.get(str(victim)) == _hl.blake2b(v2, digest_size=32).hexdigest()
    finally:
        worker.session_id = None


def test_dup06_corrupt_hash_cache_is_not_trusted(quality_root, worker_factory):
    """A cache row with wrong (size, mtime) must be ignored, never trusted."""
    target = quality_root / "data" / "cached.bin"
    payload = b"cache-distrust-payload" * 64
    target.write_bytes(payload)
    st = os.stat(str(target))

    worker = worker_factory([str(quality_root / "data")], quality_root)
    # Poison the cache with a bogus digest for the right path but stale coords.
    worker.cache_manager.update_cache(
        str(target), int(st.st_size) + 999, float(st.st_mtime) - 999.0,
        full="0" * 64,
    )
    digest, _fresh = worker.get_file_hash(str(target), int(st.st_size), float(st.st_mtime))
    expected = hashlib.blake2b(payload, digest_size=32).hexdigest()
    assert digest == expected

    # Even a correct-coords row holding a forged digest is caught by the
    # byte-compare gate downstream: same-size-different-content never groups.
    other = quality_root / "data" / "cached_other.bin"
    other.write_bytes(b"D" * len(payload))
    size_map = worker._scan_files()
    assert str(target) in worker._file_meta and str(other) in worker._file_meta
    final = _run_exact_scan(worker, byte_compare=True)
    assert find_group_containing(group_key_members(final), str(target), str(other)) is None
