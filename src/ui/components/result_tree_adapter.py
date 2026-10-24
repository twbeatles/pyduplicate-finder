"""기존 결과 트리 인터페이스 어댑터 (경로 B).

외형 개선을 이유로 ``QTableWidgetItem`` 전체 재생성 방식으로 교체하지 않기
위한 계약 고정이다: 기존 ``ResultsTreeWidget`` 의 선택·그룹·증분 업데이트
계약을 그대로 유지하고, 본 어댑터는 위임 + 계약 점검만 수행한다.
"""

from __future__ import annotations

from typing import Any


class ResultTreeAdapter:
    """``ResultsTreeWidget`` 위의 얇은 읽기 어댑터 (소유권·동작 변경 없음)."""

    def __init__(self, tree: Any) -> None:
        self._tree = tree

    @property
    def tree(self) -> Any:
        return self._tree

    def assert_contract(self) -> list[str]:
        """필수 시그널·메서드 중 빠진 이름 목록 (비어 있으면 계약 충족)."""
        missing: list[str] = []
        for name in ("files_checked", "files_checked_delta", "set_theme_mode"):
            try:
                if not hasattr(self._tree, name):
                    missing.append(name)
            except Exception:
                missing.append(name)
        return missing

    def checked_paths(self) -> set[str]:
        try:
            getter = getattr(self._tree, "get_checked_files", None)
            if callable(getter):
                res = getter()
                if isinstance(res, (list, set, tuple)):
                    return set(res)
        except Exception:
            pass
        try:
            return set(getattr(self._tree, "_checked_paths", set()) or set())
        except Exception:
            return set()

    def group_count(self) -> int:
        try:
            return int(self._tree.topLevelItemCount())
        except Exception:
            return 0


__all__ = ["ResultTreeAdapter"]
