import json
import sys

from PySide6.QtCore import QTimer

import cli


class _Signal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args):
        for cb in list(self._callbacks):
            cb(*args)


class _FakeWorker:
    def __init__(self, *_args, **_kwargs):
        self.progress_updated = _Signal()
        self.scan_finished = _Signal()
        self.scan_failed = _Signal()
        self.scan_cancelled = _Signal()
        self.latest_scan_status = "partial"
        self.latest_scan_metrics = {"errors_total": 2, "files_scanned": 10}
        self.latest_scan_warnings = ["strict_mode_threshold_exceeded"]

    def start(self):
        self.progress_updated.emit(100, "Done")
        QTimer.singleShot(0, lambda: self.scan_finished.emit({("hash", 1): ["a", "b"]}))


def test_cli_parses_strict_flags(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["pyduplicate-cli", "C:/dummy", "--strict-mode", "--strict-max-errors", "7"],
    )
    args = cli._parse_args()
    assert args.strict_mode is True
    assert args.strict_max_errors == 7


def test_cli_json_meta_contains_scan_status_and_metrics(tmp_path, monkeypatch):
    out_json = tmp_path / "out.json"
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()

    monkeypatch.setattr(cli, "ScanWorker", _FakeWorker)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pyduplicate-cli",
            str(scan_dir),
            "--strict-mode",
            "--strict-max-errors",
            "0",
            "--output-json",
            str(out_json),
            "--quiet",
        ],
    )

    rc = cli.main()
    assert rc == 0
    assert out_json.exists()

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert "meta" in data
    assert data["meta"]["scan_status"] == "partial"
    assert "metrics" in data["meta"]
    assert int(data["meta"]["metrics"]["errors_total"]) == 2
    assert "warnings" in data["meta"]
    assert "strict_mode_threshold_exceeded" in data["meta"]["warnings"]
