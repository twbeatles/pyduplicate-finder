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
        mixed_mode=False,
        detect_folder_dup=False,
        incremental_rescan=False,
        baseline_session=0,
        similarity_threshold=0.9,
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

        def start(self):
            self.scan_finished.emit({("hash1", 10): ["a.bin", "b.bin"]})

    class _FakeEventLoop:
        def exec(self):
            return 0

        def quit(self):
            return None

    class _FakeCoreApplication:
        @staticmethod
        def instance():
            return object()

        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(cli, "ScanWorker", _FakeWorker)
    monkeypatch.setattr(cli, "QEventLoop", _FakeEventLoop)
    monkeypatch.setattr(cli, "QCoreApplication", _FakeCoreApplication)

    code = cli.main()
    assert code == 0
    assert out_json.exists()

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["version"] == 2
    assert set(data.keys()) == {"version", "meta", "results"}
    assert data["meta"]["groups"] == 1
    assert data["meta"]["files"] == 2
    assert data["meta"]["source"] == "cli"
    assert isinstance(data["results"], dict)
