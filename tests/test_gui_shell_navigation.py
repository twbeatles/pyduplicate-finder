"""신규 셸·안전 계약 테스트 (경로 B, Phase 1).

- 페이지 키·순서·하단 고정·단축키 (KTrain 정보구조 parity)
- 창 크기 clamp + 반응형 스플리터 방향
- 레거시 위젯 참조 계약 (필드명 삭제 방지)
- 위험 동작 요약 문구 (visible vs checked 불일치 명시)
- 상태 피드백 중복 방지
"""

from __future__ import annotations

from types import SimpleNamespace

from src.ui.adapters.legacy_widget_refs import REQUIRED_WIDGETS, missing_widgets
from src.ui.components.operation_confirm import summarize_destructive_target
from src.ui.components.result_tree_adapter import ResultTreeAdapter
from src.ui.components.status_feedback import StatusFeedback
from src.ui.controllers.navigation_controller import NavigationController
from src.ui.shell.navigation import (
    ALL_PAGES,
    BOTTOM_PAGES,
    DEFAULT_PAGE,
    PAGE_INDICES,
    PAGE_ORDER,
    SHORTCUTS,
    can_switch_page,
    is_known_page,
)
from src.ui.shell.view_state import (
    horizontal_split_sizes,
    needed_horizontal_width,
    orientation_for_width,
    preferred_window_size,
    vertical_split_sizes,
)


def test_page_keys_match_sidebar_and_controller():
    assert PAGE_ORDER == ("scan", "results", "tools", "insights")
    assert BOTTOM_PAGES == ("settings",)
    assert ALL_PAGES == ("scan", "results", "tools", "insights", "settings")
    assert DEFAULT_PAGE == "scan"
    assert PAGE_INDICES == NavigationController.PAGE_INDICES
    assert set(ALL_PAGES) == set(REQUIRED_WIDGETS)


def test_shortcuts_cover_legacy_toolbar_actions():
    # create_toolbar 가 등록하는 모든 단축키 동작이 계약에 존재해야 한다.
    expected_actions = {
        "action_start_scan",
        "action_stop_scan",
        "action_delete_selected",
        "action_smart_select",
        "action_export_csv",
        "action_save_results",
        "action_load_results",
    }
    assert expected_actions <= set(SHORTCUTS)
    sequences = [seq for seq, _action in SHORTCUTS.values()]
    assert len(set(sequences)) == len(sequences)


def test_can_switch_page_guard():
    assert can_switch_page("scan", "scan", scan_running=True)
    assert can_switch_page("scan", "results", scan_running=False)
    assert not can_switch_page("scan", "results", scan_running=True)
    assert not can_switch_page("scan", "unknown", scan_running=False)
    for page in ALL_PAGES:
        assert is_known_page(page)
    assert not is_known_page("booking")


def test_preferred_window_size_clamps_to_available_area():
    assert preferred_window_size(1920, 1080) == (1100, 800)
    assert preferred_window_size(800, 600) == (760, 560)
    assert preferred_window_size(500, 400) == (640, 560)
    assert preferred_window_size(1100 + 40, 800 + 40) == (1100, 800)


def test_splitter_orientation_policy():
    needed = needed_horizontal_width()
    assert needed == 400 + 360 + 8 + 32
    assert orientation_for_width(needed, needed) == "horizontal"
    assert orientation_for_width(needed - 1, needed) == "vertical"
    assert orientation_for_width(640, needed) == "vertical"
    assert horizontal_split_sizes(1100) == [400, 700]
    top, bottom = vertical_split_sizes(800)
    assert top + bottom == 800


def test_missing_widgets_detects_contract_break():
    assert missing_widgets(SimpleNamespace(), "scan")
    assert missing_widgets(SimpleNamespace(), "no-such-page") == []
    host = SimpleNamespace(**{name: object() for name in REQUIRED_WIDGETS["results"]})
    assert missing_widgets(host, "results") == []


def test_destructive_summary_states_visible_vs_checked_mismatch():
    same = summarize_destructive_target(checked_count=3, visible_count=3)
    assert "3개" in same
    assert "주의" not in same
    mismatch = summarize_destructive_target(
        checked_count=10, visible_count=4, group_count=2, recoverable="격리함에서 복원 가능"
    )
    assert "10개" in mismatch and "4개" in mismatch
    assert "필터" in mismatch
    assert "복원 가능" in mismatch


def test_status_feedback_dedups_repeated_messages():
    host = SimpleNamespace(status_label=None, scan_notice_bar=None, toast_manager=None)
    fb = StatusFeedback(host)
    assert fb.show_status("ready") is False  # 위젯 없음 → no-op
    assert fb.show_notice("info", "t", "m") is False
    assert fb.show_notice("info", "t", "m") is False  # 동일 내용 반복도 False


def test_result_tree_adapter_contract():
    assert ResultTreeAdapter(object()).assert_contract() == [
        "files_checked",
        "files_checked_delta",
        "set_theme_mode",
    ]
    tree = SimpleNamespace(
        files_checked=object(),
        files_checked_delta=object(),
        set_theme_mode=lambda mode: None,
        _checked_paths={"a", "b"},
    )
    adapter = ResultTreeAdapter(tree)
    assert adapter.assert_contract() == []
    assert adapter.checked_paths() == {"a", "b"}
    assert adapter.group_count() == 0
