import json

from src.core.result_schema import dump_results_v2, load_results_any


def test_load_results_any_supports_legacy_gui_top_level_map():
    payload = {
        json.dumps(["hash_a", 123]): ["a.txt", "b.txt"],
    }
    out = load_results_any(payload)
    assert out == {("hash_a", 123): ["a.txt", "b.txt"]}


def test_load_results_any_supports_legacy_cli_meta_results_format():
    payload = {
        "meta": {"groups": 1, "files": 2, "folders": ["C:/data"]},
        "results": {"('hash_b', 456)": ["x.bin", "y.bin"]},
    }
    out = load_results_any(payload)
    assert out == {("hash_b", 456): ["x.bin", "y.bin"]}


def test_dump_results_v2_round_trip_with_loader():
    source = {
        ("deadbeef", 10): ["a", "b"],
        ("NAME_ONLY", "foo.txt"): ["c"],
    }
    payload = dump_results_v2(scan_results=source, folders=["D:/scan"], source="gui", generated_at=123.0)

    assert payload["version"] == 2
    assert payload["meta"]["groups"] == 2
    assert payload["meta"]["files"] == 3
    assert payload["meta"]["folders"] == ["D:/scan"]
    assert payload["meta"]["generated_at"] == 123.0
    assert payload["meta"]["source"] == "gui"
    assert isinstance(payload["results"], dict)

    loaded = load_results_any(payload)
    assert loaded == source
