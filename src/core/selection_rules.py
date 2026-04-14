import fnmatch
import os
import stat
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from src.core.scan_types import (
    COLLECTION_ROLE_PRIMARY,
    EXEMPTION_ACTION_IGNORE,
    EXEMPTION_ACTION_SAFELIST,
    EXEMPTION_KIND_CONTENT_HASH,
    EXEMPTION_KIND_EXACT_PATH,
    EXEMPTION_KIND_PATH_GLOB,
    SELECTION_POLICY_EXTENSION_PRIORITY,
    SELECTION_POLICY_NEWEST,
    SELECTION_POLICY_OLDEST,
    SELECTION_POLICY_PATH_SHORTEST,
    SELECTION_POLICY_PRIMARY_KEEP,
    SelectionCandidate,
    SelectionDecision,
    SelectionPolicy,
    ExemptionRule,
)


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


def parse_exemption_rules(rules_json: Iterable[Dict]) -> List[ExemptionRule]:
    out: List[ExemptionRule] = []
    for r in rules_json or []:
        try:
            kind = str(r.get("kind") or "").strip().lower()
            value = str(r.get("value") or "").strip()
            action = str(r.get("action") or "").strip().lower()
            note = str(r.get("note") or "").strip()
            if kind not in (EXEMPTION_KIND_EXACT_PATH, EXEMPTION_KIND_PATH_GLOB, EXEMPTION_KIND_CONTENT_HASH):
                continue
            if action not in (EXEMPTION_ACTION_SAFELIST, EXEMPTION_ACTION_IGNORE):
                continue
            if not value:
                continue
            normalized_value = normalize_path(value) if kind == EXEMPTION_KIND_EXACT_PATH else value
            out.append(ExemptionRule(kind=kind, value=normalized_value, action=action, note=note))
        except Exception:
            continue
    return out


def match_exemption_rule(path: str, rules: Iterable[ExemptionRule], *, content_hash: str = "") -> Optional[ExemptionRule]:
    npath = normalize_path(path)
    base = os.path.basename(npath)
    for rule in rules or []:
        if rule.kind == EXEMPTION_KIND_EXACT_PATH:
            if npath == normalize_path(rule.value):
                return rule
        elif rule.kind == EXEMPTION_KIND_PATH_GLOB:
            pat = normalize_path(rule.value)
            if fnmatch.fnmatchcase(npath, pat) or fnmatch.fnmatchcase(base, pat):
                return rule
        elif rule.kind == EXEMPTION_KIND_CONTENT_HASH:
            if content_hash and str(content_hash).lower() == str(rule.value).lower():
                return rule
    return None


def _fallback_keep_oldest(paths: List[str]) -> Optional[str]:
    if not paths:
        return None
    best = None
    best_mtime: float | None = None
    for p in paths:
        try:
            mt = os.path.getmtime(p)
        except Exception:
            mt = 0.0
        if best is None or best_mtime is None or mt < best_mtime:
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


def _extension_rank(path: str, preferred_extensions: tuple[str, ...]) -> int:
    ext = os.path.splitext(str(path or ""))[1].lower().lstrip(".")
    if not ext:
        return len(preferred_extensions) + 1
    try:
        return preferred_extensions.index(ext)
    except ValueError:
        return len(preferred_extensions) + 1


def _is_readonly(path: str) -> bool:
    try:
        mode = os.stat(path).st_mode
        return not bool(mode & stat.S_IWRITE)
    except Exception:
        return False


def _candidate_sort_key(candidate: SelectionCandidate, policy: SelectionPolicy) -> tuple:
    path = str(candidate.path or "")
    readonly_rank = 0 if (policy.prefer_readonly and candidate.readonly) else 1
    collection_rank = 0 if candidate.collection_role == str(policy.collection_preference or "") else 1
    ext_rank = _extension_rank(path, tuple(policy.preferred_extensions or ()))
    path_length = len(normalize_path(path))
    basename_length = len(os.path.basename(path))
    oldest_first = float(candidate.mtime or 0.0)
    newest_first = -float(candidate.mtime or 0.0)

    if policy.mode == SELECTION_POLICY_OLDEST:
        return (readonly_rank, collection_rank, oldest_first, path_length, basename_length, path)
    if policy.mode == SELECTION_POLICY_NEWEST:
        return (readonly_rank, collection_rank, newest_first, path_length, basename_length, path)
    if policy.mode == SELECTION_POLICY_PATH_SHORTEST:
        return (readonly_rank, collection_rank, path_length, basename_length, oldest_first, path)
    if policy.mode == SELECTION_POLICY_EXTENSION_PRIORITY:
        return (readonly_rank, collection_rank, ext_rank, path_length, oldest_first, path)
    if policy.mode == SELECTION_POLICY_PRIMARY_KEEP:
        return (collection_rank, readonly_rank, path_length, oldest_first, path)
    # smart
    return (collection_rank, readonly_rank, ext_rank, path_length, basename_length, oldest_first, path)


def decide_selection_for_candidates(
    candidates: Iterable[SelectionCandidate],
    rules: Iterable[SelectionRule],
    *,
    policy: Optional[SelectionPolicy] = None,
) -> SelectionDecision:
    selected_policy = policy or SelectionPolicy()
    entries = [c for c in (candidates or []) if c.path]
    decision = SelectionDecision()
    if not entries:
        return decision

    path_to_candidate = {c.path: c for c in entries}

    explicit_keep: set[str] = set()
    explicit_delete: set[str] = set()
    for path, candidate in path_to_candidate.items():
        if candidate.explicit_keep:
            explicit_keep.add(path)
            decision.reasons[path] = "explicit_keep"
            continue
        if candidate.explicit_delete:
            explicit_delete.add(path)
            decision.reasons[path] = "explicit_delete"
            continue
        for rule in rules or []:
            if rule.matches(path):
                if rule.action == "keep":
                    explicit_keep.add(path)
                    decision.reasons[path] = "rule_keep"
                else:
                    explicit_delete.add(path)
                    decision.reasons[path] = "rule_delete"
                break

    if explicit_keep:
        decision.keep_set = set(explicit_keep)
        decision.delete_set = {p for p in path_to_candidate if p not in explicit_keep}
        for path in decision.delete_set:
            decision.reasons.setdefault(path, "explicit_keep_else_delete")
        return decision

    safelist_keep = {c.path for c in entries if c.safelisted}
    if safelist_keep:
        decision.keep_set = set(safelist_keep)
        decision.delete_set = {p for p in path_to_candidate if p not in safelist_keep}
        for path in decision.keep_set:
            decision.reasons.setdefault(path, "safelist_keep")
        for path in decision.delete_set:
            decision.reasons.setdefault(path, "safelist_else_delete")
        if decision.delete_set:
            return decision

    remaining = [c for c in entries if c.path not in explicit_delete]
    if not remaining:
        remaining = list(entries)

    enriched_remaining = [
        SelectionCandidate(
            path=c.path,
            mtime=float(c.mtime or 0.0),
            extension=str(c.extension or os.path.splitext(c.path)[1].lower().lstrip(".")),
            collection_role=str(c.collection_role or ""),
            explicit_keep=c.explicit_keep,
            explicit_delete=c.explicit_delete,
            safelisted=c.safelisted,
            readonly=bool(c.readonly or _is_readonly(c.path)),
        )
        for c in remaining
    ]
    keep_one = min(enriched_remaining, key=lambda item: _candidate_sort_key(item, selected_policy))
    decision.keep_set = {keep_one.path}
    decision.delete_set = {c.path for c in entries if c.path != keep_one.path}
    decision.reasons[keep_one.path] = f"policy:{selected_policy.mode}"

    if keep_one.collection_role == COLLECTION_ROLE_PRIMARY and selected_policy.collection_preference == COLLECTION_ROLE_PRIMARY:
        decision.reasons[keep_one.path] = "collection_primary_keep"
    elif keep_one.safelisted:
        decision.reasons[keep_one.path] = "safelist_keep"
    elif selected_policy.mode == SELECTION_POLICY_EXTENSION_PRIORITY:
        decision.reasons[keep_one.path] = "policy:extension_priority"
    elif selected_policy.mode == SELECTION_POLICY_PATH_SHORTEST:
        decision.reasons[keep_one.path] = "policy:path_shortest"
    elif selected_policy.mode == SELECTION_POLICY_OLDEST:
        decision.reasons[keep_one.path] = "policy:oldest"
    elif selected_policy.mode == SELECTION_POLICY_NEWEST:
        decision.reasons[keep_one.path] = "policy:newest"
    elif selected_policy.mode == SELECTION_POLICY_PRIMARY_KEEP:
        decision.reasons[keep_one.path] = "policy:primary_keep"

    for path in decision.delete_set:
        if path in explicit_delete:
            decision.reasons.setdefault(path, "explicit_delete")
        else:
            decision.reasons.setdefault(path, f"delete_after_{decision.reasons[keep_one.path]}")
    return decision

