# 🔍 PyDuplicate Finder Pro

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README_EN.md)

**PyDuplicate Finder Pro**는 파이썬(PySide6) 기반의 고성능 중복 파일 관리 도구입니다. 최신 멀티스레딩 기술과 스마트 캐싱을 통해 대용량 파일 시스템에서도 빠르고 정확하게 중복 파일을 탐색하며, 안전한 삭제 복구(Undo) 기능을 제공합니다.

---

## ✨ 주요 기능 (Key Features)

### 🚀 압도적인 성능 (High Performance)
- **초고속 스캔 (Fast I/O)**: `os.scandir` 기반의 재귀 스캔 엔진을 도입하여 기존 `os.walk` 대비 파일 탐색 속도를 비약적으로 향상시켰습니다.
- **최적화된 해싱 (BLAKE2b)**: 64비트 시스템에 최적화된 `BLAKE2b` 알고리즘을 사용하여 MD5보다 빠르고 안전하게 파일을 분석합니다.
- **스마트 캐싱 & 배치 처리**: `SQLite WAL` 모드와 대용량 배치(Batch) 처리를 통해 수십만 개의 파일도 끊김 없이 처리합니다.
- **중단 복구 (Resume Scan)**: 파일 목록/해시 진행 상태를 캐시에 저장하여, 재실행 시 중단된 지점부터 이어서 스캔할 수 있습니다.
- **부드러운 UI**: 결과 목록을 점진적으로 렌더링(Incremental Rendering)하여 대량의 결과 표시 중에도 앱이 멈추지 않습니다.

### 🛡️ 안전 및 정밀성 (Safety & Precision)
- **시스템 보호 (System Protection)**: Windows/Linux의 주요 시스템 폴더(Windows, Program Files 등)를 자동으로 건너뛰어 오작동을 방지합니다.
- **물리적 중복 방지 (Inode Check)**: 심볼릭 링크나 바로가기 등으로 인해 동일한 물리적 파일이 중복 집계되는 것을 원천 차단합니다.
- **안전한 삭제 & 실행 취소 (Robust Undo)**: 비동기 방식의 '삭제/복구' 작업을 지원하여, 대량의 파일을 삭제할 때도 UI가 멈추지 않습니다.
- **휴지통 옵션**: 파일을 영구 삭제하는 대신 시스템 휴지통으로 이동시켜 안전하게 복구할 수 있는 옵션을 제공합니다.
- **파일 잠금 감지**: 삭제 전 다른 프로세스에서 사용 중인 파일을 자동으로 감지하여 오류를 방지합니다.
- **격리함 유지/보존 정책**: Undo 가능한 삭제는 persistent 격리함에 보관되며, 설정한 보존 기간/용량 정책에 따라 정리됩니다.

### 🎨 모던 UI & 사용자 경험
- **다양한 스캔 모드**: 
    - **유사 이미지 탐지 (pHash + BK-Tree)**: **BK-Tree** 알고리즘을 도입하여 수천 장의 이미지도 $O(N \log N)$ 속도로 순식간에 분석합니다. 시각적으로 비슷한 이미지(리사이즈, 변형 등)를 찾아냅니다.
    - **파일명 비교**: 파일 내용은 다르더라도 이름이 같은 파일들을 빠르게 찾아냅니다.
- **제외 패턴 (Exclude Patterns)**: `node_modules`, `.git`, `*.tmp` 등 원하지 않는 폴더나 파일을 스캔에서 제외할 수 있습니다.
- **스캔 프리셋**: 자주 사용하는 스캔 설정(유사 이미지 모드, 특정 확장자 등)을 프리셋으로 저장하고 불러올 수 있습니다.
- **결과 저장/로드**: 긴 시간 스캔한 결과를 JSON 파일로 저장했다가 나중에 다시 열어볼 수 있습니다.
  - 신규 저장은 `version=2` 공통 스키마를 사용하며, 로더는 legacy GUI/CLI 포맷도 자동 호환합니다.
- **자동 세션 복원**: 마지막 스캔 세션을 자동 감지하고 재개/새 스캔 여부를 선택할 수 있습니다.
- **직관적인 트리 뷰**: 결과 트리를 전체 펼치거나 접을 수 있으며, 우클릭 메뉴로 다양한 작업을 수행합니다.
- **실시간 결과 필터**: 이름/경로 기준으로 결과를 빠르게 필터링할 수 있습니다.
- **사이드바 네비게이션**: 스캔/결과/도구/설정 화면을 빠르게 이동할 수 있습니다.
- **커스텀 단축키**: 사용자 편의에 맞춰 모든 기능의 단축키를 설정할 수 있습니다.
- **다국어 지원**: 한국어/영어 인터페이스를 지원합니다.

### 🧰 도구 (Tools)
- **격리함(Quarantine) 관리**: Undo 가능한 삭제 모드로 삭제된 파일을 격리함에서 복구/영구삭제할 수 있습니다.
- **자동 선택 규칙(Selection Rules)**: 경로/파일명 패턴(fnmatch) 기반으로 KEEP/DELETE 규칙을 정의하고 그룹/전체 결과에 자동 적용할 수 있습니다.
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
├── claude.md                # AI 컨텍스트 (Claude)
├── gemini.md                # AI 컨텍스트 (Gemini)
├── src/
│   ├── core/                # 비즈니스 로직 (UI 독립)
│   │   ├── scanner.py           # 멀티스레드 스캔 엔진
│   │   ├── cache_manager.py     # SQLite 캐시 관리
│   │   ├── history.py           # Undo/Redo 트랜잭션
│   │   ├── result_schema.py     # 결과 JSON v2 스키마/호환 로더
│   │   ├── image_hash.py        # 유사 이미지 탐지 (pHash)
│   │   ├── file_lock_checker.py # 파일 잠금 감지
│   │   ├── preset_manager.py    # 스캔 프리셋 관리
│   │   └── empty_folder_finder.py # 빈 폴더 탐색
│   ├── ui/                  # GUI 레이어
│   │   ├── main_window.py       # 메인 윈도우
│   │   ├── theme.py             # 테마 스타일시트
│   │   ├── empty_folder_dialog.py
│   │   ├── controllers/         # UI 오케스트레이션 컨트롤러
│   │   │   ├── scan_controller.py
│   │   │   ├── scheduler_controller.py
│   │   │   ├── ops_controller.py
│   │   │   ├── operation_flow_controller.py
│   │   │   └── navigation_controller.py
│   │   ├── components/
│   │   │   ├── results_tree.py  # 결과 트리 위젯
│   │   │   ├── sidebar.py       # 사이드바 네비게이션
│   │   │   └── toast.py         # 토스트 알림
│   │   ├── pages/
│   │   │   ├── scan_page.py      # 스캔 페이지(UI)
│   │   │   ├── results_page.py   # 결과 페이지(UI)
│   │   │   ├── tools_page.py     # 도구 페이지(UI)
│   │   │   └── settings_page.py  # 설정 페이지(UI)
│   │   └── dialogs/
│   │       ├── preset_dialog.py
│   │       ├── exclude_patterns_dialog.py
│   │       ├── selection_rules_dialog.py
│   │       ├── preflight_dialog.py
│   │       └── operation_log_dialog.py
│   │       └── shortcut_settings_dialog.py
│   └── utils/
│       └── i18n.py              # 다국어 문자열 관리
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

### (선택) CLI로 스캔 실행
```bash
python cli.py "D:/Data" "E:/Photos" --extensions jpg,png --output-json result.json --output-csv result.csv
```
- `--similarity-threshold` 값은 `0.0`~`1.0`만 허용됩니다. 범위를 벗어나면 CLI는 에러(`SystemExit 2`)로 종료됩니다.
- `--similar-image` 또는 `--mixed-mode` 사용 시 `imagehash`/`Pillow` 의존성이 없으면 CLI는 즉시 실패(fail-fast)합니다.

### 2. 검색 설정
- **파일 위치 추가**: '폴더 추가' 혹은 드래그 앤 드롭으로 검색할 위치를 등록합니다.
- **필터 옵션**:
    | 옵션 | 설명 |
    |------|------|
    | 파일명만 비교 | 내용 해시 없이 이름만 비교 (초고속) |
    | 내용+파일명 모두 일치 | 해시가 같고 파일명도 같은 경우만 그룹화 |
    | 바이트 단위 정밀 비교 | 해시가 같은 후보를 바이트 단위로 재검증 |
    | 유사 이미지 탐지 | 시각적 유사성 분석 (0.1~1.0 임계값) |
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
| 자동 선택 규칙 | 패턴 기반 KEEP/DELETE 규칙으로 자동 선택 |
| 작업 기록 | 삭제/복구/정리/하드링크 작업 기록 및 내보내기 |
| 하드링크 통합 | (고급) 중복 파일을 하드링크로 통합하여 공간 절감 |
| 예약 스캔 스냅샷 | 저장된 예약 설정(`scan_jobs.config_json`)으로 실행되며, 폴더 일부 누락 시 유효 폴더만 실행/전체 누락 시 `skipped(no_valid_folders)` 처리 |
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
- 결과 JSON 스키마 통합: GUI/CLI 저장은 `version=2` 포맷 사용, 로더는 legacy GUI/legacy CLI/v2를 모두 수용
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

- `src/core/scanner.py` 본문 로직의 추가 분해(엔진 완전 분리)
- `src/ui/main_window.py` 대규모 오케스트레이션의 컨트롤러 레벨 분리 확대

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
