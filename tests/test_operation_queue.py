from src.core.operation_queue import Operation, OperationResult, OperationWorker
import src.core.operation_queue as operation_queue


class _DummyCache:
    def __init__(self):
        self.items_batches = []

    def append_operation_items(self, op_id, items_batch):
        self.items_batches.append((int(op_id), list(items_batch)))


class _DummyQuarantine:
    def move_to_quarantine(self, *_args, **_kwargs):
        return ([], [])

    def restore_item(self, *_args, **_kwargs):
        return (False, "not_called", None)


def test_delete_trash_skipped_only_results_in_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(operation_queue, "_TRASH_AVAILABLE", True)
    monkeypatch.setattr(operation_queue, "_send_to_trash", lambda _p: None)

    missing_path = str(tmp_path / "missing.txt")
    worker = OperationWorker(
        cache_manager=_DummyCache(),
        quarantine_manager=_DummyQuarantine(),
        history_manager=None,
        op=Operation("delete_trash", paths=[missing_path]),
    )
    res = OperationResult(op_type="delete_trash")
    worker._run_delete_trash(worker.op, res)

    assert res.succeeded == []
    assert res.failed == []
    assert len(res.skipped) == 1
    assert res.status == "partial"


def test_hardlink_skipped_only_results_in_partial(tmp_path):
    canonical = tmp_path / "canonical.bin"
    canonical.write_bytes(b"x")
    missing_target = str(tmp_path / "missing_target.bin")

    worker = OperationWorker(
        cache_manager=_DummyCache(),
        quarantine_manager=_DummyQuarantine(),
        history_manager=None,
        op=Operation(
            "hardlink_consolidate",
            options={"canonical": str(canonical), "targets": [missing_target]},
        ),
    )
    res = OperationResult(op_type="hardlink_consolidate")
    worker._run_hardlink(worker.op, res)

    assert res.succeeded == []
    assert res.failed == []
    assert len(res.skipped) == 1
    assert res.status == "partial"


def test_restore_exception_still_records_operation_item():
    class _ExplodingCache(_DummyCache):
        def get_quarantine_items_by_ids(self, _item_ids):
            return {}

        def get_quarantine_item(self, _item_id):
            raise RuntimeError("db_error")

    cache = _ExplodingCache()
    worker = OperationWorker(
        cache_manager=cache,
        quarantine_manager=_DummyQuarantine(),
        history_manager=None,
        op=Operation("restore", options={"item_ids": [11]}),
    )
    res = OperationResult(op_type="restore", op_id=7)
    worker._run_restore(worker.op, res)

    assert res.status == "failed"
    assert res.meta.get("failed_item_ids") == [11]
    assert len(cache.items_batches) == 1
    _op_id, rows = cache.items_batches[0]
    assert len(rows) == 1
    assert rows[0][1] == "restored"
    assert rows[0][2] == "fail"
    assert rows[0][0] == "11"
