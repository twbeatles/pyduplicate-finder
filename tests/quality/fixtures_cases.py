"""Deterministic real-file case set (Phase 0 contract).

Covers the plan's required categories with small (1 KiB grade) and large
(16 MiB grade, opt-in via env) byte payloads:

- identical bytes / same name different bytes
- empty files, same-size-different-content, partial-prefix collisions
- unicode / emoji / case-variant names
- hidden files, mtime skew, read-only files
- hardlink / symlink entries
- locked (open-handle) files are exercised by the FS tests, not built here
"""

from __future__ import annotations

import os
from pathlib import Path

from tests.quality.safety import write_bytes

SMALL = 1024  # 1 KiB grade (always built)
LARGE = 16 * 1024 * 1024  # 16 MiB grade (opt-in)


def _pattern(seed: int, size: int) -> bytes:
    return bytes(((seed + i) % 251 for i in range(size)))


def build_case_set(root: Path, *, large: bool = False) -> dict:
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    paths: dict = {}

    # 1-2: identical bytes in different paths (must group).
    payload = _pattern(7, SMALL)
    paths["dup_a"] = write_bytes(data / "dup_a.bin", payload)
    paths["dup_b"] = write_bytes(data / "subdir" / "dup_b.bin", payload)

    # 3-4: same name, different bytes (must NOT group as exact duplicates).
    paths["same_name_a"] = write_bytes(data / "same1" / "report.txt", b"content-alpha")
    paths["same_name_b"] = write_bytes(data / "same2" / "report.txt", b"content-beta-XXXX")

    # 5-6: empty files.
    paths["empty_a"] = write_bytes(data / "empty_a.bin", b"")
    paths["empty_b"] = write_bytes(data / "empty_b.bin", b"")

    # 7-8: same size, different content.
    paths["samesize_a"] = write_bytes(data / "samesize_a.bin", b"A" * SMALL)
    paths["samesize_b"] = write_bytes(data / "samesize_b.bin", b"B" * SMALL)

    # 9-10: same 4 KiB prefix, different tails (partial-hash collision shape).
    paths["prefix_a"] = write_bytes(data / "prefix_a.bin", b"P" * 4096 + b"TAIL-ONE-" * 64)
    paths["prefix_b"] = write_bytes(data / "prefix_b.bin", b"P" * 4096 + b"TAIL-TWO-" * 64)

    # 11-14: unicode / emoji / case variants.
    paths["korean"] = write_bytes(data / "한글_파일.txt", "한글 내용".encode("utf-8"))
    paths["korean_dup"] = write_bytes(data / "sub2" / "한글_파일_copy.txt", "한글 내용".encode("utf-8"))
    paths["emoji"] = write_bytes(data / "emoji_😀.txt", b"emoji-bytes")
    paths["case_a"] = write_bytes(data / "CaseName.TXT", b"case-bytes")
    paths["case_b"] = write_bytes(data / "casename.txt", b"case-bytes")

    # 15-16: hidden files (dotfiles) with identical bytes.
    hidden_payload = _pattern(99, SMALL)
    paths["hidden_a"] = write_bytes(data / ".hidden_a", hidden_payload)
    paths["hidden_b"] = write_bytes(data / ".hidden_b", hidden_payload)

    # 17: read-only file + identical writable twin.
    ro_payload = _pattern(31, SMALL)
    paths["readonly_src"] = write_bytes(data / "ro_src.bin", ro_payload)
    paths["readonly_twin"] = write_bytes(data / "ro_twin.bin", ro_payload)
    try:
        os.chmod(paths["readonly_src"], 0o444)
    except OSError:
        pass

    # 18: mtime-skewed identical twin (content equal, mtime differs by 1 day).
    mt_payload = _pattern(55, SMALL)
    paths["mtime_a"] = write_bytes(data / "mtime_a.bin", mt_payload)
    paths["mtime_b"] = write_bytes(data / "mtime_b.bin", mt_payload)
    try:
        st = os.stat(paths["mtime_b"])
        os.utime(paths["mtime_b"], (st.st_atime, st.st_mtime - 86400.0))
    except OSError:
        pass

    # 19-20: unique files (must stay singletons).
    paths["unique_a"] = write_bytes(data / "unique_a.bin", _pattern(101, SMALL))
    paths["unique_b"] = write_bytes(data / "unique_b.bin", _pattern(202, SMALL))

    # 21-22: long-path boundary (deep nesting, still < Windows MAX_PATH).
    deep = data
    for i in range(12):
        deep = deep / f"nest_{i:02d}_abcdefghij"
    paths["deep_a"] = write_bytes(deep / "deep_a.bin", _pattern(5, 512))
    paths["deep_b"] = write_bytes(deep / "deep_b.bin", _pattern(5, 512))

    # 23-24: hardlink pair (same inode) + byte-identical separate file.
    hl_payload = _pattern(77, SMALL)
    paths["hardlink_src"] = write_bytes(data / "hl_src.bin", hl_payload)
    paths["hardlink_twin"] = write_bytes(data / "hl_twin.bin", hl_payload)
    paths["hardlink_link"] = str(data / "hl_link.bin")
    try:
        if os.path.exists(paths["hardlink_link"]):
            os.remove(paths["hardlink_link"])
        os.link(paths["hardlink_src"], paths["hardlink_link"])
        paths["hardlink_supported"] = True
    except OSError:
        paths["hardlink_supported"] = False

    # 25: symlink to a duplicate (entry only; scans must not count it twice).
    paths["symlink_supported"] = False
    try:
        link = data / "link_to_dup_a.bin"
        if os.path.islink(str(link)) or os.path.exists(str(link)):
            os.remove(str(link))
        os.symlink(paths["dup_a"], str(link))
        paths["symlink_to_dup"] = str(link)
        paths["symlink_supported"] = True
    except OSError:
        pass

    # 26-30: second size grade markers + mixed duplicates.
    paths["grade_small_marker"] = write_bytes(data / "grade_small.bin", _pattern(3, SMALL))
    if large or os.environ.get("PYDUP_QUALITY_LARGE", "") == "1":
        big = _pattern(17, LARGE)
        paths["large_a"] = write_bytes(data / "large_a.bin", big)
        paths["large_b"] = write_bytes(data / "large_b.bin", big)
        paths["large_grade"] = True
    else:
        paths["large_grade"] = False

    return paths
