from __future__ import annotations

import ast
import json
import time
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


def _normalize_group_key(raw_key: Any) -> Tuple[Any, ...]:
    if isinstance(raw_key, tuple):
        return raw_key
    if isinstance(raw_key, list):
        return tuple(raw_key)

    text = str(raw_key or "")
    if not text:
        return ("",)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, (list, tuple)):
            return tuple(parsed)
        return (parsed,)
    except Exception:
        pass

    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple)):
            return tuple(parsed)
    except Exception:
        pass

    return (text,)


def _serialize_group_key(key: Any) -> str:
    parts = key if isinstance(key, tuple) else (tuple(key) if isinstance(key, list) else (key,))
    return str(tuple(parts))


def _normalize_paths(raw_paths: Any) -> List[str]:
    if raw_paths is None:
        return []
    if isinstance(raw_paths, str):
        return [raw_paths]
    if isinstance(raw_paths, (list, tuple, set)):
        out: List[str] = []
        for p in raw_paths:
            if p is None:
                continue
            out.append(str(p))
        return out
    return []


def _serialize_results(scan_results: Mapping[Any, Sequence[str]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for key, paths in (scan_results or {}).items():
        out[_serialize_group_key(key)] = _normalize_paths(paths)
    return out


def dump_results_v2(
    *,
    scan_results: Mapping[Any, Sequence[str]],
    folders: Iterable[str] | None = None,
    source: str = "gui",
    generated_at: float | None = None,
) -> Dict[str, Any]:
    results_map = _serialize_results(scan_results or {})
    groups = len(results_map)
    files = sum(len(v or []) for v in results_map.values())
    return {
        "version": 2,
        "meta": {
            "groups": int(groups),
            "files": int(files),
            "folders": [str(p) for p in (folders or []) if p],
            "generated_at": float(generated_at if generated_at is not None else time.time()),
            "source": str(source or "gui"),
        },
        "results": results_map,
    }


def load_results_any(payload: Any) -> Dict[Tuple[Any, ...], List[str]]:
    if not isinstance(payload, dict):
        raise ValueError("results payload must be an object")

    if isinstance(payload.get("results"), dict):
        raw_results = payload.get("results") or {}
    else:
        raw_results = payload

    out: Dict[Tuple[Any, ...], List[str]] = {}
    for raw_key, raw_paths in (raw_results or {}).items():
        key = _normalize_group_key(raw_key)
        paths = _normalize_paths(raw_paths)
        if not paths:
            out.setdefault(key, [])
            continue
        out.setdefault(key, []).extend(paths)
    return out
