from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication

from src.core.scanner import ScanWorker
from src.ui.components.results_tree import ResultsTreeWidget


def _make_dataset(root: Path, files: int, groups: int) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    group_size = max(2, files // max(1, groups))
    payloads = [f"group-{i}".encode("utf-8") * 32 for i in range(max(1, groups))]
    for i in range(files):
        g = i % len(payloads)
        d = root / f"d{i % 128:03d}"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"f{i:07d}.bin"
        p.write_bytes(payloads[g])
        paths.append(str(p))
    return paths


def _drain_tree(widget: ResultsTreeWidget):
    guard = 0
    while widget._populate_timer.isActive() and guard < 100000:
        widget._process_batch()
        guard += 1


def run_bench(files: int, groups: int, output: str) -> dict:
    app = QApplication.instance() or QApplication([])
    _ = app
    with tempfile.TemporaryDirectory(prefix="pydup-bench-") as td:
        root = Path(td) / "dataset"
        _make_dataset(root, files=files, groups=groups)

        t0 = time.perf_counter()
        worker = ScanWorker([str(root)], max_workers=max(1, os.cpu_count() or 4))
        holder = {"results": {}}
        worker.scan_finished.connect(lambda r: holder.__setitem__("results", dict(r or {})))
        worker.run()
        scan_time = time.perf_counter() - t0
        results = dict(holder.get("results", {}) or {})
        file_meta = dict(getattr(worker, "latest_file_meta", {}) or {})

        tree = ResultsTreeWidget()
        t1 = time.perf_counter()
        tree.populate(results, selected_paths=[], file_meta=file_meta, existence_map={p: True for p in file_meta})
        _drain_tree(tree)
        render_time = time.perf_counter() - t1

        t2 = time.perf_counter()
        tree.apply_filter("f0001")
        filter_time = time.perf_counter() - t2

        out = {
            "files": int(files),
            "groups_seed": int(groups),
            "scan_time_sec": scan_time,
            "render_time_sec": render_time,
            "filter_time_sec": filter_time,
            "result_groups": int(len(results)),
            "result_files_meta": int(len(file_meta)),
        }
        Path(output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def main():
    p = argparse.ArgumentParser(description="Local performance benchmark for PyDuplicate Finder Pro")
    p.add_argument("--files", type=int, default=200000)
    p.add_argument("--groups", type=int, default=5000)
    p.add_argument("--output", type=str, default="bench_perf.json")
    args = p.parse_args()

    out = run_bench(files=max(10, int(args.files)), groups=max(1, int(args.groups)), output=str(args.output))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
