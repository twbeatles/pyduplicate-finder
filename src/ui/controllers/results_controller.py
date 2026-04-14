from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Iterable, Optional, Sequence

from src.core.scan_types import (
    COLLECTION_ROLE_NONE,
    SelectionCandidate,
    SelectionDecision,
    SelectionPolicy,
)
from src.core.selection_rules import decide_keep_delete_for_group, decide_selection_for_candidates


@dataclass(frozen=True)
class ResultEntry:
    path: str
    mtime: float = 0.0
    extension: str = ""
    collection_role: str = COLLECTION_ROLE_NONE
    explicit_keep: bool = False
    explicit_delete: bool = False
    safelisted: bool = False
    readonly: bool = False


class ResultsController:
    """Pure selection helpers for result groups."""

    @staticmethod
    def _smart_score(entry: ResultEntry) -> float:
        path = str(entry.path or "")
        lower_path = path.lower()
        score = 0.0

        # Prefer deleting temp/cache-ish candidates.
        if any(
            x in lower_path
            for x in ("/temp/", "\\temp\\", "\\appdata\\local\\temp\\", "/cache/", "\\cache\\", ".tmp")
        ):
            score += 1000.0

        # Typical "copy" naming patterns.
        if ("copy" in lower_path) or (" - copy" in lower_path) or ("(1)" in lower_path):
            score += 500.0

        score += len(path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]) * 0.1
        score += float(entry.mtime or 0.0) * 0.0000001
        return score

    @staticmethod
    def _to_candidate(entry: ResultEntry) -> SelectionCandidate:
        ext = str(entry.extension or os.path.splitext(str(entry.path or ""))[1].lower().lstrip("."))
        return SelectionCandidate(
            path=str(entry.path or ""),
            mtime=float(entry.mtime or 0.0),
            extension=ext,
            collection_role=str(entry.collection_role or COLLECTION_ROLE_NONE),
            explicit_keep=bool(entry.explicit_keep),
            explicit_delete=bool(entry.explicit_delete),
            safelisted=bool(entry.safelisted),
            readonly=bool(entry.readonly),
        )

    def pick_keep_path(self, entries: Sequence[ResultEntry], strategy: str = "smart") -> str | None:
        valid = [e for e in (entries or []) if e.path]
        if not valid:
            return None

        if strategy == "oldest":
            return min(valid, key=lambda e: float(e.mtime or 0.0)).path
        if strategy == "newest":
            return max(valid, key=lambda e: float(e.mtime or 0.0)).path
        # default: smart
        return min(valid, key=self._smart_score).path

    def build_keep_delete(
        self,
        entries: Sequence[ResultEntry],
        strategy: str = "smart",
        *,
        rules=None,
        policy: Optional[SelectionPolicy] = None,
    ) -> tuple[set[str], set[str]]:
        decision = self.build_selection_decision(entries, strategy=strategy, rules=rules, policy=policy)
        return decision.keep_set, decision.delete_set

    def build_selection_decision(
        self,
        entries: Sequence[ResultEntry],
        strategy: str = "smart",
        *,
        rules=None,
        policy: Optional[SelectionPolicy] = None,
    ) -> SelectionDecision:
        selection_policy = policy or SelectionPolicy(mode=str(strategy or "smart"))
        candidates = [self._to_candidate(entry) for entry in (entries or []) if entry.path]
        if rules or any(c.explicit_keep or c.explicit_delete or c.safelisted or c.collection_role for c in candidates):
            return decide_selection_for_candidates(candidates, rules or [], policy=selection_policy)

        keep = self.pick_keep_path(entries, strategy=strategy)
        keep_set: set[str] = set()
        delete_set: set[str] = set()
        reasons: dict[str, str] = {}
        for e in entries or []:
            if not e.path:
                continue
            if keep and e.path == keep:
                keep_set.add(e.path)
                reasons[e.path] = f"policy:{strategy}"
            else:
                delete_set.add(e.path)
                reasons[e.path] = f"delete_after_policy:{strategy}"
        return SelectionDecision(keep_set=keep_set, delete_set=delete_set, reasons=reasons)

    def build_keep_delete_by_rules(self, paths: Iterable[str], rules) -> tuple[set[str], set[str]]:
        keep_set, delete_set = decide_keep_delete_for_group(list(paths or []), rules or [])
        return set(keep_set or []), set(delete_set or [])
