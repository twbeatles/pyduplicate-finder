from types import SimpleNamespace

from src.core.operation_queue import Operation, OperationResult
from src.ui.controllers.operation_flow_controller import OperationFlowController


class _DummyStatus:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = str(text or "")


class _DummyToast:
    def __init__(self):
        self.calls = []

    def success(self, msg, duration=0):
        self.calls.append(("success", msg, duration))

    def warning(self, msg, duration=0):
        self.calls.append(("warning", msg, duration))

    def error(self, msg, duration=0):
        self.calls.append(("error", msg, duration))


def _build_host():
    host = SimpleNamespace()
    host._op_queue = []
    host._op_progress = None
    host._op_worker = None
    host.status_label = _DummyStatus()
    host.toast_manager = _DummyToast()
    host.scan_results = {}
    host.current_session_id = None
    host.cache_manager = SimpleNamespace(
        load_selected_paths=lambda _sid: [],
        save_scan_results=lambda _sid, _results: None,
    )
    host.ops_controller = SimpleNamespace(build_retry_operation=lambda _result: None)
    host._apply_quarantine_retention = lambda: None
    host.refresh_quarantine_list = lambda: None
    host.refresh_operations_list = lambda: None
    host._remove_paths_from_results = lambda _removed: None
    host._render_results = lambda _results, selected_paths=None: None
    host._undo_redo_sync_calls = 0

    def _sync_undo_redo():
        host._undo_redo_sync_calls += 1

    host.update_undo_redo_buttons = _sync_undo_redo
    return host


def test_enqueue_operations_sets_queue_and_starts(monkeypatch):
    c = OperationFlowController()
    host = _build_host()
    started = []
    monkeypatch.setattr(c, "start_next_operation", lambda _host: started.append(True))

    c.enqueue_operations(host, [Operation("undo"), Operation("redo")])

    assert len(host._op_queue) == 2
    assert started == [True]


def test_start_next_operation_pops_first_and_delegates(monkeypatch):
    c = OperationFlowController()
    host = _build_host()
    host._op_queue = [Operation("undo"), Operation("redo")]
    called = []

    def _start(_host, op, allow_queue_continue=False):
        called.append((op.op_type, allow_queue_continue))

    monkeypatch.setattr(c, "start_operation", _start)
    c.start_next_operation(host)

    assert called == [("undo", True)]
    assert len(host._op_queue) == 1
    assert host._op_queue[0].op_type == "redo"


def test_on_finished_continues_queue_when_allowed(monkeypatch):
    c = OperationFlowController()
    host = _build_host()
    host._op_queue = [Operation("redo")]
    advanced = []
    monkeypatch.setattr(c, "start_next_operation", lambda _host: advanced.append(True))

    res = OperationResult(op_type="undo", status="completed", message="done")
    c.on_finished(host, res, allow_queue_continue=True)

    assert advanced == [True]


def test_on_finished_clears_queue_on_failed_result():
    c = OperationFlowController()
    host = _build_host()
    host._op_queue = [Operation("redo")]

    res = OperationResult(op_type="undo", status="failed", message="failed")
    c.on_finished(host, res, allow_queue_continue=True)

    assert host._op_queue == []


def test_on_finished_syncs_undo_redo_buttons():
    c = OperationFlowController()
    host = _build_host()
    res = OperationResult(op_type="delete_quarantine", status="completed", message="done")

    c.on_finished(host, res, allow_queue_continue=False)

    assert host._undo_redo_sync_calls == 1


def test_cancel_operation_stops_worker():
    c = OperationFlowController()
    host = _build_host()
    stopped = {"ok": False}

    class _Worker:
        def stop(self):
            stopped["ok"] = True

    host._op_worker = _Worker()
    c.cancel_operation(host)
    assert stopped["ok"] is True
