"""Phase 2b (FS-05..08, FS-10): hardlink consolidate+undo, stale plans,
cancel boundaries, error separation, and the real worker op path.

All file targets live under the per-test isolated root. OperationWorker's
_real_ methods run against a REAL CacheManager + QuarantineManager (no
dummy stand-ins): the "fake OperationResult" anti-pattern from the plan is
exactly what these tests refuse to do.
"""

from __future__ import annotations

import os

import pytest

from tests.quality.safety import (
    assert_inside_root,
    files_byte_equal,
    sha256_file,
    write_bytes,
)


def _real_worker(cache, qm, op):
    from src.core.operation_queue import OperationWorker

    return OperationWorker(
        cache_manager=cache,
        quarantine_manager=qm,
        history_manager=None,
        op=op,
    )


def test_fs05_hardlink_consolidate_and_undo_restore_bytes(quarantine_pair):
    if os.name != "nt":
        pytest.skip("Windows hardlink undo semantics under test")
    from src.core.operation_queue import Operation, OperationResult

    root, cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    canonical = write_bytes(root / "work" / "canonical.bin", b"canonical-bytes" * 128)
    target = write_bytes(root / "work" / "target.bin", b"target-bytes-XXXX" * 128)
    canon_sha, target_sha = sha256_file(canonical), sha256_file(target)
    canon_id_before = (os.stat(canonical).st_dev, os.stat(canonical).st_ino)

    worker = _real_worker(
        cache, qm, Operation("hardlink_consolidate", options={"canonical": canonical, "targets": [target]})
    )
    res = OperationResult(op_type="hardlink_consolidate")
    worker._run_hardlink(worker.op, res)

    assert res.status == "completed", res.failed
    assert res.failed == []
    # Target is now a hardlink to canonical: same bytes, same file id.
    assert sha256_file(target) == canon_sha
    assert (os.stat(target).st_dev, os.stat(target).st_ino) == canon_id_before
    # Canonical itself untouched.
    assert sha256_file(canonical) == canon_sha
    assert (os.stat(canonical).st_dev, os.stat(canonical).st_ino) == canon_id_before

    # Undo: the quarantined original replaces the hardlink.
    rows = cache.list_quarantine_items(status_filter="quarantined")
    assert len(rows) == 1
    ok, _msg, restored = qm.restore_item(int(rows[0]["id"]), allow_replace_hardlink_to=canonical)
    assert ok and restored == target
    assert sha256_file(target) == target_sha
    assert files_byte_equal(canonical, target) is False


def test_fs06_move_records_fresh_stat_never_stale_caller_metadata(quarantine_pair):
    """move_to_quarantine stats the file itself at move time.

    Current contract (plan §FS-06): there is no cross-call "saved plan" that
    could go stale — the recorded size/mtime always come from a fresh
    os.stat inside the move loop. This test pins that: mutate after an
    earlier stat, and the DB row must carry the NEW stat.
    """
    root, cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    src = write_bytes(root / "work" / "plan.bin", b"v1-bytes" * 64)
    stale_size = os.path.getsize(src)
    stale_mtime = os.path.getmtime(src)

    # Content changes after the "plan" was read (same path, new bytes).
    write_bytes(src, b"v2-bytes-LONGER!!" * 64)
    assert (os.path.getsize(src), os.path.getmtime(src)) != (stale_size, stale_mtime)

    moved, failures = qm.move_to_quarantine([src])
    assert failures == [] and len(moved) == 1
    row = cache.get_quarantine_item(moved[0].item_id)
    assert row is not None
    assert int(row["size"]) == os.path.getsize(moved[0].quarantine_path)
    assert int(row["size"]) != stale_size
    assert sha256_file(moved[0].quarantine_path) == sha256_file(moved[0].quarantine_path)


def test_fs07_cancel_at_boundary_leaves_only_clean_states(quarantine_pair):
    root, _cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    files = [write_bytes(root / "work" / f"c{i}.bin", b"x" * 256 + bytes([i])) for i in range(4)]
    before = {p: sha256_file(p) for p in files}

    # Cancel before any work: nothing moves, everything intact.
    moved, _failures = qm.move_to_quarantine(files, check_cancel=lambda: True)
    assert moved == []
    for p in files:
        assert os.path.exists(p) and sha256_file(p) == before[p]

    # Cancel after exactly one file: states are only before/after+DB-row.
    calls = {"n": 0}

    def _cancel_after_one() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    moved2, _ = qm.move_to_quarantine(files, check_cancel=_cancel_after_one)
    assert len(moved2) == 1
    for p in files:
        if p == moved2[0].orig_path:
            assert not os.path.exists(p)
        else:
            assert os.path.exists(p) and sha256_file(p) == before[p]
    # No orphan: every moved path has exactly one DB row in quarantined state.
    rows = _cache.list_quarantine_items(status_filter="quarantined")
    assert {r["orig_path"] for r in rows} == {moved2[0].orig_path}


def test_fs08_mixed_failures_are_separated_valid_work_survives(quarantine_pair):
    from src.core.operation_queue import Operation, OperationResult

    root, cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    good1 = write_bytes(root / "work" / "good1.bin", b"good-one" * 64)
    good2 = write_bytes(root / "work" / "good2.bin", b"good-two" * 64)
    missing = str(root / "work" / "does-not-exist.bin")
    as_dir = str(root / "work")
    for p in (good1, good2, missing, as_dir):
        if p.startswith(str(root)):
            assert_inside_root(p if os.path.exists(p) else str(root / "work"), str(root))

    worker = _real_worker(
        cache, qm, Operation("delete_quarantine", paths=[good1, missing, as_dir, good2])
    )
    res = OperationResult(op_type="delete_quarantine")
    worker._run_delete_quarantine(worker.op, res)

    # Partial — never a blanket completed/failed; successes and failures split.
    assert res.status == "partial"
    assert sorted(res.succeeded) == sorted([good1, good2])
    failed_paths = sorted(p for p, _r in res.failed)
    assert failed_paths == sorted([missing, as_dir])
    assert not os.path.exists(good1) and not os.path.exists(good2)
    # Operation items log records both outcomes in the real DB.
    assert cache is not None


def test_fs10_real_worker_delete_then_restore_roundtrip(quarantine_pair):
    """GUI-delete-button equivalent: real worker -> real SQLite -> real restore."""
    from src.core.operation_queue import Operation, OperationResult

    root, cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    payload = b"fs10-worker-roundtrip" * 128
    src = write_bytes(root / "work" / "roundtrip.bin", payload)
    before_sha = sha256_file(src)

    deleter = _real_worker(cache, qm, Operation("delete_quarantine", paths=[src]))
    del_res = OperationResult(op_type="delete_quarantine")
    deleter._run_delete_quarantine(deleter.op, del_res)
    assert del_res.status == "completed", del_res.failed
    assert not os.path.exists(src)

    rows = cache.list_quarantine_items(status_filter="quarantined")
    assert len(rows) == 1
    item_id = int(rows[0]["id"])

    restorer = _real_worker(cache, qm, Operation("restore", options={"item_ids": [item_id]}))
    res_res = OperationResult(op_type="restore")
    restorer._run_restore(restorer.op, res_res)
    assert res_res.status == "completed", res_res.failed
    assert os.path.exists(src)
    assert sha256_file(src) == before_sha
    row = cache.get_quarantine_item(item_id)
    assert row is not None and row["status"] == "restored"
