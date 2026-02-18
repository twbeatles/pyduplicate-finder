import argparse
import json
import os
import sys
from typing import Any

from PySide6.QtCore import QCoreApplication, QEventLoop

from src.core.scan_engine import ScanConfig, build_scan_worker_kwargs
from src.core.scanner import ScanWorker
from src.ui.exporting import export_scan_results_csv
from src.utils.i18n import strings


def _serialize_results(scan_results: dict[Any, list[str]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, paths in (scan_results or {}).items():
        out[str(tuple(key))] = list(paths or [])
    return out


def _parse_args() -> argparse.Namespace:
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
    p.add_argument("--mixed-mode", action="store_true")
    p.add_argument("--detect-folder-dup", action="store_true")
    p.add_argument("--incremental-rescan", action="store_true")
    p.add_argument("--baseline-session", type=int, default=0)
    p.add_argument("--similarity-threshold", type=float, default=0.9)

    p.add_argument("--no-protect-system", action="store_true")
    p.add_argument("--skip-hidden", action="store_true")
    p.add_argument("--follow-symlinks", action="store_true")

    p.add_argument("--exclude", action="append", default=[], help="Exclude pattern (repeatable)")
    p.add_argument("--include", action="append", default=[], help="Include pattern (repeatable)")

    p.add_argument("--output-json", default="")
    p.add_argument("--output-csv", default="")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


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

    app = QCoreApplication.instance() or QCoreApplication([])
    loop = QEventLoop()

    state: dict[str, Any] = {
        "results": None,
        "error": None,
        "cancelled": False,
    }

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
        use_similar_image=bool(args.similar_image),
        use_mixed_mode=bool(args.mixed_mode),
        detect_duplicate_folders=bool(args.detect_folder_dup),
        incremental_rescan=bool(args.incremental_rescan),
        baseline_session_id=int(args.baseline_session) if int(args.baseline_session or 0) > 0 else None,
        similarity_threshold=float(args.similarity_threshold or 0.9),
    )
    worker = ScanWorker(folders, **build_scan_worker_kwargs(cfg, session_id=None, use_cached_files=False))

    def on_progress(v: int, msg: str) -> None:
        if args.quiet:
            return
        print(f"[{v:3d}%] {msg}")

    def on_finished(results: object) -> None:
        state["results"] = dict(results or {})
        loop.quit()

    def on_failed(message: str) -> None:
        state["error"] = str(message)
        loop.quit()

    def on_cancelled() -> None:
        state["cancelled"] = True
        loop.quit()

    worker.progress_updated.connect(on_progress)
    worker.scan_finished.connect(on_finished)
    worker.scan_failed.connect(on_failed)
    worker.scan_cancelled.connect(on_cancelled)
    worker.start()
    loop.exec()

    if state["error"]:
        print(f"Scan failed: {state['error']}", file=sys.stderr)
        return 1
    if state["cancelled"]:
        print("Scan cancelled", file=sys.stderr)
        return 130

    results = dict(state["results"] or {})
    group_count = len(results)
    file_count = sum(len(v or []) for v in results.values())
    print(f"Done. groups={group_count}, files={file_count}")

    if args.output_json:
        out_json = os.path.abspath(args.output_json)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "meta": {
                        "groups": group_count,
                        "files": file_count,
                        "folders": folders,
                    },
                    "results": _serialize_results(results),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        print(f"Saved JSON: {out_json}")

    if args.output_csv:
        out_csv = os.path.abspath(args.output_csv)
        g, r = export_scan_results_csv(scan_results=results, out_path=out_csv, selected_paths=[])
        print(f"Saved CSV: {out_csv} (groups={g}, rows={r})")

    # Keep app reference alive until end of function.
    _ = app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
