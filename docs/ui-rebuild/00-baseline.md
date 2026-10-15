# UI Rebuild — 00 Baseline (2026-10-15)

작업 브랜치: `feat/ktrain-fluent-ui-rebuild` (HEAD `c7bf9a5` 에서 분기, 작업 트리 정리됨 —
분기 시점 `src/core/scanner/hashing.py` 의 미커밋 변경이 사라진 것을 확인, 본 작업과 무관하므로 복원하지 않음)

## Refs

| 항목 | 값 |
|---|---|
| 대상 HEAD (pyduplicate-finder) | `c7bf9a5` (2026-10-14, `chore: ignore local AI agent dirs`), 브랜치 `main`, status clean (계획서 스냅샷과 동일) |
| 참조 HEAD (srtgo-main = ktrain) | `e649490` (2026-10-15, manifest v2.0.67), 브랜치 `master`, status clean (계획서 스냅샷과 동일) |
| 참조 경로 | `D:\twbeatles-repos\srtgo-main` (읽기 전용, 수정 금지) |

## 실행 환경

- OS: Windows, Python 3.15.0, PySide6 6.12.0 (참조 `pyproject.toml` 의 GUI 핀과 동일)
- `PySide6-Fluent-Widgets 1.11.3` 이 현재 venv에 설치되어 있음 (참조 핀과 동일)
  — 단, 제품 의존성 추가는 Gate 0 통과 전 금지 (계획서 §2). 설치 사실 ≠ 도입 결정
- `pytest 9.1.1`, `pytest-qt 4.5.0`, `darkdetect 0.8.0`, `pillow 12.3.0`, `psutil 7.2.2`
- 미설치(주의): `imagehash`, `send2trash`, `watchdog`, `pypdf` 가 `pip list` 에 보이지 않음 —
  유사 이미지/문서·watch·격리 관련 테스트 실행 시 SKIP/실패 가능, 결과에 별도 기록

## 구조 대조 (실측)

| 항목 | pyduplicate-finder (대상) | ktrain/srtgo-main (참조) |
|---|---|---|
| 앱 셸 | `QMainWindow` + `Sidebar` + `QStackedWidget` (`src/ui/main_window.py`, `main_window_parts/ui_shell/legacy.py`) | `MSFluentWindow` + `addSubInterface`, 설정 하단 고정 (`ktrain/gui/main_window.py`) |
| 창 크기 | 1100×800 / 최소 640×560 (토큰에 이미 반영) | 동일 수치 + 가용영역 clamp (`preferred_window_size`) |
| 디자인 토큰 | `src/ui/design_system/tokens.py` — 8pt 그리드, 카드 최소폭 400/360, 브랜드 `#E4002B` (참조 패턴 이식済) | 코드 내 상수 + Fluent 위젯 기본값 |
| 카드/헤더/InfoBar | 순수 PySide6 독립 구현 (`design_system/components/`) | `HeaderCardWidget`, `qfluentwidgets.InfoBar/MessageBox` |
| 테마 | `ModernTheme` 전역 QSS + `system_theme` 추종 | `Theme.AUTO` + `darkdetect` + 네이티브 보정 |
| 페이지 | `src/ui/pages/` 5종 빌더 함수 (scan 434행, results 306행, settings 406행, tools 338행, insights 143행) | `pages/booking/*` 분할 + `pages/settings/page.py` Pivot 구조 |
| 동작 결합 | `window.btn_*/chk_*` 직접 참조 + mixin 다중상속 | 페이지·워커·셸 분리 |
| 패키징 | `PyDuplicateFinder.spec` (`PySide6.QtSvg` exclude 포함 — Fluent 아이콘 사용 시 해제 검토 필요) | `packaging/ktrain-gui.spec` + `gui_bundle.py` |
| 진입점 | `main.py` (인라인 부팅) | `ktrain/gui/app.py` (의존성 검증·DPI·테마·진입점 분리) |

## 선행 작업 (재구현 금지)

- `src/ui/design_system/` (tokens/fluent/hidpi/layouts/system_theme + components 7종)
- `src/ui/theme/` (ModernTheme), `tests/test_design_system.py`, `tests/test_fluent_theme.py`
- `tests/test_navigation_controller.py`, 결과 트리/프리뷰 컨트롤러 및 성능 테스트군

## 테스트 기준선 (Phase 0/1 실행 결과, 2026-10-15)

- 명령: `$env:QT_QPA_PLATFORM="offscreen"; python -m pytest -q`
- 결과(Phase 1): **231 passed, 25 skipped** (8.4s)
- 결과(경로 A 셸 추가 후): **237 passed, 25 skipped** (26.5s) — 신규
  `test_gui_fluent_shell` 5개 포함, 실패·회귀 없음
- Fluent 스모크: `python main.py --fluent` 가 offscreen에서 오류 없이 이벤트
  루프까지 부팅됨을 확인 (헤드리스 폰트 경고만, 무해)
- 패키징(Phase 5): `python -m PyInstaller PyDuplicateFinder.spec --noconfirm`
  빌드 성공 (`dist/PyDuplicateFinderPro.exe`, 약 59MB). `QtSvg` exclude 해제·
  Fluent hidden imports 포함. 번들 실행 스모크는 아래 결과 참조.
- 번들 스모크: `dist/PyDuplicateFinderPro.exe` 가 offscreen에서 즉시 종료 없이
  실행 유지됨을 확인 (이벤트 루프 진입, 크래시 없음)
- 구조 증거: `docs/ui-rebuild/evidence/after/` 에 Fluent 5페이지 + 레거지 스캔
  캡처 6종 저장, 스캔·결과 화면 픽셀 직접 확인済 (내비게이션 레일·스플리터·
  액션바·상태 스트립 정상 배치). 한글은 헤드리스 폰트 부재로 tofu(□) 표시 —
  실Windows(Malgun Gothic) 렌더와 동일시하지 않음, 실모니터 캡처는 후속 과제
- 신규 3종 포함 실행도 동일하게 전부 통과 (60 passed):
  `test_gui_shell_navigation` · `test_gui_qt_binding` · `test_gui_settings_migration` +
  기존 `test_design_system` · `test_fluent_theme` · `test_navigation_controller`
- 25 skip 전부는 `tests/rust_parity/*` — `pydup_core` 미컴파일(환경 제약, 기존 상태)
- 헤드리스 실행은 `QT_QPA_PLATFORM=offscreen` 을 사용하되, 이를 Windows 시각 검증과 동일시하지 않는다.
  실제 Windows 창 캡처·DPI(125/150%) 검증은 Phase 2 이후 후속 과제로 남는다.
