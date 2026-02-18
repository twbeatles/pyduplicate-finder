from __future__ import annotations

from src.core.operation_queue import Operation, OperationResult


class OpsController:
    @staticmethod
    def build_retry_operation(result: OperationResult):
        failed = list(getattr(result, "failed", []) or [])
        if not failed:
            return None

        op_type = str(getattr(result, "op_type", "") or "")
        meta = dict(getattr(result, "meta", {}) or {})

        if op_type in ("delete_quarantine", "delete_trash"):
            paths = [p for p, _ in failed if p]
            return Operation(op_type, paths=paths) if paths else None

        if op_type in ("restore", "purge"):
            item_ids = [int(x) for x in (meta.get("failed_item_ids") or []) if x]
            if not item_ids:
                return None
            opts = {"item_ids": item_ids}
            if op_type == "restore" and meta.get("allow_replace_hardlink_to"):
                opts["allow_replace_hardlink_to"] = meta.get("allow_replace_hardlink_to")
            return Operation(op_type, options=opts)

        if op_type == "hardlink_consolidate":
            canonical = str(meta.get("canonical") or "")
            targets = [str(x) for x in (meta.get("failed_targets") or []) if x]
            if canonical and targets:
                return Operation("hardlink_consolidate", options={"canonical": canonical, "targets": targets})

        return None

