# AI Project Context: PyDuplicate Finder Pro

이 문서는 AI 에이전트가 `PyDuplicate Finder Pro` 프로젝트의 구조, 로직 흐름, 그리고 핵심 규칙을 이해하기 위해 작성되었습니다.

## 1. 프로젝트 정체성 (Project Identity)
- **이름**: PyDuplicate Finder Pro
- **목적**: 고성능 멀티스레드 중복 파일 탐색기 및 안전한 정리 도구 (최적화됨)
- **기술 스택**: Python 3.9+, PySide6 (Qt for Python), SQLite (Caching, WAL), Standard Libs

## 2. 디렉토리 구조 및 모듈 맵 (Directory Structure & Module Map)

프로젝트는 `src` 패키지 하위에 `core` (비즈니스 로직)와 `ui` (프레젠테이션 로직)로 엄격하게 구분됩니다.

```text
g:/.../duplicate_finder/
├── main.py                  [Entry Point] 애플리케이션 초기화 및 실행
└── src/
    ├── core/                [Business Logic Layer]
    │   ├── scanner.py             # ScanWorker: 멀티스레드 파일 스캔, 해싱, Inode 중복 체크
    │   ├── cache_manager.py       # CacheManager: SQLite 기반 해시 캐시 (WAL 모드, Thread-safe)
    │   ├── history.py             # HistoryManager: Undo/Redo 트랜잭션 및 안전한 임시 삭제 관리
    │   ├── empty_folder_finder.py # EmptyFolderFinder: 재귀적 빈 폴더 탐색 알고리즘
    │   └── file_ops.py            # FileOperationWorker: 비동기 파일 삭제/복구 처리 (UI 프리징 방지)
    ├── ui/                  [Presentation Layer]
    │   ├── main_window.py         # DuplicateFinderApp: 메인 GUI, 글로벌 에러 핸들링
    │   ├── empty_folder_dialog.py # EmptyFolderDialog: 빈 폴더 정리용 모달 다이얼로그
    │   └── components/
    │       └── results_tree.py    # ResultsTreeWidget: 결과 목록 UI 및 배치 렌더링 로직 (모듈화)
    └── utils/               [Utilities]
        └── i18n.py                # 다국어 문자열 상수 관리
```

## 3. 핵심 클래스 및 상세 명세 (Key Classes & Specifications)

### A. `src.core.scanner.ScanWorker` (QThread)
중복 파일 탐색의 핵심 엔진입니다.
- **역할**: `os.scandir` 기반 고속 탐색 -> 크기 필터링 -> 1차 해시(Partial) -> 2차 해시(Full BLAKE2b) -> (옵션) 바이트 비교.
- **주요 속성**:
    - `max_workers`: CPU 코어 수에 맞춘 스레드 풀 크기.
    - `min_size`: 무시할 최소 파일 크기.
    - `protect_system`: 시스템 폴더 스캔 방지 플래그.
- **구현 특징**:
    - **Inode Check**: 심볼릭/하드 링크 중복 방지를 위해 `(dev, ino)` 쌍을 추적하여 물리적 파일 중복 집계 방지.
    - **ThreadPoolExecutor**: `get_file_hash` 메서드를 병렬로 실행하여 I/O 대기 시간을 최소화.
    - **Progress Throttling**: GUI 멈춤 방지를 위해 `progress_updated` 시그널을 최대 100ms 간격으로 방출.
    - **1MB Buffer**: `open(..., 'rb')` 시 1MB 버퍼를 사용하여 읽기 성능 최적화.

### B. `src.core.cache_manager.CacheManager`
스캔 속도를 가속화하기 위한 영구 캐시 저장소입니다.
- **DB 스키마**: `file_hashes (path PK, size, mtime, hash_partial, hash_full, last_seen)` (Generic Hash Columns)
- **최적화**:
    - **WAL Mode**: `PRAGMA journal_mode=WAL` 적용으로 동시 읽기/쓰기 성능 극대화.
    - **Synchronous NORMAL**: 디스크 동기화 오버헤드 감소.
    - **Thread-Local**: `threading.local()`을 사용하여 각 스레드별 독립적인 SQLite 커넥션 유지.

### C. `src.core.history.HistoryManager`
파괴적인 작업(삭제)에 대한 안전장치입니다.
- **트랜잭션 단위**: 한 번의 '삭제' 작업에 포함된 여러 파일들을 하나의 트랜잭션 리스트로 묶어 관리.
- **복구 로직 (`undo`)**:
    - 파일을 원래 위치로 이동 (`shutil.move`).
    - **Safety**: 원래 상위 폴더가 삭제된 경우 `os.makedirs`로 재생성하여 복구 실패 방지.
- **임시 저장소**: `tempfile.mkdtemp`로 생성된 OS 임시 폴더에 삭제된 파일을 보관 및 프로그램 종료 시 정리(`cleanup`).
- **비동기 처리**: `src.core.file_ops.FileOperationWorker`를 통해 별도 스레드에서 실행됨. UI 프리징 없이 대량 삭제 가능.

### D. `src.core.empty_folder_finder.EmptyFolderFinder`
- **알고리즘**: Bottom-Up 방식(`os.walk(topdown=False)`)으로 탐색.
- **재귀적 판단**:
    1. 파일이 없을 것.
    2. 하위 폴더가 하나라도 있다면, 그 하위 폴더들도 모두 '비어있는 폴더 목록'에 포함되어 있어야 함.
    - 이를 통해 `A/B/C`와 같이 중첩된 빈 폴더 구조를 모두 찾아냄.

### E. `src.ui.main_window.DuplicateFinderApp` (QMainWindow)
- **UI 구성**: QSplitter(트리 뷰 | 미리보기 패널). `ResultsTreeWidget` 컴포넌트 사용.
- **최적화**: 결과 목록 렌더링 시 `QTimer`를 이용한 배치 처리(Incremental Update)로 UI 프리징 방지.
- **설정 지속성**: `QSettings`를 사용하여 윈도우 크기, 마지막 선택 폴더, 옵션 등을 레지스트리/설정파일에 저장.

## 4. 코딩 컨벤션 및 규칙 (Coding Conventions & Rules)

1.  **Strict Separation**: UI 코드는 절대 `src.core`에 포함되지 않아야 하며, Core 로직은 `PySide6.QtWidgets`에 의존하지 않아야 함(단, Signal/QThread 등 QtCore는 허용).
2.  **Explicit Imports**: 상대 경로 임포트(`..core`) 대신 절대 경로 임포트(`src.core`) 사용 권장.
3.  **Concurrency Safety**: `scanner.py`나 `cache_manager.py` 수정 시 스레드 안전성(Locking, Thread-local)을 최우선으로 고려.
4.  **Error Handling**: 파일 I/O 작업(삭제, 이동, 읽기)은 항상 `try-except` 블록으로 감싸고, 실패 시에도 앱이 종료되지 않도록 처리.
