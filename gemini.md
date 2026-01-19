# AI Project Context: PyDuplicate Finder Pro

이 문서는 AI 에이전트가 `PyDuplicate Finder Pro`의 아키텍처와 구현 상세를 파악하기 위한 기술 문서입니다.

## 1. 프로젝트 개요
**PyDuplicate Finder Pro**는 PySide6 기반의 데스크톱 애플리케이션으로, 멀티스레딩과 스마트 캐싱을 활용해 중복 파일을 고속으로 탐색하고 관리합니다.

## 2. 코드베이스 구조 (Codebase Structure)

### 패키지 구조
- **`main.py`**: 부트스트래퍼. `QApplication` 초기화 및 폰트 설정, 메인 윈도우 실행.
- **`src/`**: 소스 코드 루트
    - **`core/`**: UI 독립적인 비즈니스 로직
        - **`scanner.py`**: `ScanWorker` 클래스. `QThread` 상속. `concurrent.futures`를 이용한 병렬 스캔 및 해싱 구현.
        - **`cache_manager.py`**: SQLite 기반 캐시. `WAL` 모드 및 `threading.local`로 고성능 동시성 처리.
        - **`history.py`**: 파일 삭제/복구 트랜잭션 관리. 부모 폴더 자동 재생성 로직 포함.
        - **`file_ops.py`**: `history.py`의 기능을 비동기로 실행하는 `QThread` 워커. (UI 프리징 방지)
        - **`empty_folder_finder.py`**: 중첩된 빈 폴더를 식별하는 재귀적 알고리즘 구현.
    - **`ui/`**: PySide6 기반 GUI
        - **`main_window.py`**: 메인 화면. `ScanWorker` 제어 및 글로벌 예외 처리(`sys.excepthook`) 포함.
        - **`empty_folder_dialog.py`**: 빈 폴더 확인 및 삭제를 위한 모달 다이얼로그.
        - **`components/results_tree.py`**: `QTreeWidget`을 상속받아 결과 목록을 담당하는 독립 컴포넌트. 배치 렌더링 구현.
    - **`utils/`**: 유틸리티
        - **`i18n.py`**: 문자열 상수 및 다국어 지원 기초.

## 3. 핵심 기술 구현 상세 (Implementation Details)

### 스캔 및 성능 최적화 (`scanner.py`)
- **초고속 I/O**: `os.walk` 대신 `os.scandir`을 재귀적으로 사용하여 파일 속성(stat) 접근을 최소화.
- **고속 해싱**: 64비트 시스템에 최적화된 `BLAKE2b` 알고리즘 사용. `ThreadPoolExecutor` 유지.
- **스마트 캐시**: 파일 경로, 크기, 수정 시간(mtime)이 일치하면 해시 계산을 건너뛰고 DB 값을 사용.
- **이벤트 제어**: 과도한 시그널 발생으로 인한 UI 렉을 방지하기 위해 100ms 단위로 진행률 업데이트 스로틀링 적용.
- **물리적 중복 방지**: `Inode`(`st_ino`) 검사를 통해 심볼릭 링크나 바로가기가 가리키는 원본 파일이 중복 스캔되는 것을 방지.

### 데이터 무결성 및 안전 (`history.py`, `scanner.py`)
- **시스템 보호**: Windows 시스템 드라이브의 주요 경로(`\Windows`, `\Program Files` 등)는 스캔 대상에서 원천 배제.
- **원자적 복구**: Undo 작업 시 백업 파일 존재 여부 확인 -> 부모 디렉토리 존재 확인(및 생성) -> 파일 이동 순으로 방어적 로직 수행.
- **I18n**: 모든 UI 텍스트는 `src.utils.i18n` 모듈에서 중앙 관리되어 `Core` 로직이 특정 언어(Korean)에 종속되지 않도록 분리됨.

### DB 최적화 (`cache_manager.py`)
- **SQLite TUNING**:
    - `PRAGMA journal_mode=WAL`: 동시성 향상.
    - `PRAGMA synchronous=NORMAL`: 쓰기 성능 향상.
    - Connection Pooling: 스레드별 커넥션 객체를 `threading.local`로 관리하여 오버헤드 최소화.

## 4. 유지보수 가이드
- 기능을 수정할 때는 반드시 `core`와 `ui`의 의존성을 분리하여 작성하십시오.
- `scanner.py`의 `run` 메서드는 복잡하므로 수정 시 스레드 흐름에 유의해야 합니다.
- 새로운 기능 추가 시 `src/utils/i18n.py`에 UI 텍스트를 추가하여 다국어 확장에 대비하십시오.
