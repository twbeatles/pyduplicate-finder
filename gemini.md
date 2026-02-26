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
│   ├── scanner.py               # ScanWorker: QThread 기반 병렬 스캔/해싱 + 병렬 pHash
│   ├── cache_manager.py         # SQLite 캐시 (WAL 모드, Thread-local, close_all())
│   ├── history.py               # Undo/Redo 트랜잭션 + atexit 자동 정리 + 디스크 공간 체크
│   ├── operation_queue.py       # OperationWorker: 삭제/복구/하드링크 작업 큐
│   ├── result_schema.py         # 결과 JSON v2 스키마 및 legacy 호환 로더
│   ├── image_hash.py            # pHash 기반 유사 이미지 탐지 (BK-Tree + Union-Find)
│   ├── file_lock_checker.py     # 파일 잠금 상태 확인
│   ├── preset_manager.py        # 스캔 프리셋 JSON 관리 (기본값 병합)
│   └── empty_folder_finder.py   # 빈 폴더 탐색 + EmptyFolderWorker (비동기)
├── ui/                      [PySide6 GUI]
│   ├── main_window.py           # 메인 화면 + scan_results 동기화 + 언어/테마 유지
│   ├── theme.py                 # 라이트/다크 테마 스타일시트
│   ├── empty_folder_dialog.py   # 빈 폴더 정리 다이얼로그 (비동기)
│   ├── components/
│   │   ├── results_tree.py      # 결과 트리 위젯 (배치 렌더링)
│   │   ├── sidebar.py           # 사이드바 네비게이션
│   │   └── toast.py             # 토스트 알림
│   └── dialogs/
│       ├── preset_dialog.py
│       ├── exclude_patterns_dialog.py
│       └── shortcut_settings_dialog.py  # 테마 상속 지원
└── utils/
    └── i18n.py                  # 한국어/영어 다국어 지원 + DEBUG_I18N
```

## 3. 핵심 기술 구현 상세 (Implementation Details)

### 스캔 및 성능 최적화 (`scanner.py`)
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

### DB 최적화 (`cache_manager.py`)
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
```

## 5. 유지보수 가이드
1. **core/ui 분리**: 기능 수정 시 `core`와 `ui` 의존성 분리 유지
2. **스레드 안전**: `scanner.py`, `cache_manager.py` 수정 시 동시성 고려
3. **다국어 확장**: 새 UI 텍스트는 `src/utils/i18n.py`에 추가
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
