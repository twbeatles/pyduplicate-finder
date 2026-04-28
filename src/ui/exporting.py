from __future__ import annotations

import csv
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from src.core.result_groups import classify_result_group

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GroupInfo:
    group_key_json: str
    group_type: str  # duplicate|name_only|similar|unknown
    group_kind: str  # file|folder|similar
    has_byte_compare: bool
    label: str
    size_from_key: Optional[int]
    bytes_reclaim_est: int
    baseline_delta: str


def _read_fs_meta(path: str) -> tuple[str, str]:
    try:
        if os.path.exists(path) and (not os.path.isdir(path)):
            return (str(os.path.getsize(path)), str(os.path.getmtime(path)))
    except Exception:
        logger.debug("Failed to read file metadata for export path: %s", path, exc_info=True)
    return ("", "")


def _parse_group_key(key) -> GroupInfo:
    info = classify_result_group(key)
    return GroupInfo(
        group_key_json=info.group_key_json,
        group_type=info.group_type,
        group_kind=info.group_kind,
        has_byte_compare=info.has_byte_compare,
        label=info.label,
        size_from_key=info.size_from_key,
        bytes_reclaim_est=info.bytes_reclaim_est,
        baseline_delta="",
    )


def export_scan_results_csv(
    *,
    scan_results: Dict,
    out_path: str,
    selected_paths: Optional[Iterable[str]] = None,
    file_meta: Optional[Dict[str, tuple[int, float]]] = None,
    baseline_delta_map: Optional[Dict[str, str]] = None,
    selection_reason_map: Optional[Dict[str, str]] = None,
    exemption_status_map: Optional[Dict[str, str]] = None,
    review_state_map: Optional[Dict[str, str]] = None,
    collection_role_map: Optional[Dict[str, str]] = None,
) -> Tuple[int, int]:
    """
    Export scan results to CSV robustly across group key shapes.

    Returns: (groups_written, rows_written)
    """
    selected_set = set(selected_paths or [])
    meta_map = dict(file_meta or {})
    delta_map = dict(baseline_delta_map or {})
    selection_map = dict(selection_reason_map or {})
    exemption_map = dict(exemption_status_map or {})
    review_map = dict(review_state_map or {})
    collection_map = dict(collection_role_map or {})
    allowed_delta = {"new", "changed", "revalidated"}

    groups = 0
    rows = 0

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "group_type",
                "group_kind",
                "group_label",
                "group_key_json",
                "byte_compare",
                "bytes_reclaim_est",
                "baseline_delta",
                "selection_reason",
                "exemption_status",
                "review_state",
                "collection_role",
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
                baseline_delta = ""
                if p:
                    try:
                        ext = os.path.splitext(p)[1]
                    except Exception:
                        ext = ""
                    try:
                        baseline_delta = str(delta_map.get(p) or "")
                    except Exception:
                        baseline_delta = ""
                    if baseline_delta not in allowed_delta:
                        baseline_delta = ""
                    meta = meta_map.get(p)
                    if meta and len(meta) >= 2:
                        try:
                            size = str(int(meta[0] or 0))
                            mtime = str(float(meta[1] or 0.0))
                        except Exception:
                            size = ""
                            mtime = ""
                    if not size:
                        size, mtime = _read_fs_meta(p)

                w.writerow(
                    [
                        gi.group_type,
                        gi.group_kind,
                        gi.label,
                        gi.group_key_json,
                        "1" if gi.has_byte_compare else "0",
                        str(int(gi.bytes_reclaim_est or 0)),
                        baseline_delta,
                        str(selection_map.get(p) or ""),
                        str(exemption_map.get(p) or ""),
                        str(review_map.get(p) or ""),
                        str(collection_map.get(p) or ""),
                        p or "",
                        "1" if (p in selected_set) else "0",
                        size,
                        mtime,
                        ext,
                    ]
                )
                rows += 1

    return groups, rows
