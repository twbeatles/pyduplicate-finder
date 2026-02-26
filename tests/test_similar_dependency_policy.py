import argparse

import pytest
from PySide6.QtWidgets import QApplication

import cli
import src.ui.main_window as main_window_module
from src.ui.main_window import DuplicateFinderApp


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _setup_window(tmp_path, monkeypatch):
    monkeypatch.setenv("PYDUPLICATEFINDER_DB_PATH", str(tmp_path / "scan_cache.db"))
    w = DuplicateFinderApp()
    try:
        w._scheduler_timer.stop()
    except Exception:
        pass
    return w


def test_gui_fail_fast_when_similar_dependency_missing(tmp_path, monkeypatch, qapp):
    w = _setup_window(tmp_path, monkeypatch)
    warned = {"count": 0}
    try:
        scan_root = tmp_path / "scan"
        scan_root.mkdir()
        w.selected_folders = [str(scan_root)]
        w.chk_similar_image.setChecked(True)

        monkeypatch.setattr(
            main_window_module,
            "validate_similar_image_dependency",
            lambda _cfg: "err_similar_image_dependency",
        )
        monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *_a, **_k: warned.__setitem__("count", warned["count"] + 1))
        monkeypatch.setattr(
            w.scan_controller,
            "build_worker",
            lambda **_kwargs: (_ for _ in ()).throw(AssertionError("worker must not start on dependency failure")),
        )

        w.start_scan()

        assert warned["count"] == 1
        assert not w.btn_stop_scan.isEnabled()
    finally:
        w.close()


def test_cli_fail_fast_when_similar_dependency_missing(tmp_path, monkeypatch, capsys):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()

    args = argparse.Namespace(
        folders=[str(scan_root)],
        lang="en",
        extensions="",
        min_size_kb=0,
        same_name=False,
        name_only=False,
        byte_compare=False,
        similar_image=True,
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
        output_json="",
        output_csv="",
        quiet=True,
    )
    monkeypatch.setattr(cli, "_parse_args", lambda: args)
    monkeypatch.setattr(cli, "validate_similar_image_dependency", lambda _cfg: "err_similar_image_dependency")
    monkeypatch.setattr(
        cli,
        "QCoreApplication",
        type(
            "_FakeCoreApplication",
            (),
            {
                "instance": staticmethod(lambda: object()),
                "__init__": lambda self, *_a, **_k: None,
            },
        ),
    )
    monkeypatch.setattr(
        cli,
        "ScanWorker",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("worker must not be created")),
    )

    code = cli.main()
    captured = capsys.readouterr()

    assert code == 2
    assert "imagehash" in (captured.err or "").lower()
