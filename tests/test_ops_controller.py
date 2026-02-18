from src.core.operation_queue import OperationResult
from src.ui.controllers.ops_controller import OpsController


def test_retry_operation_for_delete_paths():
    res = OperationResult(op_type="delete_quarantine")
    res.failed = [("a.txt", "locked"), ("b.txt", "missing")]
    op = OpsController.build_retry_operation(res)
    assert op is not None
    assert op.op_type == "delete_quarantine"
    assert op.paths == ["a.txt", "b.txt"]


def test_retry_operation_for_restore_item_ids():
    res = OperationResult(op_type="restore")
    res.failed = [("a.txt", "fail")]
    res.meta["failed_item_ids"] = [11, 12]
    res.meta["allow_replace_hardlink_to"] = "C:/canonical.bin"
    op = OpsController.build_retry_operation(res)
    assert op is not None
    assert op.op_type == "restore"
    assert op.options["item_ids"] == [11, 12]
    assert op.options["allow_replace_hardlink_to"] == "C:/canonical.bin"

