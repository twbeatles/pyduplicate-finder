# AI Project Context: PyDuplicate Finder Pro

이 문서는 AI 에이전트가 `PyDuplicate Finder Pro` 프로젝트의 구조, 로직 흐름, 그리고 핵심 규칙을 이해하기 위해 작성되었습니다.

## 1. 프로젝트 정체성 (Project Identity)
- **이름**: PyDuplicate Finder Pro
- **버전**: 1.3.0
- **목적**: PySide6 및 Native Rust 코어 기반의 고성능 멀티스레드 중복 파일 탐색기 및 안전한 정리 도구
- **기술 스택**: Python 3.9+, Rust (PyO3, Rayon, BLAKE2b), PySide6 (Qt for Python), SQLite (Caching, WAL), Standard Libs

## 2. 디렉토리 구조 및 모듈 맵 (Directory Structure & Module Map)

프로젝트는 `rust` (네이티브 코어), `src/core` (비즈니스 로직), `src/ui` (프레젠테이션 로직)로 명확히 분리됩니다.

```text
duplicate_finder/
├── main.py                  [Entry Point] 애플리케이션 초기화 및 실행
├── requirements.txt         [Dependencies] 의존성 패키지 목록
├── PyDuplicateFinder.spec   [Packaging] PyInstaller 빌드 스펙 (Native C-extension 포함)
├── scripts/
│   ├── build_rust_core.ps1  # Rust 코어(pydup_core) 릴리스 휠 빌드 및 pip 설치
│   └── test_rust_core.ps1   # Rust cargo test 및 clippy 자동 검증
├── rust/
│   └── pydup_core/          [Rust Native Core] PyO3 C-extension
│       ├── Cargo.toml
│       └── src/
│           ├── lib.rs       # PyO3 진입점 & GIL 해제
│           ├── hashing.rs   # BLAKE2b partial/full/batch 병렬 해싱 (Rayon)
│           ├── byte_compare.rs # 1MiB 스트리밍 바이트 정밀 비교
│           ├── discovery.rs # 고속 파일시스템 순회 & 필터링
│           ├── cancellation.rs # AtomicBool 취소 토큰
│           └── models.rs    # HashResult 데이터 모델
└── src/
    ├── core/                [Business Logic Layer]
    │   ├── native/                # Rust pydup_core 브릿지 및 Python fallback
    │   ├── scanner/               # ScanWorker façade + scan 단계별 helper 모듈
    │   ├── cache_manager/         # CacheManager façade + DB/schema/session/quarantine/jobs helper 모듈
    │   ├── history.py             # HistoryManager: Undo/Redo 트랜잭션 및 안전한 임시 삭제 관리
    │   ├── empty_folder_finder.py # EmptyFolderFinder + EmptyFolderWorker: 비동기 빈 폴더 탐색
    │   ├── operation_queue.py      # OperationWorker: 삭제/복구/하드링크 작업 큐 워커
    │   ├── result_schema.py        # 결과 JSON v3 스키마 및 legacy/v2/v3 호환 로더
    │   ├── result_groups.py        # 결과 그룹 분류/위험도/하드링크 eligibility
    │   ├── document_hash.py        # SimHash 기반 유사 문서 탐지
    │   ├── scan_types.py           # selection/exemption/review/collection 타입
    │   ├── image_hash.py          # ImageHasher: pHash 기반 유사 이미지 탐지 (BK-Tree)
    │   ├── file_lock_checker.py   # FileLockChecker: 파일 잠금 상태 확인
    │   └── preset_manager.py      # PresetManager: 스캔 설정 프리셋 관리 (기본값 병합)
    ├── ui/                  [Presentation Layer]
    │   ├── main_window.py         # DuplicateFinderApp: 조립/호환 레이어
    │   ├── main_window_parts/     # 메인 윈도우 책임 분리 모듈
    │   │   ├── ui_shell/              # build/translate/theme/navigation submixin
    │   │   ├── scan_flow/             # folders/lifecycle/config submixin
    │   │   ├── results_flow/          # rendering/selection/filtering/preview/actions/persistence
    │   │   ├── settings_flow/         # persistence/session_restore/dialogs/cache_settings
    │   │   ├── tools_flow/            # quarantine/operations/rules/hardlink
    │   │   ├── schedule_flow.py       # 스케줄 검증/tick/자동 export/실행 기록
    │   │   └── typing_contract/       # 동적 위젯 속성 계약 + host protocol 세분화
    │   ├── theme/                 # ModernTheme: 라이트/다크 테마 스타일시트
    │   ├── empty_folder_dialog.py # EmptyFolderDialog: 빈 폴더 정리용 모달 다이얼로그
    │   ├── controllers/
    │   │   ├── scan_controller.py       # ScanWorker 생성/시그널 바인딩
    │   │   ├── scheduler_controller.py  # 예약 스캔 구성/실행 기록 관리
    │   │   ├── watch_controller.py      # watch mode / debounce / rerun orchestration
    │   │   ├── ops_controller.py        # 실패 재시도 Operation 생성
    │   │   ├── operation_flow_controller.py # 작업 큐/프로그레스/완료 처리 오케스트레이션
    │   │   ├── navigation_controller.py # Sidebar/QStackedWidget 네비게이션 제어
    │   │   ├── results_controller.py    # 결과 선택/적용 계산
    │   │   └── preview_controller.py    # 미리보기 비동기 로딩/LRU
    │   ├── components/
    │   │   ├── results_tree/      # ResultsTreeWidget: 결과 목록 UI 및 배치 렌더링
    │   │   ├── sidebar.py         # Sidebar: 페이지 네비게이션
    │   │   └── toast.py           # ToastManager: 사용자 알림
    │   └── dialogs/
    │       ├── preset_dialog.py           # 프리셋 관리 다이얼로그
    │       ├── exclude_patterns_dialog.py # 제외 패턴 설정 다이얼로그
    │       └── shortcut_settings_dialog.py # 단축키 설정 다이얼로그 (테마 상속)
    └── utils/               [Utilities]
        └── i18n/                  # 다국어 문자열 관리 (DEBUG_I18N 지원)
```

## 3. 핵심 클래스 및 상세 명세 (Key Classes & Specifications)

### A. `src.core.scanner.ScanWorker` (QThread)
중복 파일 탐색의 핵심 엔진입니다.
- **역할**: `os.scandir` 기반 고속 탐색 -> 크기 필터링 -> 1차 해시(Partial) -> 2차 해시(Full BLAKE2b) -> (옵션) 바이트 비교.
- **주요 속성**:
    - `max_workers`: CPU 코어 수에 맞춘 스레드 풀 크기.
    - `min_size`: 무시할 최소 파일 크기.
    - `protect_system`: 시스템 폴더 스캔 방지 플래그.
    - `use_similar_image`: 유사 이미지 탐지 모드.
    - `use_mixed_mode`: mixed pipeline 모드(CLI에서는 `--mixed-mode` 지정 시 `use_similar_image`도 자동 활성화).
- **구현 특징**:
    - **Inode Check**: 심볼릭/하드 링크 중복 방지를 위해 `(dev, ino)` 쌍을 추적.
    - **ThreadPoolExecutor**: `get_file_hash` 메서드를 병렬로 실행.
    - **Parallel pHash**: 유사 이미지 스캔 시 pHash도 병렬 계산.
    - **Progress Throttling**: 100ms 간격으로 진행률 업데이트.
    - **1MB Buffer**: 대용량 파일 읽기 성능 최적화.
    - **Resource Cleanup**: `finally` 블록에서 `cache_manager.close_all()` 호출로 모든 스레드 커넥션 정리.
    - **Cancel Safety**: `threading.Event` 기반의 취소 신호를 사용하며, 취소 시 `scan_cancelled` 시그널을 발행.
    - **Bounded Execution**: `ThreadPoolExecutor`의 작업 큐 크기를 제한하여 대용량 스캔 시 메모리 폭증(OOM) 방지.
    - **세션 재개**: 세션별 해시 진행 정보를 저장하여 재시작 시 해싱 단계를 재사용.
    - **Name-only 모드**: 파일 내용 해시 없이 파일명 기준으로 그룹핑.
    - **Signals**: 완료 시 `scan_finished`, 취소 시 `scan_cancelled`, 오류 시 `scan_failed`.

### B. `src.core.cache_manager.CacheManager`
스캔 속도를 가속화하기 위한 영구 캐시 저장소입니다.
- **DB 스키마**:
    - `file_hashes (path PK, size, mtime, hash_partial, hash_full, last_seen)`
    - `scan_sessions (id PK, status, stage, config_json, config_hash, created_at, updated_at, progress, progress_message)`
    - `scan_files (session_id, path, size, mtime)`
    - `scan_hashes (session_id, path, size, mtime, hash_type, hash_value)`
    - `scan_results (session_id, group_key, path)`
    - `scan_selected (session_id, path, selected)`
    - `scan_file_state (session_id, path, file_exists, selection_reason, exemption_status, review_state, collection_role, baseline_delta)`
- **최적화**:
    - **WAL Mode**: `PRAGMA journal_mode=WAL` 적용.
    - **Synchronous NORMAL**: 디스크 동기화 오버헤드 감소.
    - **Thread-Local**: `threading.local()`을 사용하여 스레드별 독립적인 커넥션 유지.
    - **Connection Tracking**: `weakref.WeakSet`으로 모든 커넥션 추적, `close_all()`로 일괄 정리.

### C. `src.core.history.HistoryManager`
파괴적인 작업(삭제)에 대한 안전장치입니다.
- **트랜잭션 단위**: 한 번의 '삭제' 작업에 포함된 파일들을 하나의 트랜잭션으로 관리.
- **복구 로직 (`undo`)**: 백업 확인 -> 부모 폴더 재생성 -> 파일 이동.
- **안전한 백업**: `UUID`와 타임스탬프를 결합한 고유 파일명 생성으로, 동시 삭제 시 파일명 충돌(데이터 유실) 방지.
- **격리함 보존 정책**: Undo 가능한 삭제는 persistent 격리함으로 이동되며, 설정한 보존 기간/용량 정책에 따라 정리.
- **비동기 처리**: `OperationWorker`(`src/core/operation_queue.py`)를 통해 UI 프리징 없이 실행.

### D. `src.core.empty_folder_finder.EmptyFolderFinder`
- **알고리즘**: Bottom-Up 방식(`os.walk(topdown=False)`)으로 탐색.
- **취소 지원**: `check_cancel` 콜백 파라미터로 스캔 중 취소 가능.
- **재귀적 판단**: 하위 폴더들도 모두 비어있어야 상위 폴더가 빈 폴더로 판정.

### E. `src.core.image_hash.ImageHasher`
유사 이미지 탐지를 위한 pHash(Perceptual Hash) 엔진입니다.
- **알고리즘**: `imagehash` 라이브러리의 pHash 사용.
- **고속 그룹핑 (BK-Tree)**: **BK-Tree**와 **Union-Find** 알고리즘을 도입하여, 기존 $O(N^2)$ 비교 방식을 $O(N \log N)$ 수준으로 혁신적으로 개선.
- **유사도**: 해밍 거리(Hamming Distance)를 기반으로 0.0 ~ 1.0 사이의 유사도 계산.
- **그룹핑**: progress_callback, check_cancel 콜백으로 진행률 보고 및 취소 지원.

### F. `src.core.file_lock_checker.FileLockChecker`
파일 삭제 전 사용 중인 파일을 감지하여 오류를 방지합니다.
- **Windows**: `msvcrt.locking` API로 잠금 확인, `psutil`로 프로세스 확인.
- **Zero-byte 파일 안전성**: 먼저 파일 open 가능 여부를 확인하고, 파일 크기가 0보다 큰 경우에만 byte-range lock을 적용해 false unlocked를 줄임.
- **Linux/Mac**: `fcntl.flock` 사용.

### G. `src.core.preset_manager.PresetManager`
스캔 설정을 JSON 파일로 관리합니다.
- **위치**: 사용자 홈 디렉토리 `~/.pyduplicatefinder/presets/`
- **기능**: 저장, 불러오기, 삭제, 내보내기/가져오기.

### H. `src.ui.main_window.DuplicateFinderApp` (QMainWindow)
- **조립/호환 레이어**: 공개 import 경로(`src.ui.main_window.DuplicateFinderApp`)와 메서드/설정 키 호환성을 유지.
- **UI 구성**: QSplitter(트리 뷰 | 미리보기 패널). `ResultsTreeWidget` 컴포넌트 사용.
- **최적화**: `QTimer`를 이용한 배치 처리로 UI 프리징 방지.
- **설정 지속성**: `QSettings`를 사용하여 윈도우 크기, 옵션 등 저장.
- **세션 복원**: 마지막 스캔 세션을 감지하고 재개/새 스캔 선택을 제공.
- **페이지 네비게이션**: `Sidebar` + `QStackedWidget`으로 스캔/결과/도구/설정 화면 구성.
- **알림 UX**: `ToastManager`로 페이지 이동/상태 알림 제공.
- **책임 분리**: 실동작 메서드는 `src.ui.main_window_parts.*` mixin으로 이동해 단일 책임을 강화.
- **타입 안정성**: 동적 UI 속성은 `typing_contract/`의 `TYPE_CHECKING` 계약으로 관리.

## 4. 코딩 컨벤션 및 규칙 (Coding Conventions & Rules)

1. **Strict Separation**: UI 코드는 절대 `src.core`에 포함되지 않아야 함. Core 로직은 `PySide6.QtWidgets`에 의존하지 않아야 함 (Signal/QThread 등 QtCore는 허용).
2. **Explicit Imports**: 절대 경로 임포트(`src.core`) 사용 권장.
3. **Concurrency Safety**: `src/core/scanner/`나 `src/core/cache_manager/` 수정 시 스레드 안전성 최우선 고려.
4. **Error Handling**: 파일 I/O 작업은 항상 `try-except` 블록으로 감싸고, 실패 시에도 앱이 종료되지 않도록 처리.
5. **I18n**: 모든 UI 텍스트는 `src.utils.i18n` 모듈의 `strings.tr()` 사용. 하드코딩된 문자열 금지.
6. **Resource Cleanup**: 스레드 종료 시 `finally` 블록에서 리소스 정리.

## 5. 의존성 (Dependencies)

| 패키지 | 버전 | 용도 |
|--------|------|------|
| PySide6 | - | Qt GUI 프레임워크 |
| imagehash | >=4.3.0 | 유사 이미지 탐지 |
| Pillow | >=9.0.0 | 이미지 처리 |
| send2trash | >=1.8.0 | 휴지통 기능 |
| psutil | >=5.9.0 | 파일 잠금 프로세스 확인 |
| watchdog | >=4.0.0 | 실시간 폴더 감시 |
| pypdf | >=5.0.0 | PDF 텍스트 추출 기반 유사 문서 탐지 |
| uuid | (Std Lib) | 백업 파일명 충돌 방지 |

## 6. 업데이트 메모 (2026-02-20)

- `src/core/scan_engine.py` 추가: GUI/CLI에서 공통 스캔 옵션 전달 구조를 사용.
- `src/core/scheduler.py` 추가: 예약 스캔의 다음 실행 시각 계산 및 실행 판단.
- `src/ui/controllers/scan_controller.py`, `src/ui/controllers/ops_controller.py` 추가: `main_window` 오케스트레이션 분리 1차 적용.
- `src/ui/controllers/scheduler_controller.py` 추가: 예약 스캔/실행 기록 경로 분리.
- `src/ui/controllers/operation_flow_controller.py` 추가: 작업 큐/프리플라이트/진행/완료 후속처리 분리.
- `src/ui/controllers/navigation_controller.py` 추가: 사이드바 네비게이션/페이지 전환 로직 분리.
- `cache_manager` 스키마 버전 v4: `scan_jobs`, `scan_job_runs` 테이블 추가.
- 스캔 UI에 `mixed_mode`, `detect_duplicate_folders`, `incremental_rescan`, `baseline_session` 옵션 노출.

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

- Deleted legacy path: `src/core/file_ops.py` 제거 및 작업 실행 경로를 `operation_queue` + `operation_flow_controller`로 단일화.
- Added `src/core/result_schema.py`:
  - JSON 저장 포맷을 `version=2` canonical schema로 통합
  - 로더는 legacy GUI / legacy CLI / v2를 모두 호환
- Quarantine 안전성 강화:
  - `insert_quarantine_item <= 0`이면 파일 이동 롤백
  - 롤백 실패 시 명시적인 failure reason 기록
- Preview 동시성 강화:
  - preview cache get/put에 `threading.RLock` 적용
  - `preview_ready`는 `Qt.QueuedConnection` 연결로 메인 스레드 UI 갱신 계약 명시
- Preset 스키마 정합성:
  - `schema_version=2` 저장
  - 구버전 preset 로드 시 신규 키 기본값 자동 병합
- Scheduler/Cache 정책 강화:
  - 스케줄 시간 `HH:MM(00:00~23:59)` 엄격 검증, 실패 시 저장 차단
  - `cache/session_keep_latest`, `cache/hash_cleanup_days` 설정 추가 및 startup cleanup 연동
- Incremental 결과 확장:
  - `ScanWorker.latest_baseline_delta_map` 도입 (`new|changed|revalidated`)
  - CSV 내보내기에서 파일 단위 `baseline_delta` 기록
- Similar-image 의존성 정책:
  - GUI/CLI 모두 의존성(`imagehash`, `Pillow`) 누락 시 fail-fast
- i18n 일관성 정리:
  - `empty_folder_finder.py`, `preset_dialog.py` 하드코딩 문자열 제거

## Update Memo (2026-02-28)

- Duplicate scan reliability hardening is implemented end-to-end.
  - Added consistent cancel checkpoints after file collection, quick/full hash, folder-duplicate stage, and mixed similar-image stage.
  - On cancel, session state is persisted as `paused`, and `scan_cancelled` is emitted instead of `scan_finished`.
- Root-level system-protection guard is enforced.
  - If a selected scan root is protected, the root is skipped entirely.
- Extension normalization is unified.
  - Input extensions are canonicalized to lowercase dotless tokens (so `.txt` and `txt` behave the same).
- Scan telemetry is now first-class output.
  - Metrics: `files_scanned`, `files_hashed`, `files_skipped_error`, `files_skipped_locked`, `errors_total`
  - Metrics and warnings are exposed to UI and CLI, and exported in JSON `meta`.
- Strict mode is now supported in UI and CLI.
  - UI: strict mode toggle + max errors input.
  - CLI: `--strict-mode`, `--strict-max-errors`.
  - Threshold breach marks scan `partial` while still returning results.
- Config hash canonicalization is applied before baseline lookup.
  - Normalizes and sorts folders/extensions/include/exclude patterns for stable hash reuse.
- Session/baseline policy:
  - `partial` sessions are restorable as completed-like results.
  - Baseline candidates remain `completed`-only by design.

## Update Memo (2026-03-09)

- Main-window SOLID split completed:
  - `src/ui/main_window.py` is now a small assembly/compat layer.
  - Behavior moved to `src/ui/main_window_parts/{ui_shell,scan_flow,results_flow,settings_flow,tools_flow}/` packages plus `schedule_flow.py`.
- Added typing contract and host protocols:
  - `src/ui/main_window_parts/typing_contract/` documents dynamic widget attributes and protocolized host interfaces.
- Pylance guardrails locked (no diagnostic relaxation):
  - `pyrightconfig.json` added with Python `3.14`, standard mode, and key diagnostics pinned to `error`.
  - `pyright src tests cli.py main.py` baseline is `0 errors`.
- Encoding regression guardrails:
  - `.editorconfig` enforces UTF-8/LF/final newline.
  - `tests/test_source_encoding_integrity.py` validates UTF-8 decode + no replacement char + known mojibake pattern absence.

## Update Memo (2026-03-11)

- CLI lifecycle hardening:
  - `cli.py` now runs the worker synchronously (`ScanWorker.run()`) instead of creating a separate Qt event loop instance.
  - This avoids cross-mode lifecycle conflicts when CLI and GUI are used in the same process lifetime.
- CLI mixed-mode policy alignment:
  - `--mixed-mode` now implies `use_similar_image=True` in CLI config mapping.
- Incremental reliability hardening:
  - Deep directory skip based only on unchanged directory mtime was removed to prevent missing newly added files after baseline scans.
- File lock detection hardening:
  - `src/core/file_lock_checker.py` now handles zero-byte lock checks more safely on Windows.
- Regression coverage:
  - Added/updated tests around CLI lifecycle, mixed-mode policy, incremental delta behavior, and zero-byte lock checks.
  - Current baseline: full `pytest -q` passes (`104 passed`).

## Update Memo (2026-03-18)

- Large module packageization completed while preserving public import paths:
  - `src/core/cache_manager/`
  - `src/core/scanner/`
  - `src/utils/i18n/`
  - `src/ui/theme/`
  - `src/ui/components/results_tree/`
- Main-window submixins were packageized:
  - `src/ui/main_window_parts/{ui_shell,scan_flow,results_flow,settings_flow,tools_flow}/`
  - each package composes focused submixins over a compatibility `legacy.py`
- Typing contracts were split by host concern:
  - `scan`, `results`, `settings`, `tools`, `ui_shell`, `schedule`, `navigation`, `operation_flow`
- Packaging/docs/test alignment:
  - `PyDuplicateFinder.spec` now uses `collect_submodules(...)` for packageized trees
  - added `tests/test_public_api_facades.py`
  - current baseline: full `pytest -q` passes (`111 passed`)

## Update Memo (2026-04-12)

- Scheduler weekly first-run semantics were corrected.
  - `src/core/scheduler.py:is_due(...)` now waits for the next configured weekday/time slot instead of treating an already-passed weekday as immediately due.
- Zero-byte duplicate handling is aligned across normal collection and cached-session reuse.
  - Empty files are considered duplicate candidates only when `min_size_kb == 0`.
- Scan rollback on cancel/failure now restores the full previous result bundle.
  - Restored state includes checked paths, `file_meta`, missing-file existence flags, and `baseline_delta_map`.
- Result JSON `version=2` was extended additively.
  - `dump_results_v2(...)` can persist `meta.selected_paths`, `meta.file_meta`, and `meta.baseline_delta_map`.
  - `load_results_bundle_any(...)` restores GUI-ready results + meta in one pass while `load_results_any(...)` remains compatibility-only.
- Scheduled auto-export bookkeeping now reflects partial failures.
  - Export failure downgrades `completed -> partial`.
  - Run messages may carry `missing_folders:<n>` and `export_failed:<formats>` suffixes.
- CLI quiet mode semantics were tightened.
  - `--quiet` suppresses successful stdout entirely while keeping errors/cancellation on `stderr`.
- Quarantine retention is no longer capped by the first 5,000 rows.
  - `CacheManager.iter_quarantine_items_oldest(...)` and batched purging are now used by `QuarantineManager.apply_retention(...)`.
- Packaging review:
  - `PyDuplicateFinder.spec` already includes the modules touched by this change set, so no spec edit was required.
- Regression baseline:
  - `pytest -q` -> `122 passed`
  - At that point, `pyright src tests cli.py main.py` was blocked in this workspace by missing local dependency resolution for `imagehash` / `send2trash`.

## Update Memo (2026-04-14)

- Selection/exemption/review pipeline added:
  - `src/core/scan_types.py`
  - `src/core/selection_rules.py` 확장
  - DB schema version `6` with `scan_exemptions`, `review_marks`, `file_signatures`
- Result persistence upgraded to JSON `version=3`.
  - file-level state: `selection_reason`, `exemption_status`, `review_state`, `collection_role`, `baseline_delta`
  - loader remains compatible with legacy / v2 / v3
- Similar document detection added:
  - `src/core/document_hash.py`
  - `src/core/scanner/similar_documents.py`
  - supported: `.txt`, `.md`, `.csv`, `.json`, `.py`, `.pdf`
- UI navigation/pages expanded:
  - new `Insights` page (`src/ui/pages/insights_page.py`)
  - new `SessionCompareDialog` (`src/ui/dialogs/session_compare_dialog.py`)
  - sidebar/page stack now includes `scan/results/tools/insights/settings`
- Scheduler expanded from single `default` job to named multi-job workflow.
  - settings page now supports job create/edit/delete/run-now
  - `scan_job_runs` history is exposed in UI
- Watch mode is now connected to actual rerun behavior.
  - `src/ui/controllers/watch_controller.py`
  - changes during active scan are coalesced into one pending rerun
  - `watchdog` preferred, polling fallback when unavailable
- Post-delete empty-folder cleanup is now executed from operation completion.
  - `src/core.empty_folder_finder.cleanup_empty_parent_folders(...)`
  - separate `empty_folder_cleanup` operation log row is written
- Regression baseline in this workspace at that point:
  - `pytest -q` -> `131 passed, 1 skipped`

## Update Memo (2026-04-28)

- Static type-check baseline restored:
  - `src/core/cache_manager/contracts.py`
  - `src/core/scanner/contracts.py`
  - UI host protocol gaps filled in `src/ui/main_window_parts/typing_contract/`
  - optional `watchdog` import keeps runtime fallback while passing pyright
- Database schema version is now `7`.
  - Added `scan_file_state` for file-level result state persistence.
  - DB automatic session restore now restores the same user-visible state as JSON v3: `file_meta`, file existence, selection reason, exemption status, review state, collection role, and baseline delta.
- Result-group safety is centralized in `src/core/result_groups.py`.
  - UI labels/badges, CSV export `group_type/group_kind`, and hardlink eligibility use the same classifier.
  - Only exact duplicate groups are hardlink eligible; `NAME_ONLY`, `FOLDER_DUP`, `similar_*`, and `doc_similar_*` are blocked.
- Safelist / Ignore policy was normalized.
  - Canonical status is `"safelisted"`; legacy `"safelist"` is normalized by loaders.
  - Incremental baseline-known paths and cached-session reuse now apply the same ignore/exemption and metadata restoration path as normal scans.
  - Content-hash exemptions require an exact full BLAKE2b hash and are disabled for name-only/similar/folder groups.
- UI workflow additions:
  - Tools Safelist/Ignore manager
  - result-tree context actions for exact path, path glob, and exact content-hash exemptions
  - scan folder Path/Role table persisted through settings, presets, and scheduled job snapshots
  - Session Compare filter/select/bulk review/CSV actions
  - risk badges and destructive-action preflight risk summary
  - `operation_plan` JSON v1 save/load with path/size/mtime validation
  - Quarantine status/date/size/path filters and pagination
  - scheduled/watch history structured columns for `missing_folders`, `export_failed`, and `watch_events`
- CLI unsupported options now fail fast:
  - `--watch`
  - `--post-cleanup-empty-dirs`
  - both return exit code `2` with stderr guidance.
- Packaging/local artifact alignment:
  - `PyDuplicateFinder.spec` explicitly includes `src.core.result_groups` and `src.ui.history_messages`, and conditionally collects optional `watchdog`/`pypdf` packages only when installed.
  - `.gitignore` ignores local DB sidecars, result CSV/JSON files, `operation_plan` JSON files, and temp artifacts.
- Current regression baseline in this workspace:
  - `pyright src tests cli.py main.py` -> `0 errors, 0 warnings`
  - `pytest -q` -> `145 passed`

## Update Memo (2026-09-03)

- Native Rust Core (`pydup_core`) 점진적 마이그레이션 완료 (v1.3.0):
  - `rust/pydup_core/`: PyO3 0.24 (abi3-py39) 기반 고속 네이티브 확장.
  - BLAKE2b (32바이트 digest) 스트리밍 Full/Partial 해싱 및 Rayon 병렬 배치 해싱 (`hash_files_batch`).
  - 1MiB 스트리밍 바이트 정밀 비교 (`files_equal`).
  - Rust 고속 파일시스템 순회 및 glob 패턴 매칭 (`discover_files`).
  - `CancellationToken` (`AtomicBool`)을 통한 빠른 비동기 스캔 취소 및 GIL 해제 (`allow_threads`).
- 호환성 & 안전 Fallback:
  - `src/core/native/`: `is_rust_available()`, `get_backend_name()`, `RustCancellationToken`.
  - Rust 확장 미설치나 런타임 오류 시 크래시 없이 기존 Python 백엔드로 투명하게 Fallback.
  - 테스트 환경 동적 모킹(`is_protected`, `get_file_hash`, `_scandir_recursive`) 감지 시 자동 우회.
- 검증 및 성능:
  - Rust 단위 테스트: `cargo test` 4 passed, `cargo clippy` 0 errors, 0 warnings.
  - Parity 테스트: `tests/rust_parity/` 25 passed.
  - 전체 회귀 테스트: `pytest` 170 passed (100%).
  - 10k 파일 벤치마크: 스캔 시간 **4.411s -> 2.176s (50.7% 단축, 2.03배 고속화)**.
- 빌드 & 패키징:
  - `scripts/build_rust_core.ps1` (maturin 릴리스 휠 빌드 및 pip 설치).
  - `scripts/test_rust_core.ps1` (cargo test 및 clippy 자동 검증).
  - `PyDuplicateFinder.spec`에 `pydup_core` 바이너리 및 `src.core.native` hidden imports 등록.

## Update Memo (2026-09-25)

- Rust 감사 후속 조치 (pyo3 보안 업데이트 + 품질 게이트):
  - pyo3 0.24.2 -> 0.29.2: cargo audit 지적 2건 해소 (RUSTSEC-2026-0176, RUSTSEC-2026-0177).
  - 마이그레이션 대응: Python::allow_threads 4곳 -> detach, Clone pyclass 5곳에 rom_py_object 명시 (기존 FromPyObject 동작 유지).
  - 미사용 의존성 	hiserror 제거 (cargo machete clean).
  - cargo fmt --all 적용 (mt --check clean).
- CI 게이트 추가: .github/workflows/rust-audit.yml (fmt -> clippy -D warnings -> cargo test -> machete -> audit).
- 검증: cargo check/clippy 경고 0, cargo test 4 passed, cargo audit 취약점 0, 	ests/rust_parity/ 25 passed (pyo3 0.29.2 abi3 휠 재빌드 후).
