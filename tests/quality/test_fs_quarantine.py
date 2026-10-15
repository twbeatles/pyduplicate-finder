"""Phase 2a (FS-01..04, FS-09): quarantine lifecycle on real files + real SQLite.

Every test uses per-test isolated roots (quarantine_pair fixture). Failure
injection hooks only the DB/file API boundary — never the filesystem itself.
"""

from __future__ import annotations

import os
import sqlite3
import time
from unittest.mock import patch

from tests.quality.safety import (
    assert_inside_root,
    files_byte_equal,
    sha256_file,
    snapshot_manifest,
    write_bytes,
)


def _fresh_pair(quarantine_pair):
    """Re-open CacheManager+QuarantineManager on the same db (new process)."""
    from src.core.cache_manager import CacheManager
    from src.core.quarantine_manager import QuarantineManager

    root = quarantine_pair["root"]
    cache2 = CacheManager(db_path=str(root / "scan_cache.db"))
    qm2 = QuarantineManager(cache2, quarantine_dir=str(quarantine_pair["qdir"]))
    return cache2, qm2


def test_fs01_quarantine_then_restore_in_new_instance(quarantine_pair):
    root, cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    payload = b"fs01-cross-process-bytes" * 128
    src = write_bytes(root / "work" / "doc.bin", payload)
    before_sha = sha256_file(src)
    before_size = os.path.getsize(src)

    moved, failures = qm.move_to_quarantine([src])
    assert failures == []
    assert len(moved) == 1
    assert not os.path.exists(src)
    qpath = moved[0].quarantine_path
    assert_inside_root(qpath, str(quarantine_pair["qdir"]))
    cache.close_all()

    # "New process": fresh manager instances over the same DB + quarantine dir.
    cache2, qm2 = _fresh_pair(quarantine_pair)
    try:
        item = cache2.get_quarantine_item(moved[0].item_id)
        assert item is not None and item["status"] == "quarantined"
        ok, _msg, restored = qm2.restore_item(moved[0].item_id)
        assert ok and restored is not None
        assert sha256_file(restored) == before_sha
        assert os.path.getsize(restored) == before_size
        assert not os.path.exists(qpath)
        item2 = cache2.get_quarantine_item(moved[0].item_id)
        assert item2 is not None and item2["status"] == "restored"
        assert cache2.list_quarantine_items(status_filter="quarantined") == []
    finally:
        cache2.close_all()


def test_fs02_db_insert_failure_never_loses_bytes(quarantine_pair):
    root, cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    payload = b"fs02-rollback-bytes" * 64
    src = write_bytes(root / "work" / "precious.bin", payload)
    before_sha = sha256_file(src)

    with patch.object(cache, "insert_quarantine_item", side_effect=RuntimeError("db down")):
        moved, failures = qm.move_to_quarantine([src])

    assert moved == []
    assert len(failures) == 1
    # Invariant: bytes survive at exactly one definite location.
    if os.path.exists(src):
        assert sha256_file(src) == before_sha  # rolled back to origin
    else:
        # Rollback itself failed: the quarantined copy must still be locatable.
        leftovers = [p for p in snapshot_manifest(quarantine_pair["qdir"]) if p.endswith(".bin")]
        assert leftovers, "original gone AND no quarantined copy: DATA LOSS"
        found = [os.path.join(str(quarantine_pair["qdir"]), p) for p in leftovers]
        assert any(sha256_file(p) == before_sha for p in found)
    # Both-gone is the FAIL condition — assert it directly.
    assert os.path.exists(src) or any(
        True for _ in snapshot_manifest(quarantine_pair["qdir"])
    )


def test_fs03_status_update_failure_reports_failure_preserves_bytes(quarantine_pair):
    root, cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    payload = b"fs03-status-failure" * 64
    src = write_bytes(root / "work" / "status.bin", payload)
    before_sha = sha256_file(src)

    moved, _ = qm.move_to_quarantine([src])
    assert len(moved) == 1
    item_id = moved[0].item_id

    with patch.object(
        cache, "update_quarantine_item_status", side_effect=RuntimeError("commit failed")
    ):
        ok, _msg, restored = qm.restore_item(item_id)

    # No false success is permitted.
    assert ok is False
    # The move itself succeeded, so the bytes are at the destination and
    # its location is reported (not discarded) for reconciliation; the DB
    # row still reads "quarantined" (known non-atomic window, documented).
    assert restored is not None
    assert os.path.exists(restored)
    assert sha256_file(restored) == before_sha
    row = cache.get_quarantine_item(item_id)
    assert row is not None
    assert row["status"] == "quarantined"


def test_fs04_restore_collision_preserves_both_files(quarantine_pair):
    root, cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    original = b"fs04-original-bytes" * 64
    newcomer = b"fs04-newcomer-bytes" * 64
    src = write_bytes(root / "work" / "collide.txt", original)
    orig_sha = sha256_file(src)

    moved, _ = qm.move_to_quarantine([src])
    assert len(moved) == 1

    # A different-content file appears at the original path before restore.
    write_bytes(src, newcomer)
    newcomer_sha = sha256_file(src)

    ok, _msg, restored = qm.restore_item(moved[0].item_id)
    assert ok and restored is not None
    assert restored != src
    assert_inside_root(restored, str(root))
    # Both files survive with their own bytes.
    assert sha256_file(src) == newcomer_sha
    assert sha256_file(restored) == orig_sha
    assert not files_byte_equal(src, restored)


def test_fs02_insert_returning_zero_restores_file_to_origin(quarantine_pair):
    """Falsy insert id (no exception) must still roll the bytes back."""
    from unittest.mock import patch as _patch

    root, cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    payload = b"fs02-falsy-insert" * 64
    src = write_bytes(root / "work" / "falsy.bin", payload)
    before_sha = sha256_file(src)

    with _patch.object(cache, "insert_quarantine_item", return_value=0):
        moved, failures = qm.move_to_quarantine([src])

    assert moved == []
    assert len(failures) == 1
    assert os.path.exists(src)
    assert sha256_file(src) == before_sha


def test_fs09_retention_purges_only_expired_live_records_survive(quarantine_pair):
    import time as _time

    root, cache, qm = quarantine_pair["root"], quarantine_pair["cache"], quarantine_pair["qm"]
    old = write_bytes(root / "work" / "old.bin", b"old-retention" * 128)
    live = write_bytes(root / "work" / "live.bin", b"live-retention" * 128)
    live_sha = sha256_file(live)

    moved, failures = qm.move_to_quarantine([old, live])
    assert failures == [] and len(moved) == 2
    old_id = next(m.item_id for m in moved if m.orig_path == old)
    live_id = next(m.item_id for m in moved if m.orig_path == live)

    # Backdate only the old row past the retention horizon (real SQL update).
    cache.close_all()
    ancient = _time.time() - 60 * 86400.0
    with sqlite3.connect(str(root / "scan_cache.db")) as conn:
        conn.execute("UPDATE quarantine_items SET created_at=? WHERE id=?", (ancient, old_id))
        conn.commit()
    from src.core.cache_manager import CacheManager
    from src.core.quarantine_manager import QuarantineManager

    cache2 = CacheManager(db_path=str(root / "scan_cache.db"))
    qm2 = QuarantineManager(cache2, quarantine_dir=str(quarantine_pair["qdir"]))
    try:
        purged = qm2.apply_retention(max_days=30, max_bytes=10**12)
        assert old_id in purged
        assert live_id not in purged
        survivor = cache2.get_quarantine_item(live_id)
        assert survivor is not None and survivor["status"] == "quarantined"
        assert os.path.exists(survivor["quarantine_path"])
        assert sha256_file(survivor["quarantine_path"]) == live_sha
        gone = cache2.get_quarantine_item(old_id)
        assert gone is not None and gone["status"] == "purged"
    finally:
        cache2.close_all()
