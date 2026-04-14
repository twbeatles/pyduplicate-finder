import argparse
import json
import os
import sys
from typing import Any

from src.core.result_schema import dump_results_v3
from src.core.scan_engine import (
    ScanConfig,
    build_scan_worker_kwargs,
    validate_similar_document_dependency,
    validate_similar_image_dependency,
)
from src.core.scanner import ScanWorker
from src.ui.exporting import export_scan_results_csv
from src.utils.i18n import strings


def _similarity_threshold_type(raw: str) -> float:
    try:
        value = float(raw)
    except Exception as exc:
        raise argparse.ArgumentTypeError("similarity-threshold must be a float between 0.0 and 1.0") from exc
    if value < 0.0 or value > 1.0:
        raise argparse.ArgumentTypeError("similarity-threshold must be within [0.0, 1.0]")
    return value


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pyduplicate-cli",
        description="Headless scan runner for PyDuplicate Finder Pro",
    )
    p.add_argument("folders", nargs="+", help="Folders to scan")
    p.add_argument("--lang", choices=["ko", "en"], default="en")

    p.add_argument("--extensions", default="", help="Comma-separated extensions, e.g. jpg,png,pdf")
    p.add_argument("--min-size-kb", type=int, default=0)

    p.add_argument("--same-name", action="store_true")
    p.add_argument("--name-only", action="store_true")
    p.add_argument("--byte-compare", action="store_true")

    p.add_argument("--similar-image", action="store_true")
    p.add_argument("--similar-document", action="store_true")
    p.add_argument("--mixed-mode", action="store_true")
    p.add_argument("--detect-folder-dup", action="store_true")
    p.add_argument("--incremental-rescan", action="store_true")
    p.add_argument("--baseline-session", type=int, default=0)
    p.add_argument("--similarity-threshold", type=_similarity_threshold_type, default=0.9)
    p.add_argument("--document-threshold", type=_similarity_threshold_type, default=0.9)
    p.add_argument("--strict-mode", action="store_true")
    p.add_argument("--strict-max-errors", type=int, default=0)
    p.add_argument(
        "--selection-policy",
        choices=["smart", "oldest", "newest", "path_shortest", "extension_priority", "primary_keep"],
        default="smart",
    )
    p.add_argument("--compare-mode", choices=["none", "collections"], default="none")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--respect-exemptions", action="store_true")
    p.add_argument("--post-cleanup-empty-dirs", action="store_true")
    p.add_argument("--collection-a", action="append", default=[], help="Primary collection folder (repeatable)")
    p.add_argument("--collection-b", action="append", default=[], help="Secondary collection folder (repeatable)")

    p.add_argument("--no-protect-system", action="store_true")
    p.add_argument("--skip-hidden", action="store_true")
    p.add_argument("--follow-symlinks", action="store_true")

    p.add_argument("--exclude", action="append", default=[], help="Exclude pattern (repeatable)")
    p.add_argument("--include", action="append", default=[], help="Include pattern (repeatable)")

    p.add_argument("--output-json", default="")
    p.add_argument("--output-csv", default="")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def main() -> int:
    args = _parse_args()
    strings.set_language(args.lang)

    folders = [os.path.abspath(p) for p in args.folders if p]
    if not folders:
        print("No folders provided", file=sys.stderr)
        return 2

    missing = [p for p in folders if not os.path.isdir(p)]
    if missing:
        print(f"Invalid folder(s): {missing}", file=sys.stderr)
        return 2

    exts = [x.strip() for x in str(args.extensions or "").split(",") if x.strip()]

    state: dict[str, Any] = {
        "results": None,
        "error": None,
        "cancelled": False,
    }

    def emit_success(message: str) -> None:
        if args.quiet:
            return
        print(message)

    cfg = ScanConfig(
        folders=folders,
        extensions=exts or [],
        min_size_kb=max(0, int(args.min_size_kb or 0)),
        same_name=bool(args.same_name),
        name_only=bool(args.name_only),
        byte_compare=bool(args.byte_compare),
        protect_system=not bool(args.no_protect_system),
        skip_hidden=bool(args.skip_hidden),
        follow_symlinks=bool(args.follow_symlinks),
        include_patterns=list(args.include or []),
        exclude_patterns=list(args.exclude or []),
        # Mixed mode always requires similar-image pass.
        use_similar_image=bool(args.similar_image or args.mixed_mode),
        use_similar_document=bool(getattr(args, "similar_document", False)),
        use_mixed_mode=bool(args.mixed_mode),
        detect_duplicate_folders=bool(args.detect_folder_dup),
        incremental_rescan=bool(args.incremental_rescan),
        baseline_session_id=int(args.baseline_session) if int(args.baseline_session or 0) > 0 else None,
        similarity_threshold=float(args.similarity_threshold or 0.9),
        document_similarity_threshold=float(getattr(args, "document_threshold", 0.9) or 0.9),
        selection_policy=str(getattr(args, "selection_policy", "smart") or "smart"),
        compare_mode=str(getattr(args, "compare_mode", "none") or "none"),
        watch_mode=bool(getattr(args, "watch", False)),
        apply_exemptions=bool(getattr(args, "respect_exemptions", False)),
        post_cleanup_empty_dirs=bool(getattr(args, "post_cleanup_empty_dirs", False)),
        strict_mode=bool(getattr(args, "strict_mode", False)),
        strict_max_errors=max(0, int(getattr(args, "strict_max_errors", 0) or 0)),
    )
    if cfg.compare_mode == "collections":
        folder_roles = {}
        for path in list(getattr(args, "collection_a", []) or []):
            folder_roles[os.path.abspath(path)] = "primary"
        for path in list(getattr(args, "collection_b", []) or []):
            folder_roles[os.path.abspath(path)] = "secondary"
        if not folder_roles and len(folders) >= 2:
            folder_roles[folders[0]] = "primary"
            folder_roles[folders[1]] = "secondary"
        cfg.folder_roles = folder_roles
    dep_error_key = validate_similar_image_dependency(cfg)
    if not dep_error_key:
        dep_error_key = validate_similar_document_dependency(cfg)
    if dep_error_key:
        print(strings.tr(dep_error_key), file=sys.stderr)
        return 2
    worker = ScanWorker(folders, **build_scan_worker_kwargs(cfg, session_id=None, use_cached_files=False))

    def on_progress(v: int, msg: str) -> None:
        if args.quiet:
            return
        print(f"[{v:3d}%] {msg}")

    def on_finished(results: object) -> None:
        if isinstance(results, dict):
            state["results"] = results
        else:
            state["results"] = {}

    def on_failed(message: str) -> None:
        state["error"] = str(message)

    def on_cancelled() -> None:
        state["cancelled"] = True

    worker.progress_updated.connect(on_progress)
    worker.scan_finished.connect(on_finished)
    worker.scan_failed.connect(on_failed)
    worker.scan_cancelled.connect(on_cancelled)
    # Run synchronously to avoid creating a process-global Qt application
    # in CLI mode (prevents cross-mode CLI->GUI lifecycle conflicts).
    worker.run()

    if state["error"]:
        print(f"Scan failed: {state['error']}", file=sys.stderr)
        return 1
    if state["cancelled"]:
        print("Scan cancelled", file=sys.stderr)
        return 130

    results = dict(state["results"] or {})
    group_count = len(results)
    file_count = sum(len(v or []) for v in results.values())
    scan_status = str(getattr(worker, "latest_scan_status", "completed") or "completed")
    metrics = dict(getattr(worker, "latest_scan_metrics", {}) or {})
    warnings = list(getattr(worker, "latest_scan_warnings", []) or [])
    if scan_status == "partial" and "strict_mode_threshold_exceeded" not in warnings:
        warnings.append("strict_mode_threshold_exceeded")
    emit_success(
        f"Done. status={scan_status}, groups={group_count}, files={file_count}, errors={int(metrics.get('errors_total', 0) or 0)}"
    )

    if args.output_json:
        out_json = os.path.abspath(args.output_json)
        payload = dump_results_v3(
            scan_results=results,
            folders=folders,
            source="cli",
            selected_paths=[],
            file_meta=dict(getattr(worker, "latest_file_meta", {}) or {}),
            existence_map={p: True for p in dict(getattr(worker, "latest_file_meta", {}) or {}).keys()},
            selection_reason_map=dict(getattr(worker, "latest_selection_reason_map", {}) or {}),
            exemption_status_map=dict(getattr(worker, "latest_exemption_status_map", {}) or {}),
            review_state_map=dict(getattr(worker, "latest_result_review_state_map", {}) or {}),
            collection_role_map=dict(getattr(worker, "latest_collection_role_map", {}) or {}),
            baseline_delta_map=dict(getattr(worker, "latest_baseline_delta_map", {}) or {}),
        )
        payload_meta = payload.setdefault("meta", {})
        payload_meta["scan_status"] = scan_status
        payload_meta["metrics"] = metrics
        payload_meta["warnings"] = warnings
        payload_meta["groups"] = group_count
        payload_meta["files"] = file_count
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        emit_success(f"Saved JSON: {out_json}")

    if args.output_csv:
        out_csv = os.path.abspath(args.output_csv)
        baseline_delta_map = {}
        try:
            baseline_delta_map = dict(getattr(worker, "latest_baseline_delta_map", {}) or {})
        except Exception:
            baseline_delta_map = {}
        g, r = export_scan_results_csv(
            scan_results=results,
            out_path=out_csv,
            selected_paths=[],
            file_meta=dict(getattr(worker, "latest_file_meta", {}) or {}),
            baseline_delta_map=baseline_delta_map,
            selection_reason_map=dict(getattr(worker, "latest_selection_reason_map", {}) or {}),
            exemption_status_map=dict(getattr(worker, "latest_exemption_status_map", {}) or {}),
            review_state_map=dict(getattr(worker, "latest_result_review_state_map", {}) or {}),
            collection_role_map=dict(getattr(worker, "latest_collection_role_map", {}) or {}),
        )
        emit_success(f"Saved CSV: {out_csv} (groups={g}, rows={r})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
