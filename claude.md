# AI Project Context: PyDuplicate Finder Pro

이 문서는 AI 에이전트가 `PyDuplicate Finder Pro` 프로젝트의 구조, 로직 흐름, 그리고 핵심 규칙을 이해하기 위해 작성되었습니다.

## 1. 프로젝트 정체성 (Project Identity)
- **이름**: PyDuplicate Finder Pro
- **버전**: 1.2.0
- **목적**: 고성능 멀티스레드 중복 파일 탐색기 및 안전한 정리 도구
- **기술 스택**: Python 3.9+, PySide6 (Qt for Python), SQLite (Caching, WAL), Standard Libs

## 2. 디렉토리 구조 및 모듈 맵 (Directory Structure & Module Map)

프로젝트는 `src` 패키지 하위에 `core` (비즈니스 로직)와 `ui` (프레젠테이션 로직)로 엄격하게 구분됩니다.

```text
duplicate_finder/
├── main.py                  [Entry Point] 애플리케이션 초기화 및 실행
├── requirements.txt         [Dependencies] 의존성 패키지 목록
└── src/
    ├── core/                [Business Logic Layer]
    │   ├── scanner.py             # ScanWorker: 멀티스레드 파일 스캔, 해싱, Inode 중복 체크
    │   ├── cache_manager.py       # CacheManager: SQLite 기반 해시 캐시 (WAL 모드, Thread-safe)
    │   ├── history.py             # HistoryManager: Undo/Redo 트랜잭션 및 안전한 임시 삭제 관리
    │   ├── empty_folder_finder.py # EmptyFolderFinder + EmptyFolderWorker: 비동기 빈 폴더 탐색
    │   ├── operation_queue.py      # OperationWorker: 삭제/복구/하드링크 작업 큐 워커
    │   ├── result_schema.py        # 결과 JSON v2 스키마 및 legacy 호환 로더
    │   ├── image_hash.py          # ImageHasher: pHash 기반 유사 이미지 탐지 (BK-Tree)
    │   ├── file_lock_checker.py   # FileLockChecker: 파일 잠금 상태 확인
    │   └── preset_manager.py      # PresetManager: 스캔 설정 프리셋 관리 (기본값 병합)
    ├── ui/                  [Presentation Layer]
    │   ├── main_window.py         # DuplicateFinderApp: 메인 GUI, scan_results 동기화
    │   ├── theme.py               # ModernTheme: 라이트/다크 테마 스타일시트
    │   ├── empty_folder_dialog.py # EmptyFolderDialog: 빈 폴더 정리용 모달 다이얼로그
    │   ├── controllers/
    │   │   ├── scan_controller.py       # ScanWorker 생성/시그널 바인딩
    │   │   ├── scheduler_controller.py  # 예약 스캔 구성/실행 기록 관리
    │   │   ├── ops_controller.py        # 실패 재시도 Operation 생성
    │   │   ├── operation_flow_controller.py # 작업 큐/프로그레스/완료 처리 오케스트레이션
    │   │   └── navigation_controller.py # Sidebar/QStackedWidget 네비게이션 제어
    │   ├── components/
    │   │   ├── results_tree.py    # ResultsTreeWidget: 결과 목록 UI 및 배치 렌더링
    │   │   ├── sidebar.py         # Sidebar: 페이지 네비게이션
    │   │   └── toast.py           # ToastManager: 사용자 알림
    │   └── dialogs/
    │       ├── preset_dialog.py           # 프리셋 관리 다이얼로그
    │       ├── exclude_patterns_dialog.py # 제외 패턴 설정 다이얼로그
    │       └── shortcut_settings_dialog.py # 단축키 설정 다이얼로그 (테마 상속)
    └── utils/               [Utilities]
        └── i18n.py                # 다국어 문자열 관리 (DEBUG_I18N 지원)
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
- **Linux/Mac**: `fcntl.flock` 사용.

### G. `src.core.preset_manager.PresetManager`
스캔 설정을 JSON 파일로 관리합니다.
- **위치**: 사용자 홈 디렉토리 `~/.pyduplicatefinder/presets/`
- **기능**: 저장, 불러오기, 삭제, 내보내기/가져오기.

### H. `src.ui.main_window.DuplicateFinderApp` (QMainWindow)
- **UI 구성**: QSplitter(트리 뷰 | 미리보기 패널). `ResultsTreeWidget` 컴포넌트 사용.
- **최적화**: `QTimer`를 이용한 배치 처리로 UI 프리징 방지.
- **설정 지속성**: `QSettings`를 사용하여 윈도우 크기, 옵션 등 저장.
- **세션 복원**: 마지막 스캔 세션을 감지하고 재개/새 스캔 선택을 제공.
- **페이지 네비게이션**: `Sidebar` + `QStackedWidget`으로 스캔/결과/도구/설정 화면 구성.
- **알림 UX**: `ToastManager`로 페이지 이동/상태 알림 제공.
- **컨트롤러 위임**: 스캔/예약/작업플로우/네비게이션 로직을 `src.ui.controllers.*`로 분리하여 오케스트레이션 책임을 축소.

## 4. 코딩 컨벤션 및 규칙 (Coding Conventions & Rules)

1. **Strict Separation**: UI 코드는 절대 `src.core`에 포함되지 않아야 함. Core 로직은 `PySide6.QtWidgets`에 의존하지 않아야 함 (Signal/QThread 등 QtCore는 허용).
2. **Explicit Imports**: 절대 경로 임포트(`src.core`) 사용 권장.
3. **Concurrency Safety**: `scanner.py`나 `cache_manager.py` 수정 시 스레드 안전성 최우선 고려.
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
