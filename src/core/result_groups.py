from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional


GROUP_TYPE_DUPLICATE = "duplicate"
GROUP_TYPE_NAME_ONLY = "name_only"
GROUP_TYPE_FOLDER_DUP = "folder_dup"
GROUP_TYPE_SIMILAR_IMAGE = "similar_image"
GROUP_TYPE_SIMILAR_DOCUMENT = "similar_document"
GROUP_KIND_FILE = "file"
GROUP_KIND_FOLDER = "folder"
GROUP_KIND_SIMILAR = "similar"


@dataclass(frozen=True)
class ResultGroupInfo:
    group_key_json: str
    group_type: str
    group_kind: str
    label: str
    size_from_key: Optional[int]
    bytes_reclaim_est: int
    has_byte_compare: bool
    hardlink_eligible: bool
    risk_level: str


def _parts(key) -> list:
    if isinstance(key, (tuple, list)):
        return list(key)
    return [key]


def classify_result_group(key) -> ResultGroupInfo:
    try:
        key_json = json.dumps(key, ensure_ascii=False, default=str)
    except Exception:
        key_json = json.dumps(str(key), ensure_ascii=False)

    parts = _parts(key)
    label = ""
    size_from_key = None
    bytes_reclaim_est = 0
    has_byte_compare = any(isinstance(part, str) and part.startswith("byte_") for part in parts)

    for part in parts:
        if isinstance(part, int):
            size_from_key = part
            break

    group_type = GROUP_TYPE_DUPLICATE
    group_kind = GROUP_KIND_FILE

    if parts and parts[0] == "NAME_ONLY":
        group_type = GROUP_TYPE_NAME_ONLY
        label = str(parts[1]) if len(parts) > 1 else "name"
    elif parts and parts[0] == "FOLDER_DUP":
        group_type = GROUP_TYPE_FOLDER_DUP
        group_kind = GROUP_KIND_FOLDER
        label = str(parts[1]) if len(parts) > 1 else "folder"
        if len(parts) > 2 and isinstance(parts[2], int):
            bytes_reclaim_est = int(parts[2] or 0)
    else:
        for part in parts:
            if isinstance(part, str) and part.startswith("doc_similar_"):
                group_type = GROUP_TYPE_SIMILAR_DOCUMENT
                group_kind = GROUP_KIND_SIMILAR
                label = part
                break
            if isinstance(part, str) and part.startswith("similar_"):
                group_type = GROUP_TYPE_SIMILAR_IMAGE
                group_kind = GROUP_KIND_SIMILAR
                label = part
                break

        if not label:
            for part in parts:
                if not isinstance(part, int):
                    label = str(part)
                    break

    if not label:
        label = "group"

    hardlink_eligible = group_type == GROUP_TYPE_DUPLICATE
    if group_type in (GROUP_TYPE_NAME_ONLY, GROUP_TYPE_FOLDER_DUP):
        risk_level = "high"
    elif group_type in (GROUP_TYPE_SIMILAR_IMAGE, GROUP_TYPE_SIMILAR_DOCUMENT):
        risk_level = "medium"
    else:
        risk_level = "low"
    return ResultGroupInfo(
        group_key_json=key_json,
        group_type=group_type,
        group_kind=group_kind,
        label=label,
        size_from_key=size_from_key,
        bytes_reclaim_est=bytes_reclaim_est,
        has_byte_compare=has_byte_compare,
        hardlink_eligible=hardlink_eligible,
        risk_level=risk_level,
    )
