# UI Rebuild — 01 Design Contract (KTrain → PyDuplicateFinder, 경로 B)

목적은 시각적·상호작용적 동일 계열 경험이다. 철도 예매 전용 구조·용어는 이식하지 않는다.

## 셸·내비게이션

| KTrain (참조) | PyDuplicateFinder (본 구현) | 상태 |
|---|---|---|
| `MSFluentWindow` + `addSubInterface` | 경로 A 셸 `src/ui/shell/fluent_window.py` (`python main.py --fluent`), 레거지 셸은 기본값 유지, core 부팅(`_init_core`) 공유·이중 상속 없음 | 셸 구현済 (기본값은 레거지) |
| 상단 2 + 하단 2 (설정·업데이트) | 상단 4 (스캔/결과/도구/분석) + 하단 1 (설정), 페이지 키 `scan/results/tools/insights/settings` 유지 | 구현済 (`Sidebar.NAV_ITEMS/BOTTOM_ITEMS`) |
| 최초 화면 = 예매 | 최초 화면 = 스캔 (기존 동작 유지) | 유지 |
| 예매 중 탭 전환 가드 + 종료 확인 | 스캔 실행 중 오조작 가드 정책 `shell/navigation.py::can_switch_page` (기본: 스캔 중 결과 외 이동 시 확인 — 배선은 후속) | 정책만 고정, 미배선 |
| 창 1100×800 / 최소 640×560 + clamp | 동일 수치 (`design_system/tokens.py`), clamp 헬퍼 `shell/view_state.py::preferred_window_size` | 구현 |
| `preferred_window_size` 가용영역 clamp | 동일 수식 이식 (40px 마진, 최소값 하한) | 구현 |

## 카드·입력·액션

| KTrain (참조) | PyDuplicateFinder (본 구현) |
|---|---|
| `HeaderCardWidget` (제목 + hint + body) | `create_section` / `create_card` + `create_section_header` (제목 + hint) |
| 페이지 제목 + 요약 행 | `create_page_header` (제목 + 액션 + 메타) |
| `PrimaryPushButton` 시작 / `PushButton` 중단 | `btn_primary` 시작 / 기본 중단 (`btn_start_scan`/`btn_stop_scan`), 위험 삭제는 `btn_danger` 로 긍정 액션과 분리 |
| `LineEdit` + clear 버튼, `ComboBox(userData)` | `QLineEdit(clearButton)` 필터, `QComboBox` + `findData` 복원 (retranslate 호환) |
| `ExpandSettingCard` 고급 분리 | 스캔 필터 접힘 패널 (`btn_filter_toggle` + `filter_container`) — 카드 폭 초과 금지 |
| `IndeterminateProgressRing` + 단계 메시지 | `lbl_scan_stage` 단계 배지 + 하단 `QProgressBar` (회전형 인디케이터는 후속) |
| `QSplitter` 가로/세로 전환 (폭 부족 시) | 결과 `splitter` 3:2 + `update_splitter_orientation` 정책 `shell/view_state.py` (배선 후속) |

## 알림·확인·테마

| KTrain (참조) | PyDuplicateFinder (본 구현) |
|---|---|
| `InfoBar.success/warning` + `InfoBarPosition.TOP` | `InfoBar` 위젯 (sticky) + `ToastManager` (transient), 중복 표시 방지 `components/status_feedback.py` |
| `MessageBox` 삭제/종료 확인 | `components/operation_confirm.py`: 확인→preflight→queue→결과 순서 + visible/checked 수량 명시 (배선 후속) |
| `Theme.AUTO` + `setTheme` + `darkdetect` 폴링 | `system_theme` + `SystemThemeWatcher` + `theme/fluent_theme.py` 단일 상태 관리자 |
| 네이티브 위젯 다크 보정 | `theme/native_controls.py` — 트리/표만 최소 보정, 광역 QSS 중복 적용 금지 |
| 강조 `#E4002B` | 기본 강조는 WinUI accent (`fluent.py`) 유지, `#E4002B`는 위험/브랜드 비교 기준으로만 사용 — 삭제 버튼과 긍정 액션을 동일색으로 칠하지 않는다 |

## 여백·타이포 규칙

- 페이지 마진 16, 카드 패딩 12, 행 간격 8, 섹션 간격 12 (8pt 그리드, `tokens.py`)
- 폰트 10pt 기본, 타이틀 계층은 `results_title > card_title > section_header > filter_label`
- 테이블 고정열은 `fit_column_to_header` 로 번역·고배율 잘림 방지
- 반응형: 조건 400 + 결과 360 + 핸들 8 + 마진 = 가로 배치 필요폭, 미달 시 세로 전환·스크롤 제공 (잘라내지 않음)

## 금지 사항

- `MSFluentWindow` + `QMainWindow` 이중 상속 금지 (단일 Qt 기반 + mixin/조합만)
- 새 셸 경로에서 레거시 `init_ui` 의 `setCentralWidget/Sidebar/page_stack/create_toolbar` 재호출 금지
- `window.btn_*/chk_*` 필드명 삭제 금지 (어댑터·컨트롤러 바인딩 완비 전)
- 광역 `ModernTheme` QSS와 Fluent fragment 중복 적용 금지 (fragment는 base 이후 1회 append)
- 기존 `QSettings("MySoft", "PyDuplicateFinderPro")` 조직/앱 ID 및 키 변경 금지
