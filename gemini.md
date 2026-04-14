# AI Project Context: PyDuplicate Finder Pro

이 문서는 AI 에이전트가 `PyDuplicate Finder Pro`의 아키텍처와 구현 상세를 파악하기 위한 기술 문서입니다.

## 1. 프로젝트 개요
- **이름**: PyDuplicate Finder Pro
- **버전**: 1.2.0
- **목적**: PySide6 기반의 데스크톱 애플리케이션으로, 멀티스레딩과 스마트 캐싱을 활용해 중복 파일을 고속으로 탐색하고 관리합니다.
- **기술 스택**: Python 3.9+, PySide6 (Qt for Python), SQLite (WAL), concurrent.futures

## 2. 코드베이스 구조 (Codebase Structure)

### 패키지 구조
```
src/
├── core/                    [비즈니스 로직 - UI 독립]
│   ├── scanner/                 # ScanWorker façade + discovery/hash/incremental/similar-image helper 모듈
│   ├── cache_manager/           # CacheManager façade + DB/schema/session/quarantine/jobs helper 모듈
│   ├── history.py               # Undo/Redo 트랜잭션 + atexit 자동 정리 + 디스크 공간 체크
│   ├── operation_queue.py       # OperationWorker: 삭제/복구/하드링크 작업 큐
│   ├── result_schema.py         # 결과 JSON v3 스키마 및 legacy/v2/v3 호환 로더
│   ├── image_hash.py            # pHash 기반 유사 이미지 탐지 (BK-Tree + Union-Find)
│   ├── document_hash.py         # SimHash 기반 유사 문서 탐지
│   ├── scan_types.py            # selection/exemption/review/collection 타입
│   ├── file_lock_checker.py     # 파일 잠금 상태 확인
│   ├── preset_manager.py        # 스캔 프리셋 JSON 관리 (기본값 병합)
│   └── empty_folder_finder.py   # 빈 폴더 탐색 + EmptyFolderWorker (비동기)
├── ui/                      [PySide6 GUI]
│   ├── main_window.py           # 조립/호환 레이어(공개 import 경로 유지)
│   ├── main_window_parts/       # 메인 윈도우 책임별 분리 모듈(SOLID)
│   │   ├── ui_shell/                # build/translate/theme/navigation submixin
│   │   ├── scan_flow/               # folders/lifecycle/config submixin
│   │   ├── results_flow/            # rendering/selection/filtering/preview/actions/persistence
│   │   ├── settings_flow/           # persistence/session_restore/dialogs/cache_settings
│   │   ├── tools_flow/              # quarantine/operations/rules/hardlink
│   │   ├── schedule_flow.py         # 스케줄 검증/tick/자동 export/실행기록
│   │   └── typing_contract/         # host protocol 세분화 + aggregate contract
│   ├── theme/                   # 라이트/다크 테마 스타일시트 분리
│   ├── empty_folder_dialog.py   # 빈 폴더 정리 다이얼로그 (비동기)
│   ├── controllers/
│   │   ├── scan_controller.py
│   │   ├── scheduler_controller.py
│   │   ├── watch_controller.py
│   │   ├── ops_controller.py
│   │   ├── operation_flow_controller.py
│   │   ├── navigation_controller.py
│   │   ├── results_controller.py
│   │   └── preview_controller.py
│   ├── components/
│   │   ├── results_tree/        # 결과 트리 위젯 façade + populate/filter/state 분리
│   │   ├── sidebar.py           # 사이드바 네비게이션
│   │   └── toast.py             # 토스트 알림
│   └── dialogs/
│       ├── preset_dialog.py
│       ├── exclude_patterns_dialog.py
│       ├── session_compare_dialog.py
│       └── shortcut_settings_dialog.py  # 테마 상속 지원
└── utils/
    └── i18n/                    # 한국어/영어 다국어 지원 + DEBUG_I18N
```

## 3. 핵심 기술 구현 상세 (Implementation Details)

### 스캔 및 성능 최적화 (`src/core/scanner/`)
| 기술 | 설명 |
|------|------|
| **초고속 I/O** | `os.scandir` 재귀 사용으로 stat 접근 최소화 |
| **고속 해싱** | BLAKE2b 알고리즘 + ThreadPoolExecutor 병렬 처리 |
| **병렬 pHash** | 유사 이미지 스캔 시 pHash도 병렬 계산 |
| **스마트 캐시** | 경로/크기/mtime 일치 시 해시 계산 스킵 |
| **세션 재개** | 세션별 해시 진행 상태 저장으로 재시작 시 해싱 단계 재사용 |
| **이벤트 스로틀링** | 100ms 단위 진행률 업데이트로 UI 렉 방지 |
| **물리적 중복 방지** | Inode(st_ino) 검사로 심볼릭 링크 중복 제거 |
| **리소스 정리** | finally 블록에서 cache_manager.close_all() 호출 |
| **취소 안전성** | 취소 시 scan_cancelled 시그널 emit (완료 시에만 scan_finished) |
| **이름-only 스캔** | 파일 내용 해시 없이 파일명 기준으로 그룹핑 |

### 데이터 무결성 및 안전 (`history.py`)
| 기능 | 설명 |
|------|------|
| **시스템 보호** | Windows 주요 경로 스캔 제외 |
| **원자적 복구** | 백업 확인 → 부모 디렉토리 생성 → 파일 이동 |
| **자동 정리** | `atexit.register(cleanup)` 으로 종료 시 임시폴더 정리 |
| **디스크 공간 체크** | 삭제 전 `check_disk_space()` 검증 |
| **I18n** | 모든 에러 메시지 `strings.tr()` 사용 |

### DB 최적화 (`src/core/cache_manager/`)
```python
# SQLite Tuning
PRAGMA journal_mode=WAL     # 동시성 향상
PRAGMA synchronous=NORMAL   # 쓰기 성능 향상
PRAGMA cache_size=-64000    # 64MB 캐시
```
- **Thread-Local**: `threading.local()`로 스레드별 커넥션 관리
- **Connection Tracking**: `weakref.WeakSet`으로 모든 커넥션 추적
- **세션 캐시**: scan_sessions/scan_files/scan_hashes/scan_results/scan_selected로 스캔 진행 상태 저장

### 유사 이미지 탐지 (`image_hash.py`)
- **알고리즘**: Perceptual Hash (pHash)
- **고속 그룹핑**: BK-Tree + Union-Find ($O(N \log N)$)
- **유사도 계산**: 해밍 거리 기반 (0.0 ~ 1.0)
- **취소/진행률**: `check_cancel`, `progress_callback` 콜백 지원

## 4. 의존성 (Dependencies)

```
PySide6              # Qt GUI
imagehash>=4.3.0     # 유사 이미지 탐지
Pillow>=9.0.0        # 이미지 처리
send2trash>=1.8.0    # 휴지통 기능
psutil>=5.9.0        # 파일 잠금 프로세스 확인
watchdog>=4.0.0      # 실시간 폴더 감시
pypdf>=5.0.0         # PDF 텍스트 추출 기반 유사 문서 탐지
```

## 5. 유지보수 가이드
1. **core/ui 분리**: 기능 수정 시 `core`와 `ui` 의존성 분리 유지
2. **스레드 안전**: `src/core/scanner/`, `src/core/cache_manager/` 수정 시 동시성 고려
3. **다국어 확장**: 새 UI 텍스트는 `src/utils/i18n/`에 추가
4. **리소스 정리**: 스레드 종료 시 `finally` 블록에서 정리 로직 구현
5. **취소 지원**: 장시간 작업에는 반드시 `check_cancel` 콜백 구현
6. **테마 상속**: 다이얼로그는 부모 테마 설정 상속


## Update Memo (2026-02-21)

- Added controller split for performance-sensitive UI paths:
  - `src/ui/controllers/results_controller.py`
  - `src/ui/controllers/preview_controller.py`
- `ResultsTreeWidget` now supports delta selection signal:
  - `files_checked_delta(added, removed, selected_count)`
  - Existing `files_checked(list)` remains for compatibility.
- Preview path now uses async loading + small LRU cache to reduce UI stalls on rapid selection changes.
- Scanner improvements:
  - pre-compiled include/exclude matchers
  - throttled session progress DB writes (separate from UI progress throttle)
  - deduplicated session hash batch writes
  - folder-duplicate full hash path integrated with parallel hash pipeline
  - final `file_meta` trimmed to result-referenced paths
- Operation queue reduced repeated stat calls in trash/hardlink flows and unified throttled progress behavior.
- CSV export now supports optional `file_meta` passthrough to avoid redundant filesystem stats.
- Added deterministic performance regression tests and a local benchmark runner:
  - `tests/test_scanner_perf_path.py`
  - `tests/test_results_tree_perf.py`
  - `tests/test_exporting.py`
  - `tests/test_main_window_selection_perf.py`
  - `tests/benchmarks/bench_perf.py`

## Update Memo (2026-02-26)

- Removed legacy `src/core/file_ops.py` flow and unified operation execution via:
  - `src/core/operation_queue.py`
  - `src/ui/controllers/operation_flow_controller.py`
- Added `src/core/result_schema.py`:
  - canonical result JSON schema (`version=2`)
  - backward-compatible loader for legacy GUI / legacy CLI / v2
- Quarantine safety hardening:
  - rollback moved file if `insert_quarantine_item` fails (`<=0`)
  - explicit failure reason for rollback failure paths
- Preview concurrency hardening:
  - cache access guarded with `threading.RLock`
  - `preview_ready` connected with `Qt.QueuedConnection` for main-thread UI updates
- Preset schema alignment:
  - save `schema_version=2`
  - merge defaults when loading old presets
- Scheduler/cache policy updates:
  - strict `HH:MM (00:00-23:59)` validation blocks invalid schedule saves
  - new settings: `cache/session_keep_latest`, `cache/hash_cleanup_days`
  - startup cleanup respects those settings
- Incremental export enhancement:
  - `ScanWorker.latest_baseline_delta_map` added
  - CSV `baseline_delta` filled per file with `new|changed|revalidated`
- Similar-image dependency policy:
  - GUI and CLI both fail fast when `imagehash`/`Pillow` are unavailable
- i18n consistency cleanup:
  - removed hardcoded UI text from `empty_folder_finder.py`, `preset_dialog.py`

## Update Memo (2026-03-09)

- Main-window SOLID split completed while preserving compatibility:
  - Public import path remains `src.ui.main_window.DuplicateFinderApp`.
  - Behavior moved to `src/ui/main_window_parts/*` mixin packages/modules.
- Typing contract introduced for dynamic UI attributes:
  - `src/ui/main_window_parts/typing_contract/` adds `TYPE_CHECKING` attributes and host protocols.
  - Reduced `Any` dependence in controller-host interactions without relaxing diagnostics.
- Pylance/Pyright regression prevention:
  - Added `pyrightconfig.json` (Python `3.14`, scoped to `src`, `tests`, `cli.py`, `main.py`).
  - Key diagnostics pinned to `error` (`reportAttributeAccessIssue` included).
- Encoding regression prevention:
  - Added `.editorconfig` UTF-8/LF/final-newline policy.
  - Added `tests/test_source_encoding_integrity.py` checks:
    - UTF-8 decode validity
    - no replacement char (`U+FFFD`)
    - known mojibake pattern absence.

## Update Memo (2026-03-11)

- CLI lifecycle stability:
  - `cli.py` now executes `ScanWorker.run()` synchronously without creating a separate Qt event-loop instance.
  - This reduces lifecycle collision risk when users switch between CLI and GUI workflows.
- CLI option consistency:
  - `--mixed-mode` now implicitly enables similar-image pass (`use_similar_image=True`).
- Incremental scan reliability:
  - Removed deep subtree skip policy that relied only on unchanged directory mtime.
  - This lowers risk of missing new files that appear after baseline scans.
- File lock reliability:
  - Windows zero-byte lock-check path in `file_lock_checker.py` was hardened to avoid false-unlocked outcomes.
- Regression tests and baseline:
  - Added/updated tests for CLI lifecycle, mixed-mode config policy, incremental delta map behavior, and zero-byte lock checks.
  - Current full-suite baseline: `pytest -q` -> `104 passed`.

## Update Memo (2026-03-18)

- Large module packageization completed while preserving public import paths:
  - `src/core/cache_manager/`
  - `src/core/scanner/`
  - `src/utils/i18n/`
  - `src/ui/theme/`
  - `src/ui/components/results_tree/`
- Main-window submixins were packageized:
  - `src/ui/main_window_parts/{ui_shell,scan_flow,results_flow,settings_flow,tools_flow}/`
  - each package now composes focused submixins over a compatibility `legacy.py`
- Typing contracts were split by host concern:
  - `scan`, `results`, `settings`, `tools`, `ui_shell`, `schedule`, `navigation`, `operation_flow`
- Packaging/docs/test alignment:
  - `PyDuplicateFinder.spec` now collects packageized submodules with `collect_submodules(...)`
  - added `tests/test_public_api_facades.py`
  - current full-suite baseline: `pytest -q` -> `111 passed`

## Update Memo (2026-04-12)

- Scheduler weekly first-run semantics were corrected.
  - `src/core/scheduler.py:is_due(...)` now waits for the next configured weekday/time slot instead of firing immediately after the target weekday has already passed.
- Zero-byte duplicate handling is now consistent across live scan collection and cached-session reuse.
  - Empty files are eligible only when `min_size_kb == 0`.
- Cancel/failure rollback now restores the prior result bundle instead of only the duplicate groups.
  - Checked paths, `file_meta`, missing-file state, and `baseline_delta_map` are restored together.
- Result JSON `version=2` remains backward-compatible and now supports richer optional metadata.
  - `dump_results_v2(...)` can persist `meta.selected_paths`, `meta.file_meta`, and `meta.baseline_delta_map`.
  - `load_results_bundle_any(...)` restores GUI-ready state while `load_results_any(...)` keeps legacy compatibility behavior.
- Scheduled auto-export bookkeeping now reports partial export failures correctly.
  - If scan execution completed but JSON/CSV export failed, run status is finalized as `partial`.
  - Run messages may include `missing_folders:<n>` and `export_failed:<formats>`.
- CLI quiet mode semantics were tightened.
  - `--quiet` suppresses successful stdout completely, while errors and cancellation remain on `stderr`.
- Quarantine retention now iterates over the full quarantine table in batches rather than stopping at the first 5,000 rows.
- Packaging review:
  - `PyDuplicateFinder.spec` already includes the affected modules, so no hidden-import update was necessary.
- Current regression baseline:
  - `pytest -q` -> `122 passed`
  - `pyright src tests cli.py main.py` was attempted in this workspace, but local dependency resolution for `imagehash` / `send2trash` is currently missing.

## Update Memo (2026-04-14)

- Database schema version advanced to `6`.
  - Added `scan_exemptions`, `review_marks`, and `file_signatures`.
- Result persistence now targets JSON `version=3`.
  - File-level state is saved/restored: `selection_reason`, `exemption_status`, `review_state`, `collection_role`, `baseline_delta`.
- Selection policy flow was unified.
  - explicit keep/delete -> safelist -> collection role -> attribute priority -> fallback keep-one
- Incremental scan review UX was extended.
  - Results page adds a delta filter for `new|changed|revalidated`.
  - `src/ui/dialogs/session_compare_dialog.py` provides dedicated session-delta review.
- Scheduler moved from single-job assumptions to named multi-job workflow.
  - Settings now support create/edit/delete/run-now per saved job and show recent run history.
- Added `Insights` page and navigation slot.
  - Sidebar/page stack now includes `scan/results/tools/insights/settings`.
  - Metrics summarize recent sessions, reclaim estimates, failure rate, quarantine usage, and scheduled runs.
- Watch mode now triggers real rerun behavior.
  - `src/ui/controllers/watch_controller.py` uses `watchdog` when available and polling fallback otherwise.
  - File events during an active scan are coalesced into one pending rerun.
- Post-delete empty-folder cleanup is now executed from operation flow.
  - `src/core.empty_folder_finder.cleanup_empty_parent_folders(...)`
  - cleanup runs only for affected parent trees and is logged as a separate operation.
- Similar-document detection is enabled for `.txt`, `.md`, `.csv`, `.json`, `.py`, `.pdf`.
  - `pypdf` is used for PDF text extraction.
- Current regression baseline in this workspace:
  - `pytest -q` -> `131 passed, 1 skipped`
