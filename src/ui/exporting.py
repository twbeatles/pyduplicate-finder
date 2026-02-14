from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class GroupInfo:
    group_key_json: str
    group_type: str  # duplicate|name_only|similar|unknown
    has_byte_compare: bool
    label: str
    size_from_key: Optional[int]


def _parse_group_key(key) -> GroupInfo:
    try:
        key_json = json.dumps(key, ensure_ascii=False, default=str)
    except Exception:
        key_json = json.dumps(str(key), ensure_ascii=False)

    group_type = "unknown"
    has_byte_compare = False
    label = ""
    size_from_key = None

    parts: List = []
    if isinstance(key, (tuple, list)):
        parts = list(key)
    else:
        parts = [key]

    for p in parts:
        if isinstance(p, int):
            size_from_key = p
        if isinstance(p, str) and p.startswith("byte_"):
            has_byte_compare = True

    if parts and isinstance(parts[0], str) and parts[0] == "NAME_ONLY":
        group_type = "name_only"
        if len(parts) > 1:
            label = str(parts[1])
    else:
        sim = None
        for p in parts:
            if isinstance(p, str) and p.startswith("similar_"):
                sim = p
                break
        if sim:
            group_type = "similar"
            label = sim
        else:
            group_type = "duplicate"
            # Prefer first non-int part as label (typically a hash string).
            for p in parts:
                if not isinstance(p, int):
                    label = str(p)
                    break

    if not label:
        label = "group"

    return GroupInfo(
        group_key_json=key_json,
        group_type=group_type,
        has_byte_compare=has_byte_compare,
        label=label,
        size_from_key=size_from_key,
    )


def export_scan_results_csv(
    *,
    scan_results: Dict,
    out_path: str,
    selected_paths: Optional[Iterable[str]] = None,
) -> Tuple[int, int]:
    """
    Export scan results to CSV robustly across group key shapes.

    Returns: (groups_written, rows_written)
    """
    selected_set = set(selected_paths or [])

    groups = 0
    rows = 0

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "group_type",
                "group_label",
                "group_key_json",
                "byte_compare",
                "path",
                "selected",
                "size_bytes",
                "mtime",
                "ext",
            ]
        )

        for key, paths in (scan_results or {}).items():
            gi = _parse_group_key(key)
            groups += 1
            for p in (paths or []):
                size = ""
                mtime = ""
                ext = ""
                if p:
                    try:
                        ext = os.path.splitext(p)[1]
                    except Exception:
                        ext = ""
                    try:
                        if os.path.exists(p) and (not os.path.isdir(p)):
                            size = str(os.path.getsize(p))
                            mtime = str(os.path.getmtime(p))
                    except Exception:
                        pass

                w.writerow(
                    [
                        gi.group_type,
                        gi.label,
                        gi.group_key_json,
                        "1" if gi.has_byte_compare else "0",
                        p or "",
                        "1" if (p in selected_set) else "0",
                        size,
                        mtime,
                        ext,
                    ]
                )
                rows += 1

    return groups, rows

