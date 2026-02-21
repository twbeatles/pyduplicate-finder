from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from src.core.selection_rules import decide_keep_delete_for_group


@dataclass(frozen=True)
class ResultEntry:
    path: str
    mtime: float = 0.0


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

    def build_keep_delete(self, entries: Sequence[ResultEntry], strategy: str = "smart") -> tuple[set[str], set[str]]:
        keep = self.pick_keep_path(entries, strategy=strategy)
        keep_set: set[str] = set()
        delete_set: set[str] = set()
        for e in entries or []:
            if not e.path:
                continue
            if keep and e.path == keep:
                keep_set.add(e.path)
            else:
                delete_set.add(e.path)
        return keep_set, delete_set

    def build_keep_delete_by_rules(self, paths: Iterable[str], rules) -> tuple[set[str], set[str]]:
        keep_set, delete_set = decide_keep_delete_for_group(list(paths or []), rules or [])
        return set(keep_set or []), set(delete_set or [])
