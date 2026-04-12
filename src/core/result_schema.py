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


def _collect_result_paths(results_map: Mapping[str, Sequence[str]]) -> set[str]:
    out: set[str] = set()
    for paths in (results_map or {}).values():
        for path in paths or []:
            if path:
                out.add(str(path))
    return out


def _normalize_selected_paths(raw_paths: Any, *, allowed_paths: set[str] | None = None) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for path in _normalize_paths(raw_paths):
        norm_path = str(path)
        if not norm_path or norm_path in seen:
            continue
        if allowed_paths is not None and norm_path not in allowed_paths:
            continue
        seen.add(norm_path)
        out.append(norm_path)
    return out


def _normalize_delta(value: Any) -> str:
    token = str(value or "").strip()
    return token if token in {"new", "changed", "revalidated"} else ""


def _serialize_meta_file_map(
    *,
    allowed_paths: set[str],
    file_meta: Mapping[str, Sequence[Any]] | None = None,
    existence_map: Mapping[str, Any] | None = None,
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    raw_meta = dict(file_meta or {})
    raw_exists = dict(existence_map or {})
    for path in sorted(allowed_paths):
        meta = raw_meta.get(path)
        exists = bool(raw_exists.get(path)) if path in raw_exists else None
        size_value: int | None = None
        mtime_value: float | None = None
        if isinstance(meta, (list, tuple)) and len(meta) >= 2:
            try:
                size_value = int(meta[0])
            except Exception:
                size_value = None
            try:
                mtime_value = float(meta[1])
            except Exception:
                mtime_value = None
        if exists is None and meta is None:
            continue
        item: Dict[str, Any] = {}
        if size_value is not None:
            item["size"] = size_value
        if mtime_value is not None:
            item["mtime"] = mtime_value
        if exists is not None:
            item["exists"] = bool(exists)
        out[path] = item
    return out


def _normalize_meta_file_map(raw: Any) -> tuple[Dict[str, tuple[int, float]], Dict[str, bool]]:
    file_meta: Dict[str, tuple[int, float]] = {}
    existence_map: Dict[str, bool] = {}
    if not isinstance(raw, dict):
        return file_meta, existence_map
    for path, value in raw.items():
        norm_path = str(path or "")
        if not norm_path or not isinstance(value, dict):
            continue
        size = value.get("size")
        mtime = value.get("mtime")
        if size is not None and mtime is not None:
            try:
                file_meta[norm_path] = (int(size), float(mtime))
            except Exception:
                pass
        if "exists" in value:
            existence_map[norm_path] = bool(value.get("exists"))
    return file_meta, existence_map


def dump_results_v2(
    *,
    scan_results: Mapping[Any, Sequence[str]],
    folders: Iterable[str] | None = None,
    source: str = "gui",
    generated_at: float | None = None,
    selected_paths: Iterable[str] | None = None,
    file_meta: Mapping[str, Sequence[Any]] | None = None,
    baseline_delta_map: Mapping[str, str] | None = None,
    existence_map: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    results_map = _serialize_results(scan_results or {})
    result_paths = _collect_result_paths(results_map)
    groups = len(results_map)
    files = sum(len(v or []) for v in results_map.values())
    meta: Dict[str, Any] = {
        "groups": int(groups),
        "files": int(files),
        "folders": [str(p) for p in (folders or []) if p],
        "generated_at": float(generated_at if generated_at is not None else time.time()),
        "source": str(source or "gui"),
    }
    selected = _normalize_selected_paths(selected_paths, allowed_paths=result_paths)
    if selected_paths is not None:
        meta["selected_paths"] = selected
    serialized_meta_map = _serialize_meta_file_map(
        allowed_paths=result_paths,
        file_meta=file_meta,
        existence_map=existence_map,
    )
    if serialized_meta_map:
        meta["file_meta"] = serialized_meta_map
    deltas = {
        path: delta
        for path in sorted(result_paths)
        for delta in [_normalize_delta((baseline_delta_map or {}).get(path))]
        if delta
    }
    if deltas:
        meta["baseline_delta_map"] = deltas
    return {
        "version": 2,
        "meta": meta,
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


def load_results_bundle_any(payload: Any) -> Dict[str, Any]:
    results = load_results_any(payload)
    meta = payload.get("meta") if isinstance(payload, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    result_paths = set()
    for paths in results.values():
        for path in paths or []:
            if path:
                result_paths.add(str(path))
    file_meta, existence_map = _normalize_meta_file_map(meta.get("file_meta"))
    baseline_delta_map = {}
    raw_deltas = meta.get("baseline_delta_map")
    if isinstance(raw_deltas, dict):
        for path, value in raw_deltas.items():
            norm_path = str(path or "")
            if not norm_path or norm_path not in result_paths:
                continue
            delta = _normalize_delta(value)
            if delta:
                baseline_delta_map[norm_path] = delta
    selected_paths = _normalize_selected_paths(meta.get("selected_paths"), allowed_paths=result_paths)
    return {
        "results": results,
        "selected_paths": selected_paths,
        "file_meta": {path: meta_tuple for path, meta_tuple in file_meta.items() if path in result_paths},
        "existence_map": {path: exists for path, exists in existence_map.items() if path in result_paths},
        "baseline_delta_map": baseline_delta_map,
        "scan_status": str(meta.get("scan_status") or "completed"),
        "metrics": dict(meta.get("metrics") or {}),
        "warnings": list(meta.get("warnings") or []),
    }
