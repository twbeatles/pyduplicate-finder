import json

from src.core.preset_manager import PresetManager


def test_load_legacy_preset_merges_new_default_keys(tmp_path):
    pm = PresetManager(preset_dir=str(tmp_path))
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(
        json.dumps(
            {
                "name": "legacy",
                "created_at": "2026-02-26T00:00:00",
                "config": {
                    "folders": ["D:/data"],
                    "use_similar_image": True,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    cfg = pm.load_preset("legacy")
    assert cfg is not None
    assert cfg["use_similar_image"] is True
    assert "use_mixed_mode" in cfg
    assert "detect_duplicate_folders" in cfg
    assert "incremental_rescan" in cfg
    assert "baseline_session_id" in cfg


def test_save_preset_writes_schema_version_2(tmp_path):
    pm = PresetManager(preset_dir=str(tmp_path))
    ok = pm.save_preset("new_schema", {"folders": [], "use_similar_image": False})
    assert ok is True

    data = json.loads((tmp_path / "new_schema.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert "config" in data
