"""Fluent 셸 뷰 상태 (경로 B, Qt 비의존 순수 함수).

KTrain ``preferred_window_size`` 의 가용영역 clamp 수식과
``update_splitter_orientation`` 의 가로/세로 전환 정책을 독립 구현한다.
수치는 ``src.ui.design_system.tokens`` 를 단일 소스로 사용한다.
"""

from __future__ import annotations

from src.ui.design_system.tokens import (
    CONDITION_CARD_MIN_WIDTH,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    RESULT_CARD_MIN_WIDTH,
    SPLITTER_HANDLE,
)

SCREEN_MARGIN = 40


def preferred_window_size(
    avail_width: int,
    avail_height: int,
    *,
    default_width: int = DEFAULT_WINDOW_WIDTH,
    default_height: int = DEFAULT_WINDOW_HEIGHT,
    min_width: int = MIN_WINDOW_WIDTH,
    min_height: int = MIN_WINDOW_HEIGHT,
    margin: int = SCREEN_MARGIN,
) -> tuple[int, int]:
    """화면 가용 영역을 넘지 않는 기본 창 크기 (KTrain과 동일 수식)."""
    width = min(default_width, max(min_width, avail_width - margin))
    height = min(default_height, max(min_height, avail_height - margin))
    return width, height


def needed_horizontal_width(
    *,
    condition_min: int = CONDITION_CARD_MIN_WIDTH,
    detail_min: int = RESULT_CARD_MIN_WIDTH,
    handle: int = SPLITTER_HANDLE,
    horizontal_margin: int = 32,
) -> int:
    """두 카드를 가로로 나란히 두는 데 필요한 최소 폭."""
    return condition_min + detail_min + handle + horizontal_margin


def orientation_for_width(page_width: int, needed_width: int) -> str:
    """``page_width`` 에 맞는 스플리터 방향. ``"horizontal"`` 또는 ``"vertical"``."""
    return "horizontal" if page_width >= needed_width else "vertical"


def horizontal_split_sizes(page_width: int, left: int = 400) -> list[int]:
    """가로 배치 초기 분할 (조건 400 + 나머지, KTrain과 동일)."""
    return [left, max(360, page_width - left)]


def vertical_split_sizes(page_height: int, ratio: float = 0.55) -> list[int]:
    """세로 배치 초기 분할 (위 55% + 아래 나머지)."""
    top = max(1, int(page_height * ratio))
    return [top, max(1, page_height - top)]


__all__ = [
    "SCREEN_MARGIN",
    "horizontal_split_sizes",
    "needed_horizontal_width",
    "orientation_for_width",
    "preferred_window_size",
    "vertical_split_sizes",
]
