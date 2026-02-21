import csv

from src.ui.exporting import export_scan_results_csv
import src.ui.exporting as exporting_module


def _write_file(path, data=b"x"):
    path.write_bytes(data)
    return str(path)


def test_export_scan_results_handles_various_group_keys(tmp_path):
    a = _write_file(tmp_path / "a.txt", b"aaa")
    b = _write_file(tmp_path / "b.txt", b"bbb")
    c = _write_file(tmp_path / "c.txt", b"ccc")

    scan_results = {
        ("NAME_ONLY", "foo.txt"): [a, b],
        ("deadbeefcafebabe", 123): [c],
        ("similar_1", 999): [a],
        ("byte_compare", "byte_1", 10): [b],
        ("FOLDER_DUP", "sig", 4096, 3): [str(tmp_path / "dirA"), str(tmp_path / "dirB")],
    }

    out = tmp_path / "out.csv"
    groups, rows = export_scan_results_csv(scan_results=scan_results, out_path=str(out), selected_paths=[a])

    assert groups == 5
    assert rows == 7
    assert out.exists()

    # Basic CSV sanity: header + rows
    with out.open("r", encoding="utf-8-sig", newline="") as f:
        r = list(csv.reader(f))
    assert len(r) == 1 + rows
    assert r[0][0] == "group_type"
    assert "group_kind" in r[0]


def test_export_scan_results_prefers_file_meta_without_fs_calls(tmp_path, monkeypatch):
    p1 = str(tmp_path / "x.txt")
    p2 = str(tmp_path / "y.txt")
    scan_results = {("deadbeef", 10): [p1, p2]}
    file_meta = {p1: (10, 1000.0), p2: (20, 2000.0)}

    def fail_exists(_path):
        raise AssertionError("os.path.exists should not be called when file_meta is provided")

    monkeypatch.setattr(exporting_module.os.path, "exists", fail_exists)

    out = tmp_path / "meta.csv"
    groups, rows = export_scan_results_csv(
        scan_results=scan_results,
        out_path=str(out),
        selected_paths=[],
        file_meta=file_meta,
    )
    assert groups == 1
    assert rows == 2
    assert out.exists()
