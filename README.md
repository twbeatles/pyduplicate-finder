# 🔍 PyDuplicate Finder Pro

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README_EN.md)

**PyDuplicate Finder Pro**는 파이썬(PySide6) 기반의 고성능 중복 파일 관리 도구입니다. 최신 멀티스레딩 기술과 스마트 캐싱을 통해 대용량 파일 시스템에서도 빠르고 정확하게 중복 파일을 탐색하며, 안전한 삭제 복구(Undo) 기능을 제공합니다.

---

## ✨ 주요 기능 (Key Features)

### 🚀 압도적인 성능 (High Performance)
- **초고속 스캔 (Fast I/O)**: `os.scandir` 기반의 재귀 스캔 엔진을 도입하여 기존 `os.walk` 대비 파일 탐색 속도를 비약적으로 향상시켰습니다.
- **최적화된 해싱 (BLAKE2b)**: 64비트 시스템에 최적화된 `BLAKE2b` 알고리즘을 사용하여 MD5보다 빠르고 안전하게 파일을 분석합니다.
- **스마트 캐싱 & 배치 처리**: `SQLite WAL` 모드와 대용량 배치(Batch) 처리를 통해 수십만 개의 파일도 끊김 없이 처리합니다.
- **부드러운 UI**: 결과 목록을 점진적으로 렌더링(Incremental Rendering)하여 대량의 결과 표시 중에도 앱이 멈추지 않습니다.

### 🛡️ 안전 및 정밀성 (Safety & Precision)
- **시스템 보호 (System Protection)**: Windows/Linux의 주요 시스템 폴더(Windows, Program Files 등)를 자동으로 건너뛰어 오작동을 방지합니다.
- **물리적 중복 방지 (Inode Check)**: 심볼릭 링크나 바로가기 등으로 인해 동일한 물리적 파일이 중복 집계되는 것을 원천 차단합니다.
- **안전한 삭제 & 실행 취소 (Robust Undo)**: 비동기 방식의 '삭제/복구' 작업을 지원하여, 대량의 파일을 삭제할 때도 UI가 멈추지 않습니다.
- **휴지통 옵션**: 파일을 영구 삭제하는 대신 시스템 휴지통으로 이동시켜 안전하게 복구할 수 있는 옵션을 제공합니다.
- **파일 잠금 감지**: 삭제 전 다른 프로세스에서 사용 중인 파일을 자동으로 감지하여 오류를 방지합니다.
- **자동 정리**: 프로그램 종료 시 임시 폴더가 자동으로 정리됩니다. (atexit 핸들러)

### 🎨 모던 UI & 사용자 경험
- **다양한 스캔 모드**: 
    - **유사 이미지 탐지 (pHash)**: 시각적으로 비슷한 이미지(리사이즈, 변형 등)를 찾아냅니다.
    - **파일명 비교**: 파일 내용은 다르더라도 이름이 같은 파일들을 빠르게 찾아냅니다.
- **제외 패턴 (Exclude Patterns)**: `node_modules`, `.git`, `*.tmp` 등 원하지 않는 폴더나 파일을 스캔에서 제외할 수 있습니다.
- **스캔 프리셋**: 자주 사용하는 스캔 설정(유사 이미지 모드, 특정 확장자 등)을 프리셋으로 저장하고 불러올 수 있습니다.
- **결과 저장/로드**: 긴 시간 스캔한 결과를 JSON 파일로 저장했다가 나중에 다시 열어볼 수 있습니다.
- **직관적인 트리 뷰**: 결과 트리를 전체 펼치거나 접을 수 있으며, 우클릭 메뉴로 다양한 작업을 수행합니다.
- **커스텀 단축키**: 사용자 편의에 맞춰 모든 기능의 단축키를 설정할 수 있습니다.
- **다국어 지원**: 한국어/영어 인터페이스를 지원합니다.

---

## 📁 프로젝트 구조 (Project Structure)

```
duplicate_finder/
├── main.py                  # 애플리케이션 진입점
├── requirements.txt         # 의존성 목록
├── PyDuplicateFinder.spec   # PyInstaller 빌드 설정
├── src/
│   ├── core/                # 비즈니스 로직 (UI 독립)
│   │   ├── scanner.py           # 멀티스레드 스캔 엔진
│   │   ├── cache_manager.py     # SQLite 캐시 관리
│   │   ├── history.py           # Undo/Redo 트랜잭션
│   │   ├── file_ops.py          # 비동기 파일 작업
│   │   ├── image_hash.py        # 유사 이미지 탐지 (pHash)
│   │   ├── file_lock_checker.py # 파일 잠금 감지
│   │   ├── preset_manager.py    # 스캔 프리셋 관리
│   │   └── empty_folder_finder.py # 빈 폴더 탐색
│   ├── ui/                  # GUI 레이어
│   │   ├── main_window.py       # 메인 윈도우
│   │   ├── theme.py             # 테마 스타일시트
│   │   ├── empty_folder_dialog.py
│   │   ├── components/
│   │   │   └── results_tree.py  # 결과 트리 위젯
│   │   └── dialogs/
│   │       ├── preset_dialog.py
│   │       ├── exclude_patterns_dialog.py
│   │       └── shortcut_settings_dialog.py
│   └── utils/
│       └── i18n.py              # 다국어 문자열 관리
└── docs/
    ├── claude.md            # AI 컨텍스트 (Claude)
    └── gemini.md            # AI 컨텍스트 (Gemini)
```

---

## 📥 설치 방법 (Installation)

### 전제 조건
- Python 3.9 이상

### 의존성 패키지
| 패키지 | 용도 |
|--------|------|
| PySide6 | Qt GUI 프레임워크 |
| imagehash | 유사 이미지 탐지 (pHash) |
| Pillow | 이미지 처리 |
| send2trash | 휴지통 기능 |
| psutil | 파일 잠금 프로세스 확인 |

### 설치 단계

1. **리포지토리 복제**
   ```bash
   git clone https://github.com/your-username/PyDuplicateFinder.git
   cd PyDuplicateFinder
   ```

2. **가상 환경 생성 (권장)**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **의존성 설치**
   ```bash
   pip install -r requirements.txt
   ```

---

## 📖 사용 방법 (Usage Guide)

### 1. 프로그램 실행
```bash
python main.py
```

### 2. 검색 설정
- **파일 위치 추가**: '폴더 추가' 혹은 드래그 앤 드롭으로 검색할 위치를 등록합니다.
- **필터 옵션**:
    | 옵션 | 설명 |
    |------|------|
    | 파일명만 비교 | 내용 해시 없이 이름만 비교 (초고속) |
    | 유사 이미지 탐지 | 시각적 유사성 분석 (0.1~1.0 임계값) |
    | 휴지통 사용 | 영구 삭제 대신 휴지통으로 이동 |
    | 제외 패턴 | 스캔에서 제외할 glob 패턴 설정 |

### 3. 스캔 및 중복 확인
- **스캔 시작**: 버튼을 누르면 빠른 속도로 스캔이 진행됩니다.
- **스캔 취소**: 진행 중 언제든 중지 버튼으로 취소할 수 있습니다.
- **결과 확인**:
    - 왼쪽 트리 뷰에서 중복 파일 그룹을 확인
    - 상단 툴바의 `+`/`-` 버튼으로 트리 펼치기/접기
    - 파일 클릭 시 오른쪽 패널에서 **미리보기** 표시

### 4. 정리 및 삭제
- **자동 선택 (스마트)**: 각 그룹에서 가장 오래된 파일을 원본으로 남기고 나머지 선택
- **선택 항목 삭제**: 잠금 감지 후 안전하게 삭제
- **실행 취소 (Undo)**: `Ctrl+Z`로 복구 (휴지통 사용 시 제외)

### 5. 고급 기능
| 기능 | 설명 |
|------|------|
| 결과 저장/불러오기 | JSON 파일로 스캔 결과 관리 |
| 프리셋 관리 | 자주 사용하는 설정 저장/로드 |
| 단축키 설정 | 모든 기능의 단축키 커스터마이징 |
| 빈 폴더 찾기 | 빈 폴더 탐색 및 일괄 삭제 |

---

## 🏗️ 패키징 (Build Executable)

단독 실행 가능한 `.exe` 파일을 생성하려면:
```bash
pyinstaller PyDuplicateFinder.spec
```
생성된 파일: `dist/PyDuplicateFinderPro.exe`

---

## 🔧 기술 스택

| 카테고리 | 기술 |
|----------|------|
| 언어 | Python 3.9+ |
| GUI | PySide6 (Qt for Python) |
| 캐싱 | SQLite (WAL 모드) |
| 해싱 | BLAKE2b |
| 이미지 분석 | pHash (imagehash) |
| 병렬 처리 | concurrent.futures.ThreadPoolExecutor |

---

## 🤝 기여하기 (Contributing)
이 프로젝트는 지속적으로 개선되고 있습니다. 성능 개선 아이디어나 버그 리포트는 언제든 환영합니다!

## 📝 라이선스
MIT License