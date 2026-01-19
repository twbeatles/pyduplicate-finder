# AI Project Context: PyDuplicate Finder Pro

이 문서는 AI 에이전트가 `PyDuplicate Finder Pro` 프로젝트의 구조, 로직 흐름, 그리고 핵심 규칙을 이해하기 위해 작성되었습니다.

## 1. 프로젝트 정체성 (Project Identity)
- **이름**: PyDuplicate Finder Pro
- **버전**: 1.1.0
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
    │   ├── empty_folder_finder.py # EmptyFolderFinder: 재귀적 빈 폴더 탐색 알고리즘
    │   ├── file_ops.py            # FileOperationWorker: 비동기 파일 삭제/복구 처리
    │   ├── image_hash.py          # ImageHasher: pHash 기반 유사 이미지 탐지
    │   ├── file_lock_checker.py   # FileLockChecker: 파일 잠금 상태 확인
    │   └── preset_manager.py      # PresetManager: 스캔 설정 프리셋 관리
    ├── ui/                  [Presentation Layer]
    │   ├── main_window.py         # DuplicateFinderApp: 메인 GUI, 글로벌 에러 핸들링
    │   ├── theme.py               # ModernTheme: 라이트/다크 테마 스타일시트
    │   ├── empty_folder_dialog.py # EmptyFolderDialog: 빈 폴더 정리용 모달 다이얼로그
    │   ├── components/
    │   │   └── results_tree.py    # ResultsTreeWidget: 결과 목록 UI 및 배치 렌더링
    │   └── dialogs/
    │       ├── preset_dialog.py           # 프리셋 관리 다이얼로그
    │       ├── exclude_patterns_dialog.py # 제외 패턴 설정 다이얼로그
    │       └── shortcut_settings_dialog.py # 단축키 설정 다이얼로그
    └── utils/               [Utilities]
        └── i18n.py                # 다국어 문자열 상수 관리 (한국어/영어)
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
    - **Progress Throttling**: 100ms 간격으로 진행률 업데이트.
    - **1MB Buffer**: 대용량 파일 읽기 성능 최적화.
    - **Resource Cleanup**: `finally` 블록에서 `cache_manager.close()` 호출로 커넥션 정리.
    - **Cancel Safety**: 취소 시 `scan_finished.emit({})` 호출 보장.

### B. `src.core.cache_manager.CacheManager`
스캔 속도를 가속화하기 위한 영구 캐시 저장소입니다.
- **DB 스키마**: `file_hashes (path PK, size, mtime, hash_partial, hash_full, last_seen)`
- **최적화**:
    - **WAL Mode**: `PRAGMA journal_mode=WAL` 적용.
    - **Synchronous NORMAL**: 디스크 동기화 오버헤드 감소.
    - **Thread-Local**: `threading.local()`을 사용하여 스레드별 독립적인 커넥션 유지.

### C. `src.core.history.HistoryManager`
파괴적인 작업(삭제)에 대한 안전장치입니다.
- **트랜잭션 단위**: 한 번의 '삭제' 작업에 포함된 파일들을 하나의 트랜잭션으로 관리.
- **복구 로직 (`undo`)**: 백업 확인 -> 부모 폴더 재생성 -> 파일 이동.
- **자동 정리**: `atexit.register(self.cleanup)`으로 프로그램 종료 시 임시 폴더 자동 정리.
- **비동기 처리**: `FileOperationWorker`를 통해 UI 프리징 없이 실행.

### D. `src.core.empty_folder_finder.EmptyFolderFinder`
- **알고리즘**: Bottom-Up 방식(`os.walk(topdown=False)`)으로 탐색.
- **취소 지원**: `check_cancel` 콜백 파라미터로 스캔 중 취소 가능.
- **재귀적 판단**: 하위 폴더들도 모두 비어있어야 상위 폴더가 빈 폴더로 판정.

### E. `src.core.image_hash.ImageHasher`
유사 이미지 탐지를 위한 pHash(Perceptual Hash) 엔진입니다.
- **알고리즘**: `imagehash` 라이브러리의 pHash 사용.
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
