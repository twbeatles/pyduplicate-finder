"""Fluent 셸 내비게이션 계약 (경로 B).

KTrain ``MainWindow.addSubInterface`` 구조와 같은 정보구조를 고정한다:
상단 페이지(스캔/결과/도구/분석) + 하단 고정(설정), 최초 화면 스캔,
기존 페이지 키·단축키 유지. 실제 위젯 배선은 레거시 셸이 담당하고,
본 모듈은 순서·단축키·전환 가드라는 계약만 제공한다.
"""

from __future__ import annotations

from src.ui.controllers.navigation_controller import NavigationController

#: 상단 내비게이션 순서 (Sidebar.NAV_ITEMS 와 동일해야 한다).
PAGE_ORDER: tuple[str, ...] = ("scan", "results", "tools", "insights")

#: 하단 고정 항목 (KTrain의 BOTTOM position相当).
BOTTOM_PAGES: tuple[str, ...] = ("settings",)

#: 전체 페이지 키 (기존 5개 화면 식별자 유지).
ALL_PAGES: tuple[str, ...] = PAGE_ORDER + BOTTOM_PAGES

#: 최초 화면 (기존 동작: 스캔).
DEFAULT_PAGE = "scan"

#: 기존 툴바 단축키 매핑 (기능 보존 — 키 매핑 누락 금지).
#: 값은 (QKeySequence 문자열, 대상 동작명) 이다.
SHORTCUTS: dict[str, tuple[str, str]] = {
    "action_start_scan": ("Ctrl+Return", "start_scan"),
    "action_stop_scan": ("Escape", "stop_scan"),
    "action_delete_selected": ("Delete", "delete_selected_files"),
    "action_smart_select": ("Ctrl+Shift+A", "select_duplicates_smart"),
    "action_export_csv": ("Ctrl+E", "export_results"),
    "action_save_results": ("Ctrl+S", "save_scan_results"),
    "action_load_results": ("Ctrl+O", "load_scan_results"),
}

#: 스택 인덱스 — NavigationController 와 단일 소스로 일치시킨다.
PAGE_INDICES: dict[str, int] = dict(NavigationController.PAGE_INDICES)


def is_known_page(name: str) -> bool:
    return name in ALL_PAGES


def can_switch_page(current: str, target: str, *, scan_running: bool) -> bool:
    """페이지 전환 허용 여부 (KTrain 예매 중 가드와 같은 위치의 정책).

    스캔 실행 중에는 확인 없이 이동하지 않는다(``False`` = 호출자가
    확인 대화상자를 먼저 표시). 그 외에는 항상 허용한다.
    동일 페이지로의 이동은 항상 허용한다.
    """
    if target == current:
        return True
    if not is_known_page(target):
        return False
    if scan_running:
        return False
    return True


__all__ = [
    "ALL_PAGES",
    "BOTTOM_PAGES",
    "DEFAULT_PAGE",
    "PAGE_INDICES",
    "PAGE_ORDER",
    "SHORTCUTS",
    "can_switch_page",
    "is_known_page",
]
