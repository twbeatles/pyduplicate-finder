import argparse
import json

import pytest

import cli
from cli import _parse_args


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", 0.0),
        ("1", 1.0),
        ("0.9", 0.9),
    ],
)
def test_parse_args_accepts_similarity_threshold_boundary_values(raw, expected):
    args = _parse_args(["D:/scan-target", "--similarity-threshold", raw])
    assert float(args.similarity_threshold) == expected


@pytest.mark.parametrize("raw", ["-0.1", "1.5"])
def test_parse_args_rejects_similarity_threshold_out_of_range(raw):
    with pytest.raises(SystemExit) as ex:
        _parse_args(["D:/scan-target", "--similarity-threshold", raw])
    assert int(ex.value.code or 0) == 2


def test_main_writes_output_json_in_v2_schema(tmp_path, monkeypatch):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    out_json = tmp_path / "out.json"

    args = argparse.Namespace(
        folders=[str(scan_root)],
        lang="en",
        extensions="",
        min_size_kb=0,
        same_name=False,
        name_only=False,
        byte_compare=False,
        similar_image=False,
        similar_document=False,
        mixed_mode=False,
        detect_folder_dup=False,
        incremental_rescan=False,
        baseline_session=0,
        similarity_threshold=0.9,
        document_threshold=0.9,
        selection_policy="smart",
        compare_mode="none",
        watch=False,
        respect_exemptions=False,
        post_cleanup_empty_dirs=False,
        collection_a=[],
        collection_b=[],
        no_protect_system=False,
        skip_hidden=False,
        follow_symlinks=False,
        exclude=[],
        include=[],
        output_json=str(out_json),
        output_csv="",
        quiet=True,
    )
    monkeypatch.setattr(cli, "_parse_args", lambda: args)

    class _Signal:
        def __init__(self):
            self._callbacks = []

        def connect(self, cb):
            self._callbacks.append(cb)

        def emit(self, *a):
            for cb in list(self._callbacks):
                cb(*a)

    class _FakeWorker:
        def __init__(self, *_args, **_kwargs):
            self.progress_updated = _Signal()
            self.scan_finished = _Signal()
            self.scan_failed = _Signal()
            self.scan_cancelled = _Signal()

        def run(self):
            self.scan_finished.emit({("hash1", 10): ["a.bin", "b.bin"]})

    monkeypatch.setattr(cli, "ScanWorker", _FakeWorker)

    code = cli.main()
    assert code == 0
    assert out_json.exists()

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["version"] == 3
    assert set(data.keys()) == {"version", "meta", "results"}
    assert data["meta"]["groups"] == 1
    assert data["meta"]["files"] == 2
    assert data["meta"]["source"] == "cli"
    assert isinstance(data["results"], dict)


def test_main_mixed_mode_auto_enables_similar_image(tmp_path, monkeypatch):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()

    args = argparse.Namespace(
        folders=[str(scan_root)],
        lang="en",
        extensions="",
        min_size_kb=0,
        same_name=False,
        name_only=False,
        byte_compare=False,
        similar_image=False,
        similar_document=False,
        mixed_mode=True,
        detect_folder_dup=False,
        incremental_rescan=False,
        baseline_session=0,
        similarity_threshold=0.9,
        document_threshold=0.9,
        selection_policy="smart",
        compare_mode="none",
        watch=False,
        respect_exemptions=False,
        post_cleanup_empty_dirs=False,
        collection_a=[],
        collection_b=[],
        strict_mode=False,
        strict_max_errors=0,
        no_protect_system=False,
        skip_hidden=False,
        follow_symlinks=False,
        exclude=[],
        include=[],
        output_json="",
        output_csv="",
        quiet=True,
    )
    monkeypatch.setattr(cli, "_parse_args", lambda: args)
    monkeypatch.setattr(cli, "validate_similar_image_dependency", lambda _cfg: None)

    captured_kwargs = {}

    class _Signal:
        def __init__(self):
            self._callbacks = []

        def connect(self, cb):
            self._callbacks.append(cb)

        def emit(self, *a):
            for cb in list(self._callbacks):
                cb(*a)

    class _FakeWorker:
        def __init__(self, *_args, **kwargs):
            captured_kwargs.update(kwargs)
            self.progress_updated = _Signal()
            self.scan_finished = _Signal()
            self.scan_failed = _Signal()
            self.scan_cancelled = _Signal()

        def run(self):
            self.scan_finished.emit({})

    monkeypatch.setattr(cli, "ScanWorker", _FakeWorker)

    code = cli.main()
    assert code == 0
    assert captured_kwargs["use_mixed_mode"] is True
    assert captured_kwargs["use_similar_image"] is True


def test_main_does_not_leave_plain_qcoreapplication_instance(tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication

    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()

    args = argparse.Namespace(
        folders=[str(scan_root)],
        lang="en",
        extensions="",
        min_size_kb=0,
        same_name=False,
        name_only=False,
        byte_compare=False,
        similar_image=False,
        similar_document=False,
        mixed_mode=False,
        detect_folder_dup=False,
        incremental_rescan=False,
        baseline_session=0,
        similarity_threshold=0.9,
        document_threshold=0.9,
        selection_policy="smart",
        compare_mode="none",
        watch=False,
        respect_exemptions=False,
        post_cleanup_empty_dirs=False,
        collection_a=[],
        collection_b=[],
        strict_mode=False,
        strict_max_errors=0,
        no_protect_system=False,
        skip_hidden=False,
        follow_symlinks=False,
        exclude=[],
        include=[],
        output_json="",
        output_csv="",
        quiet=True,
    )
    monkeypatch.setattr(cli, "_parse_args", lambda: args)

    class _Signal:
        def __init__(self):
            self._callbacks = []

        def connect(self, cb):
            self._callbacks.append(cb)

        def emit(self, *a):
            for cb in list(self._callbacks):
                cb(*a)

    class _FakeWorker:
        def __init__(self, *_args, **_kwargs):
            self.progress_updated = _Signal()
            self.scan_finished = _Signal()
            self.scan_failed = _Signal()
            self.scan_cancelled = _Signal()

        def run(self):
            self.scan_finished.emit({})

    monkeypatch.setattr(cli, "ScanWorker", _FakeWorker)
    assert cli.main() == 0

    inst = QCoreApplication.instance()
    assert inst is None or isinstance(inst, QApplication)

def test_main_quiet_suppresses_success_stdout(tmp_path, monkeypatch, capsys):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    out_json = tmp_path / "out.json"
    out_csv = tmp_path / "out.csv"

    args = argparse.Namespace(
        folders=[str(scan_root)],
        lang="en",
        extensions="",
        min_size_kb=0,
        same_name=False,
        name_only=False,
        byte_compare=False,
        similar_image=False,
        similar_document=False,
        mixed_mode=False,
        detect_folder_dup=False,
        incremental_rescan=False,
        baseline_session=0,
        similarity_threshold=0.9,
        document_threshold=0.9,
        selection_policy="smart",
        compare_mode="none",
        watch=False,
        respect_exemptions=False,
        post_cleanup_empty_dirs=False,
        collection_a=[],
        collection_b=[],
        strict_mode=False,
        strict_max_errors=0,
        no_protect_system=False,
        skip_hidden=False,
        follow_symlinks=False,
        exclude=[],
        include=[],
        output_json=str(out_json),
        output_csv=str(out_csv),
        quiet=True,
    )
    monkeypatch.setattr(cli, "_parse_args", lambda: args)

    class _Signal:
        def __init__(self):
            self._callbacks = []

        def connect(self, cb):
            self._callbacks.append(cb)

        def emit(self, *a):
            for cb in list(self._callbacks):
                cb(*a)

    class _FakeWorker:
        def __init__(self, *_args, **_kwargs):
            self.progress_updated = _Signal()
            self.scan_finished = _Signal()
            self.scan_failed = _Signal()
            self.scan_cancelled = _Signal()
            self.latest_file_meta = {}
            self.latest_baseline_delta_map = {}
            self.latest_selection_reason_map = {}
            self.latest_exemption_status_map = {}
            self.latest_result_review_state_map = {}
            self.latest_collection_role_map = {}
            self.latest_scan_metrics = {}
            self.latest_scan_status = "completed"
            self.latest_scan_warnings = []

        def run(self):
            self.progress_updated.emit(100, "Done")
            self.scan_finished.emit({("hash", 1): ["a", "b"]})

    monkeypatch.setattr(cli, "ScanWorker", _FakeWorker)

    assert cli.main() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_parse_args_supports_new_policy_and_compare_flags():
    args = _parse_args(
        [
            "D:/scan-target",
            "--selection-policy",
            "primary_keep",
            "--compare-mode",
            "collections",
            "--similar-document",
            "--document-threshold",
            "0.8",
            "--watch",
            "--respect-exemptions",
        ]
    )
    assert args.selection_policy == "primary_keep"
    assert args.compare_mode == "collections"
    assert args.similar_document is True
    assert float(args.document_threshold) == 0.8
    assert args.watch is True
    assert args.respect_exemptions is True


def test_cli_unsupported_watch_and_post_cleanup_fail_fast(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "pyduplicate-cli",
            str(tmp_path),
            "--watch",
            "--post-cleanup-empty-dirs",
        ],
    )

    assert cli.main() == 2
    captured = capsys.readouterr()
    assert "--watch" in captured.err
    assert "--post-cleanup-empty-dirs" in captured.err
