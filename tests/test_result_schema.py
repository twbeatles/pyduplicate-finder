import json

from src.core.result_schema import dump_results_v2, load_results_any, load_results_bundle_any


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


def test_dump_results_v2_bundle_round_trip_with_extended_meta():
    source = {
        ("deadbeef", 10): ["a", "b"],
    }
    payload = dump_results_v2(
        scan_results=source,
        folders=["D:/scan"],
        source="gui",
        generated_at=123.0,
        selected_paths=["b", "missing-path"],
        file_meta={"a": (10, 1.5), "b": (10, 2.5), "orphan": (99, 3.5)},
        baseline_delta_map={"a": "new", "b": "changed", "orphan": "revalidated", "bad": "ignored"},
        existence_map={"a": True, "b": False, "ghost": True},
    )

    meta = payload["meta"]
    assert meta["selected_paths"] == ["b"]
    assert meta["file_meta"]["a"] == {"size": 10, "mtime": 1.5, "exists": True}
    assert meta["file_meta"]["b"] == {"size": 10, "mtime": 2.5, "exists": False}
    assert meta["baseline_delta_map"] == {"a": "new", "b": "changed"}

    bundle = load_results_bundle_any(payload)
    assert bundle["results"] == source
    assert bundle["selected_paths"] == ["b"]
    assert bundle["file_meta"] == {"a": (10, 1.5), "b": (10, 2.5)}
    assert bundle["existence_map"] == {"a": True, "b": False}
    assert bundle["baseline_delta_map"] == {"a": "new", "b": "changed"}


def test_load_results_bundle_any_defaults_for_legacy_payload():
    payload = {
        json.dumps(["hash_a", 123]): ["a.txt", "b.txt"],
    }
    bundle = load_results_bundle_any(payload)
    assert bundle["results"] == {("hash_a", 123): ["a.txt", "b.txt"]}
    assert bundle["selected_paths"] == []
    assert bundle["file_meta"] == {}
    assert bundle["existence_map"] == {}
    assert bundle["baseline_delta_map"] == {}
