from pathlib import Path


def test_empty_folder_finder_uses_i18n_instead_of_hardcoded_status_text():
    content = Path("src/core/empty_folder_finder.py").read_text(encoding="utf-8")
    assert '"Complete"' not in content
    assert 'f"Error: {e}"' not in content
    assert "strings.tr(" in content


def test_preset_dialog_tooltip_uses_i18n_key():
    content = Path("src/ui/dialogs/preset_dialog.py").read_text(encoding="utf-8")
    assert "Created:" not in content
    assert "preset_created_at" in content
