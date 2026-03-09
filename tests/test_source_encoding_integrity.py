from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {".py", ".md", ".txt", ".ini", ".json", ".toml", ".yaml", ".yml", ".spec"}
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", "build", "dist"}
BROKEN_TEXT_PATTERNS = ("?뵇", "以鍮꾨맖")


def _iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        yield path


def test_repository_text_files_are_valid_utf8_without_replacement_chars():
    invalid_utf8 = []
    replacement_char_paths = []

    for path in _iter_text_files():
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            invalid_utf8.append(path)
            continue

        if "\ufffd" in text:
            replacement_char_paths.append(path)

    assert not invalid_utf8, f"Invalid UTF-8 files: {[str(p.relative_to(ROOT)) for p in invalid_utf8]}"
    assert not replacement_char_paths, (
        "Files containing Unicode replacement character: "
        f"{[str(p.relative_to(ROOT)) for p in replacement_char_paths]}"
    )


def test_repository_text_files_do_not_contain_known_mojibake_patterns():
    hits: list[str] = []
    for path in _iter_text_files():
        if path.name == "test_source_encoding_integrity.py":
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in BROKEN_TEXT_PATTERNS:
            if pattern in text:
                hits.append(f"{path.relative_to(ROOT)}::{pattern}")
    assert not hits, f"Known mojibake patterns found: {hits}"
