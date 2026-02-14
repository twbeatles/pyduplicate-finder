import fnmatch
import os
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Set


def normalize_path(path: str) -> str:
    if not path:
        return ""
    p = os.path.normpath(path).replace("\\", "/")
    if os.name == "nt":
        return p.lower()
    return p


@dataclass(frozen=True)
class SelectionRule:
    pattern: str
    action: str  # "keep" | "delete"

    def matches(self, path: str) -> bool:
        if not self.pattern:
            return False
        pat = normalize_path(self.pattern)
        val = normalize_path(path)
        # Match against full normalized path and basename.
        base = os.path.basename(val)
        return fnmatch.fnmatchcase(val, pat) or fnmatch.fnmatchcase(base, pat)


def parse_rules(rules_json: List[Dict]) -> List[SelectionRule]:
    out: List[SelectionRule] = []
    for r in rules_json or []:
        try:
            pat = str(r.get("pattern") or "").strip()
            act = str(r.get("action") or "").strip().lower()
            if act not in ("keep", "delete"):
                continue
            if not pat:
                continue
            out.append(SelectionRule(pattern=pat, action=act))
        except Exception:
            continue
    return out


def _fallback_keep_oldest(paths: List[str]) -> Optional[str]:
    if not paths:
        return None
    best = None
    best_mtime = None
    for p in paths:
        try:
            mt = os.path.getmtime(p)
        except Exception:
            mt = 0.0
        if best is None or mt < best_mtime:
            best = p
            best_mtime = mt
    return best


def decide_keep_delete_for_group(paths: List[str], rules: List[SelectionRule]) -> Tuple[Set[str], Set[str]]:
    """
    Returns (keep_set, delete_set).

    Policy:
    - Apply ordered rules; first match wins per path.
    - If any explicit KEEP rules matched in the group: keep those, delete everything else.
    - Else: keep 1 (fallback: oldest among non-explicit-delete), delete the rest.
    """
    all_paths = [p for p in (paths or []) if p]
    decided_keep: Set[str] = set()
    decided_delete: Set[str] = set()

    for p in all_paths:
        for rule in rules or []:
            if rule.matches(p):
                if rule.action == "keep":
                    decided_keep.add(p)
                else:
                    decided_delete.add(p)
                break

    remaining = set(all_paths) - decided_keep - decided_delete

    if decided_keep:
        # Keep explicitly kept, delete all else.
        keep_set = set(decided_keep)
        delete_set = set(decided_delete) | remaining
        # Safety: never delete everything.
        if keep_set and not (set(all_paths) - keep_set):
            # Keep all (no deletes).
            return keep_set, set()
        return keep_set, delete_set

    # No explicit keep -> fallback to keep one.
    candidate_pool = list(set(all_paths) - decided_delete)
    if not candidate_pool:
        candidate_pool = list(all_paths)

    keep_one = _fallback_keep_oldest(candidate_pool)
    keep_set = {keep_one} if keep_one else set()
    delete_set = set(all_paths) - keep_set
    return keep_set, delete_set

