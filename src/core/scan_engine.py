from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ScanConfig:
    folders: List[str]
    extensions: List[str] = field(default_factory=list)
    min_size_kb: int = 0
    same_name: bool = False
    name_only: bool = False
    byte_compare: bool = False
    protect_system: bool = True
    skip_hidden: bool = False
    follow_symlinks: bool = False
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    use_similar_image: bool = False
    use_mixed_mode: bool = False
    detect_duplicate_folders: bool = False
    incremental_rescan: bool = False
    baseline_session_id: Optional[int] = None
    similarity_threshold: float = 0.9


def build_scan_worker_kwargs(
    cfg: ScanConfig,
    *,
    session_id: Optional[int] = None,
    use_cached_files: bool = False,
) -> Dict[str, Any]:
    return {
        "check_name": bool(cfg.same_name),
        "min_size_kb": max(0, int(cfg.min_size_kb or 0)),
        "extensions": list(cfg.extensions or []) or None,
        "protect_system": bool(cfg.protect_system),
        "byte_compare": bool(cfg.byte_compare),
        "include_patterns": list(cfg.include_patterns or []),
        "exclude_patterns": list(cfg.exclude_patterns or []),
        "skip_hidden": bool(cfg.skip_hidden),
        "follow_symlinks": bool(cfg.follow_symlinks),
        "name_only": bool(cfg.name_only),
        "use_similar_image": bool(cfg.use_similar_image),
        "use_mixed_mode": bool(cfg.use_mixed_mode),
        "detect_duplicate_folders": bool(cfg.detect_duplicate_folders),
        "incremental_rescan": bool(cfg.incremental_rescan),
        "base_session_id": int(cfg.baseline_session_id) if cfg.baseline_session_id else None,
        "similarity_threshold": float(cfg.similarity_threshold or 0.9),
        "session_id": int(session_id) if session_id else None,
        "use_cached_files": bool(use_cached_files),
    }

