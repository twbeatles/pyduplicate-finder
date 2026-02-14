import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal

try:
    from send2trash import send2trash as _send_to_trash
    _TRASH_AVAILABLE = True
except Exception:
    _TRASH_AVAILABLE = False


@dataclass
class Operation:
    op_type: str
    paths: List[str] = field(default_factory=list)
    options: Dict = field(default_factory=dict)


@dataclass
class OperationResult:
    op_type: str
    op_id: int = 0
    status: str = "failed"  # completed|partial|failed|cancelled
    message: str = ""
    succeeded: List[str] = field(default_factory=list)
    failed: List[Tuple[str, str]] = field(default_factory=list)  # (path, reason)
    skipped: List[Tuple[str, str]] = field(default_factory=list)
    bytes_total: int = 0
    bytes_saved_est: int = 0
    meta: Dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status in ("completed", "partial")


class OperationWorker(QThread):
    progress_updated = Signal(int, str)
    operation_result = Signal(object)  # OperationResult

    def __init__(
        self,
        *,
        cache_manager,
        quarantine_manager=None,
        history_manager=None,
        op: Operation,
    ):
        super().__init__()
        self.cache_manager = cache_manager
        self.quarantine_manager = quarantine_manager
        self.history_manager = history_manager
        self.op = op
        self._running = True

    def stop(self):
        self._running = False

    def _check_cancel(self) -> bool:
        return not self._running

    def run(self):
        op = self.op
        res = OperationResult(op_type=op.op_type)

        # Create op log row early.
        try:
            res.op_id = self.cache_manager.create_operation(op.op_type, op.options or {}, status="running")
        except Exception:
            res.op_id = 0

        try:
            if op.op_type == "delete_quarantine":
                self._run_delete_quarantine(op, res)
            elif op.op_type == "delete_trash":
                self._run_delete_trash(op, res)
            elif op.op_type == "restore":
                self._run_restore(op, res)
            elif op.op_type == "purge":
                self._run_purge(op, res)
            elif op.op_type == "hardlink_consolidate":
                self._run_hardlink(op, res)
            elif op.op_type == "undo":
                self._run_undo(res)
            elif op.op_type == "redo":
                self._run_redo(res)
            else:
                res.status = "failed"
                res.message = f"Unknown op_type: {op.op_type}"
        except Exception as e:
            res.status = "failed"
            res.message = str(e)

        # Finish op log row.
        try:
            self.cache_manager.finish_operation(
                res.op_id,
                res.status,
                res.message,
                bytes_total=res.bytes_total,
                bytes_saved_est=res.bytes_saved_est,
            )
        except Exception:
            pass

        self.operation_result.emit(res)

    def _run_delete_quarantine(self, op: Operation, res: OperationResult):
        if not self.quarantine_manager:
            res.status = "failed"
            res.message = "Quarantine manager unavailable"
            return
        paths = list(op.paths or [])
        total = len(paths)

        def prog(cur, tot, msg):
            if tot:
                pct = int((cur / tot) * 100)
            else:
                pct = 0
            self.progress_updated.emit(pct, msg)

        moved, failures = self.quarantine_manager.move_to_quarantine(
            paths,
            progress_callback=prog,
            check_cancel=self._check_cancel,
        )

        # Update HistoryManager stacks if provided (undo/redo in-session).
        if self.history_manager and moved:
            try:
                self.history_manager._record_quarantine_transaction(moved)
            except Exception:
                pass

        items_batch = []
        bytes_total = 0
        for m in moved:
            res.succeeded.append(m.orig_path)
            bytes_total += int(m.size or 0)
            items_batch.append((m.orig_path, "moved_to_quarantine", "ok", "", m.size, m.mtime, m.quarantine_path))
        for p, reason in failures:
            res.failed.append((p, reason))
            items_batch.append((p, "moved_to_quarantine", "fail", reason, None, None, ""))

        res.bytes_total = bytes_total
        if self._check_cancel():
            res.status = "cancelled"
            res.message = "Cancelled"
        else:
            if res.failed and res.succeeded:
                res.status = "partial"
            elif res.failed and not res.succeeded:
                res.status = "failed"
            else:
                res.status = "completed"
            res.message = f"Moved {len(res.succeeded)}/{total} to quarantine"

        if items_batch and res.op_id:
            self.cache_manager.append_operation_items(res.op_id, items_batch)

    def _run_delete_trash(self, op: Operation, res: OperationResult):
        if not _TRASH_AVAILABLE:
            res.status = "failed"
            res.message = "System trash unavailable"
            return
        paths = list(op.paths or [])
        total = len(paths)
        items_batch = []
        ok = 0
        for idx, p in enumerate(paths):
            if self._check_cancel():
                break
            pct = int(((idx + 1) / total) * 100) if total else 0
            self.progress_updated.emit(pct, f"{idx + 1}/{total}")
            if not p or not os.path.exists(p) or os.path.isdir(p):
                res.skipped.append((p, "missing_or_dir"))
                items_batch.append((p, "delete_trash", "fail", "missing_or_dir", None, None, ""))
                continue
            try:
                size = None
                mtime = None
                try:
                    size = os.path.getsize(p)
                    mtime = os.path.getmtime(p)
                except Exception:
                    pass
                _send_to_trash(p)
                ok += 1
                res.succeeded.append(p)
                items_batch.append((p, "delete_trash", "ok", "", size, mtime, ""))
            except Exception as e:
                res.failed.append((p, str(e)))
                items_batch.append((p, "delete_trash", "fail", str(e), None, None, ""))

        if self._check_cancel():
            res.status = "cancelled"
            res.message = "Cancelled"
        else:
            if res.failed and res.succeeded:
                res.status = "partial"
            elif res.failed and not res.succeeded:
                res.status = "failed"
            else:
                res.status = "completed"
            res.message = f"Moved {len(res.succeeded)}/{total} to system trash"

        if items_batch and res.op_id:
            self.cache_manager.append_operation_items(res.op_id, items_batch)

    def _run_restore(self, op: Operation, res: OperationResult):
        if not self.quarantine_manager:
            res.status = "failed"
            res.message = "Quarantine manager unavailable"
            return
        item_ids = list(op.options.get("item_ids") or [])
        allow_replace = op.options.get("allow_replace_hardlink_to")
        total = len(item_ids)
        items_batch = []

        for idx, item_id in enumerate(item_ids):
            if self._check_cancel():
                break
            pct = int(((idx + 1) / total) * 100) if total else 0
            self.progress_updated.emit(pct, f"{idx + 1}/{total}")
            try:
                ok, msg, restored_path = self.quarantine_manager.restore_item(
                    int(item_id),
                    allow_replace_hardlink_to=allow_replace,
                )
                item = self.cache_manager.get_quarantine_item(int(item_id)) or {}
                orig = item.get("orig_path") or ""
                qpath = item.get("quarantine_path") or ""
                size = item.get("size")
                mtime = item.get("mtime")
                if ok:
                    res.succeeded.append(restored_path or orig)
                    items_batch.append((orig, "restored", "ok", restored_path or "", size, mtime, qpath))
                else:
                    res.failed.append((orig, msg))
                    items_batch.append((orig, "restored", "fail", msg, size, mtime, qpath))
            except Exception as e:
                res.failed.append((str(item_id), str(e)))

        if self._check_cancel():
            res.status = "cancelled"
            res.message = "Cancelled"
        else:
            if res.failed and res.succeeded:
                res.status = "partial"
            elif res.failed and not res.succeeded:
                res.status = "failed"
            else:
                res.status = "completed"
            res.message = f"Restored {len(res.succeeded)}/{total}"

        if items_batch and res.op_id:
            self.cache_manager.append_operation_items(res.op_id, items_batch)

    def _run_purge(self, op: Operation, res: OperationResult):
        if not self.quarantine_manager:
            res.status = "failed"
            res.message = "Quarantine manager unavailable"
            return
        item_ids = list(op.options.get("item_ids") or [])
        total = len(item_ids)
        items_batch = []
        bytes_total = 0
        for idx, item_id in enumerate(item_ids):
            if self._check_cancel():
                break
            pct = int(((idx + 1) / total) * 100) if total else 0
            self.progress_updated.emit(pct, f"{idx + 1}/{total}")
            item = self.cache_manager.get_quarantine_item(int(item_id)) or {}
            orig = item.get("orig_path") or ""
            qpath = item.get("quarantine_path") or ""
            size = int(item.get("size") or 0)
            mtime = item.get("mtime")
            try:
                ok, msg = self.quarantine_manager.purge_item(int(item_id))
                if ok:
                    res.succeeded.append(orig)
                    bytes_total += size
                    items_batch.append((orig, "purged", "ok", "", size, mtime, qpath))
                else:
                    res.failed.append((orig, msg))
                    items_batch.append((orig, "purged", "fail", msg, size, mtime, qpath))
            except Exception as e:
                res.failed.append((orig, str(e)))
                items_batch.append((orig, "purged", "fail", str(e), size, mtime, qpath))

        res.bytes_total = bytes_total

        if self._check_cancel():
            res.status = "cancelled"
            res.message = "Cancelled"
        else:
            if res.failed and res.succeeded:
                res.status = "partial"
            elif res.failed and not res.succeeded:
                res.status = "failed"
            else:
                res.status = "completed"
            res.message = f"Purged {len(res.succeeded)}/{total}"

        if items_batch and res.op_id:
            self.cache_manager.append_operation_items(res.op_id, items_batch)

    def _run_hardlink(self, op: Operation, res: OperationResult):
        if not self.quarantine_manager:
            res.status = "failed"
            res.message = "Quarantine manager unavailable"
            return
        canonical = str(op.options.get("canonical") or "")
        targets = list(op.options.get("targets") or [])
        total = len(targets)
        items_batch = []
        saved = 0

        if not canonical or not os.path.exists(canonical):
            res.status = "failed"
            res.message = "Canonical missing"
            return

        for idx, t in enumerate(targets):
            if self._check_cancel():
                break
            pct = int(((idx + 1) / total) * 100) if total else 0
            self.progress_updated.emit(pct, f"{idx + 1}/{total}")

            if not t or not os.path.exists(t) or os.path.isdir(t):
                res.skipped.append((t, "missing_or_dir"))
                items_batch.append((t, "hardlinked", "fail", "missing_or_dir", None, None, ""))
                continue

            # Ensure same volume on Windows (hardlink constraint).
            if os.name == "nt":
                da = os.path.splitdrive(os.path.abspath(canonical))[0].lower()
                dt = os.path.splitdrive(os.path.abspath(t))[0].lower()
                if da != dt:
                    res.skipped.append((t, "cross_volume"))
                    items_batch.append((t, "hardlinked", "fail", "cross_volume", None, None, ""))
                    continue

            try:
                size = 0
                mtime = None
                try:
                    size = int(os.path.getsize(t))
                    mtime = float(os.path.getmtime(t))
                except Exception:
                    pass

                moved, failures = self.quarantine_manager.move_to_quarantine([t], check_cancel=self._check_cancel)
                if not moved:
                    reason = failures[0][1] if failures else "move_failed"
                    res.failed.append((t, reason))
                    items_batch.append((t, "hardlinked", "fail", reason, size, mtime, ""))
                    continue

                m = moved[0]

                try:
                    os.link(canonical, t)
                    res.succeeded.append(t)
                    saved += size
                    items_batch.append((t, "hardlinked", "ok", canonical, size, mtime, m.quarantine_path))
                except Exception as e:
                    # Roll back: restore the quarantined original (best effort).
                    try:
                        self.quarantine_manager.restore_item(m.item_id, allow_replace_hardlink_to=None)
                    except Exception:
                        pass
                    res.failed.append((t, str(e)))
                    items_batch.append((t, "hardlinked", "fail", str(e), size, mtime, m.quarantine_path))
            except Exception as e:
                res.failed.append((t, str(e)))

        res.bytes_saved_est = saved

        if self._check_cancel():
            res.status = "cancelled"
            res.message = "Cancelled"
        else:
            if res.failed and res.succeeded:
                res.status = "partial"
            elif res.failed and not res.succeeded:
                res.status = "failed"
            else:
                res.status = "completed"
            res.message = f"Hardlinked {len(res.succeeded)}/{total}"

        if items_batch and res.op_id:
            self.cache_manager.append_operation_items(res.op_id, items_batch)

    def _run_undo(self, res: OperationResult):
        if not self.history_manager:
            res.status = "failed"
            res.message = "History manager unavailable"
            return
        self.progress_updated.emit(0, "undo")
        out = self.history_manager.undo()
        if not out:
            res.status = "failed"
            res.message = "Nothing to undo"
            return
        restored_paths, failed_count = out if isinstance(out, tuple) else (out, 0)
        res.succeeded = list(restored_paths or [])
        if failed_count:
            res.status = "partial"
            res.message = f"Undo restored {len(res.succeeded)} (failed {failed_count})"
        else:
            res.status = "completed"
            res.message = f"Undo restored {len(res.succeeded)}"

    def _run_redo(self, res: OperationResult):
        if not self.history_manager:
            res.status = "failed"
            res.message = "History manager unavailable"
            return
        self.progress_updated.emit(0, "redo")
        out = self.history_manager.redo()
        if not out:
            res.status = "failed"
            res.message = "Nothing to redo"
            return
        deleted_paths, failed_count = out if isinstance(out, tuple) else (out, 0)
        res.succeeded = list(deleted_paths or [])
        if failed_count:
            res.status = "partial"
            res.message = f"Redo deleted {len(res.succeeded)} (failed {failed_count})"
        else:
            res.status = "completed"
            res.message = f"Redo deleted {len(res.succeeded)}"

