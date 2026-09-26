# 🔍 PyDuplicate Finder Pro

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README_EN.md)

**PyDuplicate Finder Pro**는 파이썬(PySide6)과 네이티브 Rust 코어(`pydup_core`)가 결합된 고성능 중복 파일 관리 도구입니다. 최신 멀티스레딩(Rayon) 기술과 스마트 캐싱을 통해 대용량 파일 시스템에서도 빠르고 정확하게 중복 파일을 탐색하며, 안전한 삭제 복구(Undo) 기능을 제공합니다.

---

## ✨ 주요 기능 (Key Features)

### 🚀 압도적인 성능 (High Performance with Rust Core)
- **Native Rust 엔진 (`pydup_core`)**: 핵심 I/O 및 해싱 파이프라인에 PyO3 C-extension을 도입하여, 10,000개 파일 기준 **스캔 소요 시간을 50.7% 단축(2.03배 고속화)**했습니다.
- **초고속 병렬 해싱 (BLAKE2b + Rayon)**: 64비트 시스템에 최적화된 `BLAKE2b` 알고리즘을 Rust Rayon 스레드 풀에서 GIL 없이 병렬 처리하여 대용량 파일 분석 중에도 UI가 멈추지 않습니다.
- **정밀 바이트 스트리밍 비교**: 해시 충돌 위험을 배제하기 위해 1MiB 스트리밍 버퍼 기반의 Rust 네이티브 바이트 비교(`files_equal`)를 제공합니다.
- **초고속 파일 탐색 (Native Discovery)**: Rust 기반의 재귀 디렉토리 순회와 사전 컴파일된 `globset` 패턴 매칭을 통해 수십만 개의 파일 시스템을 순식간에 인덱싱합니다.
- **스마트 캐싱 & 배치 처리**: `SQLite WAL` 모드와 대용량 배치(Batch) 처리를 통해 수십만 개의 파일도 끊김 없이 처리합니다.
- **무손실 Python Fallback**: Rust 모듈 부재 또는 런타임 환경에 따라 자동으로 순수 Python 엔진으로 부드럽게 Fallback됩니다.
- **중단 복구 (Resume Scan)**: 파일 목록/해시 진행 상태를 캐시에 저장하여, 재실행 시 중단된 지점부터 이어서 스캔할 수 있습니다.
- **부드러운 UI**: 결과 목록을 점진적으로 렌더링(Incremental Rendering)하여 대량의 결과 표시 중에도 앱이 멈추지 않습니다.

### 🛡️ 안전 및 정밀성 (Safety & Precision)
- **시스템 보호 (System Protection)**: Windows/Linux의 주요 시스템 폴더(Windows, Program Files 등)를 자동으로 건너뛰어 오작동을 방지합니다.
- **물리적 중복 방지 (Inode Check)**: 심볼릭 링크나 바로가기 등으로 인해 동일한 물리적 파일이 중복 집계되는 것을 원천 차단합니다.
- **안전한 삭제 & 실행 취소 (Robust Undo)**: 비동기 방식의 '삭제/복구' 작업을 지원하여, 대량의 파일을 삭제할 때도 UI가 멈추지 않습니다.
- **휴지통 옵션**: 파일을 영구 삭제하는 대신 시스템 휴지통으로 이동시켜 안전하게 복구할 수 있는 옵션을 제공합니다.
- **파일 잠금 감지**: 삭제 전 다른 프로세스에서 사용 중인 파일을 자동으로 감지하여 오류를 방지합니다.
- **격리함 유지/보존 정책**: Undo 가능한 삭제는 persistent 격리함에 보관되며, 설정한 보존 기간/용량 정책에 따라 정리됩니다.
- **결과 그룹 안전 분류**: 정확 중복, 이름 중복, 폴더 중복, 유사 이미지, 유사 문서를 공통 classifier로 분류하고, 유사/이름/폴더 그룹은 하드링크 통합 대상에서 제외합니다.

### 🎨 모던 UI & 사용자 경험
- **다양한 스캔 모드**: 
    - **유사 이미지 탐지 (pHash + BK-Tree)**: **BK-Tree** 알고리즘을 도입하여 수천 장의 이미지도 $O(N \log N)$ 속도로 순식간에 분석합니다. 시각적으로 비슷한 이미지(리사이즈, 변형 등)를 찾아냅니다.
    - **유사 문서 탐지 (SimHash)**: `.txt`, `.md`, `.csv`, `.json`, `.py`, `.pdf` 문서를 정규화해 near-duplicate 문서를 그룹화합니다.
    - **파일명 비교**: 파일 내용은 다르더라도 이름이 같은 파일들을 빠르게 찾아냅니다.
- **제외 패턴 (Exclude Patterns)**: `node_modules`, `.git`, `*.tmp` 등 원하지 않는 폴더나 파일을 스캔에서 제외할 수 있습니다.
- **스캔 프리셋**: 자주 사용하는 스캔 설정(유사 이미지 모드, 특정 확장자 등)을 프리셋으로 저장하고 불러올 수 있습니다.
- **결과 저장/로드**: 긴 시간 스캔한 결과를 JSON 파일로 저장했다가 나중에 다시 열어볼 수 있습니다.
  - 신규 저장은 `version=3` 공통 스키마를 사용하며, 로더는 legacy / v2 / v3 포맷을 자동 호환합니다.
  - 파일 단위 상태(`selection_reason`, `exemption_status`, `review_state`, `collection_role`, `baseline_delta`)도 함께 보존합니다.
- **자동 세션 복원**: 마지막 스캔 세션을 자동 감지하고 재개/새 스캔 여부를 선택할 수 있습니다.
- **직관적인 트리 뷰**: 결과 트리를 전체 펼치거나 접을 수 있으며, 우클릭 메뉴로 다양한 작업을 수행합니다.
- **실시간 결과 필터**: 이름/경로 기준으로 결과를 빠르게 필터링할 수 있습니다.
- **사이드바 네비게이션**: 스캔/결과/도구/인사이트/설정 화면을 빠르게 이동할 수 있습니다.
- **인사이트 대시보드**: 최근 스캔 세션, 절감 용량, 실패율, 예약 실행 이력을 별도 페이지에서 확인할 수 있습니다.
- **세션 비교 다이얼로그**: 증분 스캔 결과의 `new / changed / revalidated` 파일을 필터링하고, 결과 트리 선택/검토 상태 변경/CSV 내보내기로 바로 이어갈 수 있습니다.
- **컬렉션 역할 테이블**: 스캔 폴더를 Path/Role 테이블로 관리하고 `primary`, `secondary`, `none` 역할을 설정해 보존 정책과 예약 job snapshot에 반영합니다.
- **감시 모드**: 선택 폴더를 계속 감시하고 변경이 감지되면 증분 재스캔을 자동 예약합니다.
- **커스텀 단축키**: 사용자 편의에 맞춰 모든 기능의 단축키를 설정할 수 있습니다.
- **외관 설정**: 화면 밀도(여유 있게/촘촘하게)와 시스템 테마 따르기를 설정 화면에서 조절할 수 있습니다.
- **다국어 지원**: 한국어/영어 인터페이스를 지원합니다.

### 🧰 도구 (Tools)
- **격리함(Quarantine) 관리**: Undo 가능한 삭제 모드로 삭제된 파일을 격리함에서 복구/영구삭제할 수 있습니다.
- **Safelist / Ignore 관리**: Tools 화면에서 path/hash/glob 기반 예외 규칙을 추가, 수정, 삭제, 검색할 수 있으며 결과 트리 우클릭 메뉴에서도 바로 등록할 수 있습니다.
- **자동 선택 규칙(Selection Rules)**: 경로/파일명 패턴(fnmatch) 기반으로 KEEP/DELETE 규칙을 정의하고 그룹/전체 결과에 자동 적용할 수 있습니다.
- **작업 계획 저장/불러오기**: 선택된 삭제 계획을 `operation_plan` JSON v1로 저장하고, 다시 불러올 때 path/size/mtime을 검증해 stale/missing 항목을 제외합니다.
- **작업 기록(Operations Log)**: 삭제/복구/영구삭제/하드링크 등 수행된 작업을 기록하고, 항목별 상세/CSV/JSON 내보내기를 지원합니다.
- **사전 점검(Preflight)**: 하드링크 통합 등 위험도가 있는 작업 전, 잠금/권한/볼륨 조건 등을 사전 점검하여 차단/경고를 표시합니다.
- **하드링크 통합(Hardlink Consolidation, 고급)**: 동일 내용의 중복 파일을 하드링크로 통합해 디스크 사용량을 절감할 수 있습니다(옵션).

---

## 📁 프로젝트 구조 (Project Structure)

```
duplicate_finder/
├── main.py                  # 애플리케이션 진입점
├── requirements.txt         # 의존성 목록
├── PyDuplicateFinder.spec   # PyInstaller 빌드 설정
├── pyrightconfig.json       # Pylance/Pyright 정적 타입 검사 설정 (Python 3.14)
├── .editorconfig            # UTF-8/EOL 규칙
├── claude.md                # AI 컨텍스트 (Claude)
├── gemini.md                # AI 컨텍스트 (Gemini)
├── scripts/
│   ├── build_rust_core.ps1  # Rust 코어(pydup_core) 휠 빌드 및 pip 설치 스크립트
│   └── test_rust_core.ps1   # Rust cargo test 및 clippy 자동 검증 스크립트
├── rust/
│   └── pydup_core/          [Native Rust Core]
│       ├── Cargo.toml
│       └── src/
│           ├── lib.rs       # PyO3 진입점 & GIL 해제
│           ├── hashing.rs   # BLAKE2b partial/full/batch 병렬 해싱 (Rayon)
│           ├── byte_compare.rs # 1MiB 스트리밍 바이트 정밀 비교
│           ├── discovery.rs # 고속 파일시스템 순회 & 필터링
│           ├── cancellation.rs # AtomicBool 취소 토큰
│           └── models.rs    # HashResult 데이터 모델
├── src/
│   ├── core/                # 비즈니스 로직 (UI 독립)
│   │   ├── native/              # Rust pydup_core 브릿지 및 Python fallback
│   │   ├── scanner/             # ScanWorker façade + discovery/hash/incremental/similar-image 분리
│   │   │   ├── __init__.py
│   │   │   ├── worker.py
│   │   │   └── ...
│   │   ├── cache_manager/       # CacheManager façade + DB/schema/session/quarantine/jobs 분리
│   │   │   ├── __init__.py
│   │   │   ├── database.py
│   │   │   └── ...
│   │   ├── history.py           # Undo/Redo 트랜잭션
│   │   ├── result_schema.py     # 결과 JSON v3 스키마/호환 로더
│   │   ├── result_groups.py     # 결과 그룹 분류/위험도/하드링크 eligibility
│   │   ├── image_hash.py        # 유사 이미지 탐지 (pHash)
│   │   ├── document_hash.py     # 유사 문서 탐지 (SimHash / PDF text extraction)
│   │   ├── scan_types.py        # selection/exemption/review/collection 타입
│   │   ├── file_lock_checker.py # 파일 잠금 감지
│   │   ├── preset_manager.py    # 스캔 프리셋 관리
│   │   └── empty_folder_finder.py # 빈 폴더 탐색
│   ├── ui/                  # GUI 레이어
│   │   ├── main_window.py       # 메인 윈도우
│   │   ├── main_window_parts/   # 메인 윈도우 책임 분리 모듈(SOLID)
│   │   │   ├── ui_shell/            # build/translate/theme/navigation submixin
│   │   │   ├── scan_flow/           # folders/lifecycle/config submixin
│   │   │   ├── results_flow/        # rendering/selection/filtering/preview/actions/persistence
│   │   │   ├── settings_flow/       # persistence/session_restore/dialogs/cache_settings
│   │   │   ├── tools_flow/          # quarantine/operations/rules/hardlink
│   │   │   ├── schedule_flow.py
│   │   │   └── typing_contract/     # host protocol 세분화 + aggregate contract
│   │   ├── theme/               # palette/token/stylesheet 분리
│   │   ├── empty_folder_dialog.py
│   │   ├── controllers/         # UI 오케스트레이션 컨트롤러
│   │   │   ├── scan_controller.py
│   │   │   ├── scheduler_controller.py
│   │   │   ├── watch_controller.py
│   │   │   ├── ops_controller.py
│   │   │   ├── operation_flow_controller.py
│   │   │   ├── navigation_controller.py
│   │   │   ├── results_controller.py
│   │   │   └── preview_controller.py
│   │   ├── components/
│   │   │   ├── results_tree/    # 결과 트리 façade + populate/filter/state 분리
│   │   │   ├── sidebar.py       # 사이드바 네비게이션
│   │   │   └── toast.py         # 토스트 알림
│   │   ├── pages/
│   │   │   ├── scan_page.py      # 스캔 페이지(UI)
│   │   │   ├── results_page.py   # 결과 페이지(UI)
│   │   │   ├── tools_page.py     # 도구 페이지(UI)
│   │   │   ├── insights_page.py  # 인사이트 페이지(UI)
│   │   │   └── settings_page.py  # 설정 페이지(UI)
│   │   └── dialogs/
│   │       ├── preset_dialog.py
│   │       ├── exclude_patterns_dialog.py
│   │       ├── selection_rules_dialog.py
│   │       ├── preflight_dialog.py
│   │       ├── operation_log_dialog.py
│   │       ├── session_compare_dialog.py
│   │       └── shortcut_settings_dialog.py
│   └── utils/
│       └── i18n/                # catalog_en/catalog_ko/service 분리
```

---

## 📊 성능 벤치마크 (Performance Benchmark)

10,000개 파일 (500개 중복 그룹) 기준 스캔 성능 비교:

| 측정 항목 | Python Backend | Native Rust Backend | 속도 향상 |
|---|---:|---:|---:|
| **스캔 소요 시간 (`scan_time_sec`)** | **4.411 s** | **2.176 s** | **50.7% 단축 (2.03배 고속화)** |
| **결과 트리 렌더링 (`render_time`)** | 0.960 s | 0.906 s | UI 렌더링 병목 없음 |
| **중복 그룹 검출 정확도** | 500 그룹 | 500 그룹 | 100% 동일 (0 오차) |
| **인덱싱 파일 메타데이터** | 10,000 파일 | 10,000 파일 | 100% 동일 (0 오차) |

---

## 📥 설치 방법 (Installation)

### 전제 조건
- Python 3.9 이상
- Rust 툴체인 (소스에서 Rust 코어를 직접 빌드할 경우: `cargo`, `maturin`)

### 의존성 패키지
| 패키지 | 용도 |
|--------|------|
| PySide6 | Qt GUI 프레임워크 |
| pydup_core | Native Rust 가속 엔진 (PyO3 + Rayon + BLAKE2b) |
| imagehash | 유사 이미지 탐지 (pHash) |
| Pillow | 이미지 처리 |
| send2trash | 휴지통 기능 |
| psutil | 파일 잠금 프로세스 확인 |
| watchdog | 실시간 폴더 감시 |
| pypdf | PDF 텍스트 추출 기반 유사 문서 탐지 |
| darkdetect | OS 다크/라이트 테마 감지 |

### 설치 단계

1. **리포지토리 복제**
   ```bash
   git clone https://github.com/twbeatles/pyduplicate-finder.git
   cd pyduplicate-finder
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

4. **(선택) Native Rust 코어 빌드 및 설치**
   ```powershell
   # Windows (Visual Studio Build Tools 환경 자동 감지)
   powershell -ExecutionPolicy Bypass -File scripts\build_rust_core.ps1
   ```
   *참고: Rust 코어가 없어도 순수 Python 모드로 100% 정상 작동(무손실 Fallback)합니다.*

---

## 📖 사용 방법 (Usage Guide)

### 1. 프로그램 실행
```bash
python main.py
```

### (선택) CLI로 스캔 실행
```bash
python cli.py "D:/Data" "E:/Photos" --extensions jpg,png --output-json result.json --output-csv result.csv
```
- `--similarity-threshold` 값은 `0.0`~`1.0`만 허용됩니다. 범위를 벗어나면 CLI는 에러(`SystemExit 2`)로 종료됩니다.
- `--similar-image` 또는 `--mixed-mode` 사용 시 `imagehash`/`Pillow` 의존성이 없으면 CLI는 즉시 실패(fail-fast)합니다.
- `--mixed-mode`를 사용하면 `--similar-image` 패스가 자동으로 활성화됩니다(별도 플래그 불필요).
- `--watch`, `--post-cleanup-empty-dirs`는 GUI 전용 흐름이므로 CLI에서는 exit code `2`와 명확한 stderr 메시지로 실패합니다.

### 2. 검색 설정
- **파일 위치 추가**: '폴더 추가' 혹은 드래그 앤 드롭으로 검색할 위치를 등록합니다.
- **필터 옵션**:
    | 옵션 | 설명 |
    |------|------|
    | 파일명만 비교 | 내용 해시 없이 이름만 비교 (초고속) |
    | 내용+파일명 모두 일치 | 해시가 같고 파일명도 같은 경우만 그룹화 |
    | 바이트 단위 정밀 비교 | 해시가 같은 후보를 바이트 단위로 재검증 |
    | 유사 이미지 탐지 | 시각적 유사성 분석 (0.1~1.0 임계값) |
    | 유사 문서 탐지 | SimHash 기반 near-duplicate 문서 그룹화 |
    | 휴지통 사용 | 영구 삭제 대신 휴지통으로 이동 |
    | 숨김/시스템 파일 제외 | .으로 시작하는 파일/폴더 및 OS 메타데이터를 제외 |
    | 심볼릭 링크 따라가기 | 심볼릭 링크를 따라 스캔 (루프 감지 포함) |
    | 포함 패턴 | 설정 시, 해당 패턴과 매칭되는 파일만 스캔 |
    | 제외 패턴 | 스캔에서 제외할 패턴(*, ?) 설정 (파일명/전체 경로 매칭) |

### 3. 스캔 및 중복 확인
- **스캔 시작**: 버튼을 누르면 빠른 속도로 스캔이 진행됩니다.
- **스캔 취소**: 진행 중 언제든 중지 버튼으로 취소할 수 있습니다.
- **스캔 이어하기**: 앱을 다시 실행하면 중단된 스캔을 이어서 진행할지 묻습니다.
- **결과 확인**:
    - 왼쪽 트리 뷰에서 중복 파일 그룹을 확인
    - 상단 툴바의 펼치기/접기 버튼으로 트리 펼치기/접기
    - 결과 필터에서 이름/경로로 빠르게 검색
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
| 격리함 관리 | Undo 가능한 삭제로 이동된 파일 복구/영구삭제 |
| Safelist / Ignore 관리 | path/hash/glob 예외 규칙 CRUD, 검색, 결과 트리 우클릭 등록 |
| 자동 선택 규칙 | 패턴 기반 KEEP/DELETE 규칙으로 자동 선택 |
| 작업 기록 | 삭제/복구/정리/하드링크 작업 기록 및 내보내기 |
| 작업 계획 저장/로드 | 선택된 삭제 계획을 JSON으로 저장하고 로드 시 path/size/mtime 검증 |
| 결과 위험도 표시 | 그룹별 위험도 badge 및 파괴적 작업 preflight 위험도 요약 |
| 하드링크 통합 | (고급) 중복 파일을 하드링크로 통합하여 공간 절감 |
| 예약 스캔 스냅샷 | 저장된 예약 설정(`scan_jobs.config_json`)으로 실행되며, 폴더 일부 누락 시 유효 폴더만 실행/전체 누락 시 `skipped(no_valid_folders)` 처리 |
| 다중 예약 작업 | 이름별 scan job 저장/편집/삭제/수동 실행과 최근 실행 이력 확인 |
| 감시 모드 | 폴더 변경 감지 후 debounce 기반 증분 재스캔 예약 |
| 인사이트 | 최근 세션, 절감 용량, 실패율, 예약 실행 이력 표시 |
| 세션 비교 | 증분 스캔 delta(`new`, `changed`, `revalidated`) 검토 |
| 격리함 필터/페이지네이션 | status/date/size/path 필터와 페이지 이동으로 대량 격리함 목록 관리 |
| 캐시 유지 정책 | 세션 보존 개수(`cache/session_keep_latest`)와 해시 캐시 보존 일수(`cache/hash_cleanup_days`)를 설정하고 즉시 적용 |
| 헤드리스 CLI 스캔 | GUI 없이 폴더 스캔 후 JSON/CSV 결과 출력 |

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
| 병렬 처리 | concurrent.futures (Bounded Executor) |
| 이미지 그룹핑 | BK-Tree + Union-Find |

---

## 🤝 기여하기 (Contributing)
이 프로젝트는 지속적으로 개선되고 있습니다. 성능 개선 아이디어나 버그 리포트는 언제든 환영합니다!

## 📝 라이선스
MIT License

## ✅ 구현 상태 (2026-02-26)

다음 항목은 현재 코드에 반영되었습니다.

- 고급 스캔 옵션 노출: 혼합 모드, 중복 폴더 탐지, 증분 재스캔, Baseline 세션 선택
- CLI 확장: `--mixed-mode`, `--detect-folder-dup`, `--incremental-rescan`, `--baseline-session`
- CLI 입력 검증: `--similarity-threshold`는 `0.0~1.0` 범위만 허용 (범위 밖 입력 거부)
- 삭제 Dry-run 요약: 삭제 전 선택/가시 항목/예상 절감 용량 및 그룹 요약 표시
- 작업 재시도 확장: delete 외 hardlink/restore/purge 실패 재시도 경로 강화
- i18n 정리: 코어 하드코딩 메시지(Undo/Redo/Quarantine/History) 다국어 키로 통합
- 예약 스캔(기본): 설정 화면에서 일/주 단위 스케줄 + 자동 JSON/CSV 출력
- 예약 스캔 실행 정책: UI 현재 상태가 아닌 저장 스냅샷(`scan_jobs.config_json`) 기준 실행, 누락 폴더 정책은 `유효 폴더만 실행 / 전체 누락 시 skipped(no_valid_folders)`
- 결과 뷰/내보내기 강화: `FOLDER_DUP` 그룹 라벨 개선, CSV에 `group_kind`, `bytes_reclaim_est`, `baseline_delta` 컬럼 추가
- 결과 JSON 스키마 통합: GUI/CLI 저장은 `version=3` 포맷 사용, 로더는 legacy GUI/legacy CLI/v2/v3를 모두 수용
- 삭제 복구성 강화: Quarantine DB insert 실패 시 파일 이동 롤백 처리(고아 파일 방지)
- 미리보기 동시성 강화: preview cache에 `RLock` 적용, 시그널 연결을 `Qt.QueuedConnection`으로 명시
- 프리셋 스키마 정합성: `schema_version=2` 저장 및 구버전 preset 로드 시 누락 키 기본값 자동 병합
- 스케줄 입력 검증 강화: `HH:MM(00:00~23:59)` 형식 검증 실패 시 저장 차단 + 오류 안내
- 캐시 유지 정책 추가: `cache/session_keep_latest`, `cache/hash_cleanup_days` 설정과 startup cleanup 연동
- 증분 CSV 확장: `baseline_delta`를 파일 단위(`new|changed|revalidated`)로 기록
- 유사 이미지 의존성 정책: GUI/CLI 모두 의존성 누락 시 fail-fast
- 구조 분리 2차 진행:
  - `src/core/scan_engine.py` + `src/ui/controllers/scan_controller.py` + `src/ui/controllers/scheduler_controller.py`
  - 작업 플로우 분리: `src/ui/controllers/operation_flow_controller.py`
  - 네비게이션 분리: `src/ui/controllers/navigation_controller.py`

아래 항목은 후속 리팩터링으로 유지됩니다.

- `legacy.py` 기반 submixin 위임을 더 얇은 서비스/도메인 객체로 단계적 축소
- `schedule_flow.py`에 대해서도 필요 시 동일한 패키지화 패턴 적용

## ✅ 구현 상태 (2026-03-09)

- UI 메인 윈도우를 SOLID 기준으로 분리:
  - `src/ui/main_window.py`는 조립/호환 레이어로 축소
  - 기능 구현은 `src/ui/main_window_parts/{ui_shell,scan_flow,results_flow,settings_flow,tools_flow}/` 패키지와 `schedule_flow.py`로 이동
- 동적 위젯 속성 타입 계약 추가:
  - `src/ui/main_window_parts/typing_contract/`에서 `TYPE_CHECKING` 기반 계약 + host protocol 정의
  - `reportAttributeAccessIssue`를 완화하지 않고 코드로 해결
- Pylance 재발 방지 설정 고정:
  - `pyrightconfig.json` 추가 (범위: `src`, `tests`, `cli.py`, `main.py`; Python 3.14, 핵심 진단 `error` 고정)
- 인코딩 재발 방지:
  - `.editorconfig`로 UTF-8/EOL 규칙 고정
  - `tests/test_source_encoding_integrity.py`로 UTF-8 decode/`U+FFFD`/대표 깨짐 패턴 검사
- 기준선 검증:
  - `pyright src tests cli.py main.py` 결과 `0 errors`
  - (당시 기준) 전체 `pytest`의 `-1073740791` 종료는 기존 사전 존재 이슈로 분리 관리

## ✅ 구현 상태 (2026-03-11)

- CLI 실행 경로 안정화:
  - CLI는 Qt 이벤트 루프를 별도 생성하지 않고 `ScanWorker.run()`을 동기 실행합니다.
  - GUI/CLI 연속 실행 시 프로세스 전역 Qt lifecycle 충돌 가능성을 줄였습니다.
- CLI mixed mode 동작 정합화:
  - `--mixed-mode` 지정 시 유사 이미지 탐지가 자동 활성화됩니다 (`--similar-image` 별도 지정 불필요).
- 파일 잠금 감지 보강:
  - 0바이트 파일에서도 잠금 우회(false unlocked)가 발생하지 않도록 Windows 잠금 확인 흐름을 보강했습니다.
- 증분 스캔 안정성 보강:
  - 디렉토리 mtime만으로 하위 트리를 통째로 생략하지 않도록 정책을 조정해, baseline 이후 신규 파일 누락 가능성을 낮췄습니다.
- 회귀 검증:
  - `pytest -q` 기준 전체 `104 passed`.

## ✅ 구현 상태 (2026-03-18)

- 대형 단일 모듈 패키지화 완료:
  - `src/core/cache_manager/`: `database`, `schema`, `sessions`, `scan_storage`, `operations`, `quarantine`, `hash_cache`, `jobs`
  - `src/core/scanner/`: `worker`, `discovery`, `hashing`, `incremental`, `similar_images`, `folder_duplicates`, `filters`, `metrics`, `state`
  - `src/utils/i18n/`: `catalog_en`, `catalog_ko`, `catalogs`, `service`
  - `src/ui/theme/`: `palettes`, `tokens`, `stylesheet`
  - `src/ui/components/results_tree/`: `populate`, `filtering`, `state`, `appearance`, `constants`
- 메인 윈도우 책임 분리 2차 완료:
  - `src/ui/main_window_parts/{ui_shell,scan_flow,results_flow,settings_flow,tools_flow}/`를 submixin 패키지로 전환
  - `src/ui/main_window_parts/typing_contract/`를 `scan/results/settings/tools/ui_shell/schedule/navigation/operation_flow` host protocol로 세분화
- 공개 import 경로 호환 유지:
  - `CacheManager`, `ScanWorker`, `IMAGE_HASH_AVAILABLE`, `I18n`, `strings`, `ModernTheme`, `DuplicateFinderApp`, `ResultsTreeWidget`
- 회귀/안정성 검증:
  - `tests/test_public_api_facades.py` 추가
  - 현재 전체 기준선: `pytest -q` -> `111 passed`
- 배포 정합성 보강:
  - `PyDuplicateFinder.spec`에서 패키지화된 하위 모듈을 `collect_submodules(...)`로 자동 수집

## Performance Refactor Notes (2026-02)

- Hashing hot path now consumes pre-collected `(path, size, mtime)` tuples to avoid repeated `os.stat` calls.
- Hash/session cache lookup is processed in chunks to reduce memory spikes on large scans.
- Results tree rendering accepts injected metadata and applies filtering inside the widget for faster UI response.
- Selection persistence now uses delta upsert/delete instead of full-table rewrite on each change.
- Operation restore/purge flows now use batch quarantine item fetch with throttled progress updates.

## Performance Refactor Notes (2026-02-21)

- Added delta selection signal on results tree (`files_checked_delta`) while keeping existing `files_checked` behavior.
- Improved large-result interaction via dynamic batch rendering, filter short-circuit, and cached group summaries.
- Added controller split for maintainability/performance: `results_controller.py`, `preview_controller.py`.
- Added async preview loading + LRU cache to reduce UI freeze when moving quickly between items.
- Optimized scanner pattern matching, session progress DB write throttling, hash session batch dedupe, and folder-duplicate full-hash path.
- Reduced memory peak by trimming `file_meta` to final-result paths.
- Optimized operation queue progress/stat calls and CSV export path reuse with optional `file_meta`.

## Benchmark & Regression Guardrails

- Deterministic perf regression tests were added in `tests/`.
- Local benchmark runner:

```bash
python tests/benchmarks/bench_perf.py --files 200000 --groups 5000 --output bench_perf.json
```

## Documentation Sync (2026-02-28)

### CLI strict mode example
```bash
python cli.py "D:/Data" --strict-mode --strict-max-errors 0 --output-json result.json
```

### Result JSON compatibility
- New save/export format: `{"meta": {...}, "results": {...}}`
- Legacy format `{"<group_key>": [...]}` is still supported when loading results.
- `meta` fields include:
  - `scan_status` (`completed` or `partial`)
  - `metrics` (`files_scanned`, `files_hashed`, `files_skipped_error`, `files_skipped_locked`, `errors_total`)
  - `warnings` (for example `strict_mode_threshold_exceeded`)

### Duplicate scan audit completion
- Cancel reliability is now enforced across full-hash, folder-duplicate, and mixed-mode stages.
- Protected roots are skipped at scan-root level.
- Extension normalization now treats `.txt` and `txt` identically.
- Error telemetry is exposed in UI/CLI/JSON meta.
- Strict mode is available in both UI and CLI (`--strict-mode`, `--strict-max-errors`).
- Config hash canonicalization is applied for better baseline reuse.
- Baseline policy remains `completed`-only (`partial` excluded).

## 구현 상태 (2026-04-14)

- DB 스키마 버전이 `6`으로 확장되었습니다.
  - `scan_exemptions`, `review_marks`, `file_signatures` 테이블이 추가되었습니다.
- 선택 정책 엔진이 통합되었습니다.
  - `smart`, `oldest`, `newest`, `path_shortest`, `extension_priority`, `primary_keep`
  - 명시적 규칙 → safelist → 컬렉션 역할 → 속성 우선순위 → fallback 순서로 평가합니다.
- Safelist / Ignore / Review state가 결과와 JSON v3, CSV export에 반영됩니다.
- 결과 JSON `version=3`는 파일 단위 상태를 함께 저장합니다.
  - `selection_reason`, `exemption_status`, `review_state`, `collection_role`, `baseline_delta`
- Results 화면에 delta filter(`new`, `changed`, `revalidated`)와 Session Compare 다이얼로그가 추가되었습니다.
- Settings 화면에 다중 예약 작업 관리 UI가 추가되었습니다.
  - job 생성/수정/삭제/수동 실행
  - 최근 실행 이력 테이블 표시
- Insights 페이지가 추가되었습니다.
  - 최근 세션, 절감 용량, 실패율, 격리함 사용량, 예약 실행 이력 확인
- Watch mode 실제 동작이 연결되었습니다.
  - `watchdog` 사용 가능 시 실시간 감시, 미설치 환경에서는 polling fallback
  - 스캔 중 변경은 `pending rerun` 1건으로 합쳐지고, 완료 후 증분 재스캔됩니다.
- 삭제 후 빈 폴더 후처리가 실제 실행 경로에 연결되었습니다.
  - 삭제/하드링크 작업 후 비게 된 상위 폴더를 다시 검사하고 별도 operation log로 남깁니다.
- 유사 문서 탐지가 `.txt`, `.md`, `.csv`, `.json`, `.py`, `.pdf`에 대해 활성화되었습니다.
  - `pypdf`가 있으면 PDF 텍스트 기반 SimHash 그룹핑을 수행합니다.
- 당시 이 워크스페이스 기준 자동 회귀 결과:
  - `pytest -q` -> `131 passed, 1 skipped`

- 이전 2026-04-12 변경사항도 유지됩니다.

## 구현 상태 (2026-04-28)

- DB 스키마 버전이 `7`로 확장되었습니다.
  - `scan_file_state` 저장 모델을 추가해 DB 자동 세션 복원도 JSON v3와 같은 수준으로 `file_meta`, 존재 여부, 선택 사유, 예외 상태, 검토 상태, 컬렉션 역할, baseline delta를 복원합니다.
- `pyright src tests cli.py main.py` 기준선을 복구했습니다.
  - core `CacheManager`/`ScanWorker` mixin host protocol과 UI host protocol 누락을 보강했고, `watchdog` optional import는 런타임 fallback을 유지하면서 타입 검사를 통과합니다.
- 결과 그룹 분류가 `src/core/result_groups.py`로 공통화되었습니다.
  - UI badge, CSV `group_type/group_kind`, hardlink eligibility가 같은 classifier를 사용합니다.
  - `NAME_ONLY`, `FOLDER_DUP`, `similar_*`, `doc_similar_*`는 하드링크 통합에서 제외됩니다.
- Safelist / Ignore 정책이 정합화되었습니다.
  - canonical 상태는 `"safelisted"`이며 legacy `"safelist"`는 JSON/DB 로드 시 normalize됩니다.
  - 증분 baseline-known path와 cached-resume scan 경로에도 동일한 ignore/exemption/metadata 복원 정책을 적용합니다.
  - content-hash 예외 규칙은 exact full BLAKE2b hash 기준이며, name-only/similar 계열에서는 content-hash 액션을 비활성화합니다.
- 사용자-facing 관리 기능을 보강했습니다.
  - Tools Safelist/Ignore manager, 결과 트리 우클릭 예외 등록, 폴더 Path/Role 테이블, Session Compare action, 위험도 badge/preflight 요약, `operation_plan` JSON v1 저장/로드, Quarantine 필터/페이지네이션을 추가했습니다.
  - scheduled/watch 이력은 `missing_folders`, `export_failed`, `watch_events` 구조 필드로 분리해 표시합니다.
- CLI 미구현 옵션은 fail-fast 처리합니다.
  - `--watch`, `--post-cleanup-empty-dirs` 지정 시 exit code `2`와 stderr 안내를 반환합니다.
- 패키징/로컬 산출물 정합성을 갱신했습니다.
  - `PyDuplicateFinder.spec`는 새 런타임 helper(`src.core.result_groups`, `src.ui.history_messages`)를 명시 hidden import로 포함하고, `watchdog`/`pypdf`는 설치된 경우에만 수집합니다.
  - `.gitignore`는 로컬 DB sidecar, 결과 CSV/JSON, `operation_plan` JSON, temp 산출물을 무시합니다.
- 현재 이 워크스페이스 기준 자동 회귀 결과:
  - `pyright src tests cli.py main.py` -> `0 errors, 0 warnings`
  - `pytest -q` -> `145 passed`
