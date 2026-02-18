import csv

from src.ui.exporting import export_scan_results_csv


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
