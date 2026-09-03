from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.scan_types import (
    COMPARE_MODE_NONE,
    SELECTION_POLICY_SMART,
)


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
    strict_mode: bool = False
    strict_max_errors: int = 0
    selection_policy: str = SELECTION_POLICY_SMART
    compare_mode: str = COMPARE_MODE_NONE
    folder_roles: Dict[str, str] = field(default_factory=dict)
    use_similar_document: bool = False
    document_similarity_threshold: float = 0.9
    watch_mode: bool = False
    apply_exemptions: bool = True
    post_cleanup_empty_dirs: bool = False
    scan_backend: str = "auto"


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
        "strict_mode": bool(cfg.strict_mode),
        "strict_max_errors": max(0, int(cfg.strict_max_errors or 0)),
        "selection_policy": str(cfg.selection_policy or SELECTION_POLICY_SMART),
        "compare_mode": str(cfg.compare_mode or COMPARE_MODE_NONE),
        "folder_roles": dict(cfg.folder_roles or {}),
        "use_similar_document": bool(cfg.use_similar_document),
        "document_similarity_threshold": float(cfg.document_similarity_threshold or 0.9),
        "watch_mode": bool(cfg.watch_mode),
        "apply_exemptions": bool(cfg.apply_exemptions),
        "post_cleanup_empty_dirs": bool(cfg.post_cleanup_empty_dirs),
        "scan_backend": str(getattr(cfg, "scan_backend", "auto") or "auto"),
        "session_id": int(session_id) if session_id else None,
        "use_cached_files": bool(use_cached_files),
    }


def validate_similar_image_dependency(cfg: ScanConfig) -> Optional[str]:
    requested = bool(cfg.use_similar_image) or bool(cfg.use_mixed_mode)
    if not requested:
        return None
    try:
        from src.core.scanner import IMAGE_HASH_AVAILABLE
    except Exception:
        return "err_similar_image_dependency"
    if not bool(IMAGE_HASH_AVAILABLE):
        return "err_similar_image_dependency"
    return None


def validate_similar_document_dependency(cfg: ScanConfig) -> Optional[str]:
    requested = bool(getattr(cfg, "use_similar_document", False))
    if not requested:
        return None
    try:
        from src.core.scanner import DOCUMENT_HASH_AVAILABLE
    except Exception:
        return "err_similar_document_dependency"
    if not bool(DOCUMENT_HASH_AVAILABLE):
        return "err_similar_document_dependency"
    return None

