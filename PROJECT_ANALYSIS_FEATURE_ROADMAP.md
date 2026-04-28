# PyDuplicate Finder Pro 프로젝트 분석 및 기능 확장 로드맵

작성일: 2026-04-14
최종 갱신: 2026-04-28

참조 문서:
- `README.md`
- `claude.md`
- `gemini.md`
- `tests/MANUAL_VERIFY.md`
- 실제 소스 트리(`src/`, `tests/`) 직접 분석

## 1. 분석 목적

이 문서는 현재 `PyDuplicate Finder Pro`의 구조와 설계 의도를 정리하고, 앞으로 "중복 파일 제거 및 관련 기능"을 어떤 방향으로 확장하면 좋은지 실무 관점에서 제안하기 위해 작성했다.

핵심 관점은 아래 3가지다.

1. 현재 구조가 어떤 기능 추가에 강한지
2. 어떤 영역이 이미 잘 분리되어 있어 확장이 쉬운지
3. 어떤 기능부터 추가해야 제품 가치가 가장 빨리 커지는지

## 2. 코드베이스 스냅샷

분석 시점 기준 대략적인 규모:

| 구분 | 파일 수 | 라인 수 |
|---|---:|---:|
| `src/` 전체 | 122 | 14,899 |
| `tests/` 전체 | 44 | 2,653 |
| `src/core/` | 33 | 5,035 |
| `src/ui/` | 83 | 8,989 |
| `src/utils/` | 5 | 875 |
| `src/core/scanner/` | 11 | 1,379 |
| `src/core/cache_manager/` | 9 | 1,560 |
| `src/ui/main_window_parts/` | 44 | 3,755 |

해석:

- 제품의 중심은 스캔 엔진이지만, 실제 코드 비중은 `UI orchestration`이 더 크다.
- 즉 "새 기능을 추가하는 일"은 단순히 코어 알고리즘만 고치는 일이 아니라,
  `스캔 옵션 -> UI 노출 -> 저장/복원 -> 결과 렌더링 -> export -> 테스트`
  까지 한 세트로 봐야 한다.

## 3. 현재 아키텍처 요약

### 3.1 진입점

- `main.py`
  - GUI 실행 진입점
  - 전역 예외 훅 설정
  - `DuplicateFinderApp` 초기화
- `cli.py`
  - 헤드리스 스캔 진입점
  - GUI 없이 스캔/JSON/CSV 출력 가능
  - GUI와 동일한 `ScanConfig`, `ScanWorker` 파이프라인을 재사용

### 3.2 Core 레이어

`src/core/`는 제품의 실질적인 도메인 로직이다.

핵심 모듈:

- `scanner/`
  - 파일 수집
  - 해시 계산
  - 증분 스캔
  - 유사 이미지 스캔
  - 중복 폴더 탐지
  - 진행률/텔레메트리/취소 처리
- `cache_manager/`
  - SQLite 기반 영구 캐시
  - 세션, 해시, 결과, 선택 상태, 격리함, 작업 로그, 예약 작업 저장
- `operation_queue.py`
  - 삭제/복구/하드링크/Undo/Redo 실행 워커
- `preflight.py`
  - 위험 작업 전 검증
- `quarantine_manager.py`
  - 안전한 삭제 및 복구
- `history.py`
  - Undo/Redo 메모리 스택
- `scheduler.py`
  - daily/weekly 예약 실행 판단
- `selection_rules.py`
  - KEEP/DELETE 규칙 판정
- `result_schema.py`
  - JSON 결과 v3 스키마 및 legacy / v2 / v3 호환
- `preset_manager.py`
  - 스캔 설정 프리셋
- `empty_folder_finder.py`
  - 빈 폴더 탐색/삭제

### 3.3 UI 레이어

`src/ui/`는 화면, 상호작용, 컨트롤러, 페이지, 다이얼로그로 구성된다.

핵심 구조:

- `main_window.py`
  - 조립/호환 레이어
- `main_window_parts/`
  - `scan_flow`, `results_flow`, `settings_flow`, `tools_flow`, `ui_shell`, `schedule_flow`
  - 현재 기능 대부분이 여기서 오케스트레이션됨
- `controllers/`
  - scan / results / preview / scheduler / ops / navigation / operation_flow 책임 분리
- `pages/`
  - Scan / Results / Tools / Insights / Settings 페이지 빌드
- `components/results_tree/`
  - 대량 결과 표시용 핵심 위젯
- `dialogs/`
  - preset, rules, preflight, operation log, session compare, shortcut 등

### 3.4 지원 레이어

- `src/utils/i18n/`
  - 한국어/영어 카탈로그
- `PyDuplicateFinder.spec`
  - PyInstaller 패키징
- `tests/`
  - 기능 회귀 + 성능 + 공개 API 안정성 + 인코딩 무결성

## 4. 현재 제품 기능 정리

이미 구현된 기능 범위가 꽤 넓다.

### 스캔/분석

- 내용 해시 기반 중복 파일 탐지
- 파일명 기반 탐지
- 바이트 단위 재검증
- 유사 이미지 탐지
- mixed mode
- 중복 폴더 탐지
- 증분 재스캔 + baseline 세션
- 보호 경로 제외
- include/exclude 패턴
- hidden/system/symlink 정책
- strict mode + metrics/warnings

### 안전한 정리

- quarantine 기반 삭제/복구
- system trash 삭제
- file lock 검사
- preflight 확인
- operation log
- Undo/Redo
- hardlink consolidation

### UX/운영

- 결과 JSON/CSV export
- 프리셋 저장/로드
- 예약 스캔
- 세션 복원
- 미리보기
- 다국어
- 테마
- 단축키
- 빈 폴더 찾기

결론적으로 이 프로젝트는 "중복 파일 찾기" 수준을 이미 넘어섰고, 지금부터는
"더 똑똑하게 고르기", "더 안전하게 정리하기", "더 잘 운영하기"
방향으로 기능을 쌓는 것이 맞다.

## 5. 구조적 강점

### 5.1 확장성 좋은 지점

- 스캔 옵션이 `ScanConfig`로 정리되어 있어 새 스캔 모드 추가가 비교적 명확하다.
- `scanner/`가 mixin 단위로 분리되어 있어 알고리즘 추가 시 파일 책임 경계가 있다.
- `cache_manager/`가 schema/session/jobs/quarantine 등으로 나뉘어 있어 저장 모델 확장이 가능하다.
- destructive action이 `Preflight -> Operation -> OperationLog -> Quarantine` 흐름으로 표준화돼 있다.
- GUI와 CLI가 scan config/worker를 공유하므로 자동화 기능을 붙이기 좋다.
- 테스트가 공개 facade, 성능, 스키마 호환까지 커버하고 있어 리팩터링 방어력이 있다.

### 5.2 제품적으로 좋은 지점

- "안전"을 제품 핵심 가치로 잡고 있다.
- 유사 이미지, 증분 스캔, 스케줄러까지 이미 있어 고급 사용자에게 매력적이다.
- `operation log`, `quarantine`, `preflight`가 있어 향후 기업형/전문가형 기능으로 확장 가능하다.

## 6. 현재 제약과 주의점

### 6.1 기능 추가 시 동기화해야 할 면이 많다

새 필터/모드를 추가하면 대개 아래를 함께 수정해야 한다.

- `src/core/scan_engine.py`
- `src/core/scanner/*`
- `cli.py`
- `src/ui/pages/scan_page.py`
- `src/ui/main_window_parts/scan_flow/legacy.py`
- `src/ui/main_window_parts/settings_flow/legacy.py`
- `src/core/preset_manager.py`
- `src/core/result_schema.py`
- `src/ui/exporting.py`
- i18n catalog
- tests

즉, 이 프로젝트에서 기능 추가는 "한 파일 수정"으로 끝나지 않는 경우가 많다.

### 6.2 여전히 큰 legacy mixin이 남아 있다

`main_window_parts/*/legacy.py`는 예전 거대한 `main_window`를 단계적으로 분해한 결과물이다.

좋은 점:
- 호환성 유지
- 빠른 기능 추가 가능

아쉬운 점:
- 신규 기능을 급하게 넣으면 다시 거대 mixin으로 회귀할 위험이 있다.

원칙:
- 새 기능은 가능하면 `controller`, `core service`, `dialog`, `component`로 분리하고
  `legacy.py`에는 배선만 남기는 편이 좋다.

### 6.3 예약 스캔은 아직 단일 job 구조다

초기 분석 시점에는 `scan_jobs`가 사실상 `"default"` 1개 중심이었지만, 현재 구현은 다중 named job 기준으로 확장되었다.

이 말은 곧:
- 여러 프로필 예약 실행
- 폴더 세트별 스케줄
- 다른 output 정책

같은 기능은 아직 구조적으로 확장 여지가 남아 있다는 뜻이다.

### 6.4 빈 폴더 기능은 도구로 잘 분리되어 있지만 독립적이다

`empty_folder_dialog.py` + `empty_folder_finder.py`는 분리 상태는 좋지만,
현재 전체 operation logging / safety 체계와 완전히 통합된 느낌은 아니다.

즉, 여기는 비교적 작은 노력으로 체감 기능을 크게 늘릴 수 있는 영역이다.

## 7. 기능 확장 방향 제안

아래는 "추가하면 실제로 유용하고, 현재 구조에도 잘 맞는 기능" 위주로 정리한 우선순위 제안이다.

### 7.1 1순위: 바로 제품 가치가 커지는 기능

| 기능 | 사용자 가치 | 난이도 | 주요 수정 위치 |
|---|---|---|---|
| 보존 우선순위 정책 | 어느 파일을 남길지 더 똑똑하게 결정 | 중 | `results_controller.py`, `selection_rules.py`, `results_page.py`, `selection_rules_dialog.py` |
| Safelist / Ignore list | "이 파일은 다시 후보로 보지 않기" | 중 | `cache_manager/schema.py`, `scanner/*`, `tools_page.py`, `result_schema.py` |
| 세션 비교 뷰 | 이전 스캔 대비 신규/변경/재검증 차이를 UI로 확인 | 중 | `scanner/incremental.py`, `results_flow`, `exporting.py`, 새 dialog/page |
| 루트 우선 보존 정책 | `D:`는 원본, `E:`는 백업처럼 정리 | 중 | `selection_rules.py`, `results_controller.py`, scan/settings UI |
| 결과 위험도/추천 점수 | 삭제 추천 신뢰도를 눈으로 확인 | 중 | `results_tree/*`, `results_controller.py`, `exporting.py` |

#### 추천 상세

1. 보존 우선순위 정책
   - 현재는 smart/newest/oldest/pattern/rules 정도다.
   - 확장안:
     - "짧은 경로 우선 보존"
     - "사용자 지정 루트 우선"
     - "특정 확장자 우선"
     - "최근 수정 파일 보존"
     - "읽기 전용/시스템 속성 파일 보존"
   - 이 기능은 실제 삭제 정확도를 크게 올린다.

2. Safelist / Ignore list
   - 사용자가 한 번 "이 파일은 원본"이라고 판단한 뒤 다시 매번 체크하는 것은 비효율적이다.
   - path 기반과 hash 기반 두 가지를 두는 것이 좋다.
   - 특히 hash 기반 safelist는 파일이 이동돼도 유효하다.

3. 세션 비교 뷰
   - 이미 `baseline_delta_map(new|changed|revalidated)`가 있으므로 데이터 토대는 있다.
   - 지금은 CSV에만 드러나는 정보를 UI에 올리는 작업이 우선이다.
   - "지난 스캔 이후 새로 생긴 중복만 보기"는 매우 유용하다.

### 7.2 2순위: 정리 도구를 제품답게 만드는 기능

| 기능 | 사용자 가치 | 난이도 | 주요 수정 위치 |
|---|---|---|---|
| 컬렉션 비교 모드 | 원본 폴더 vs 백업 폴더 비교/정리 | 중상 | `ScanConfig`, `scanner/*`, `results_controller.py`, UI/CLI |
| 폴더 병합 마법사 | 중복 폴더 그룹을 실제 병합/정리 | 상 | `folder_duplicates.py`, `operation_queue.py`, `preflight.py`, 새 dialog |
| 검토 상태 태깅 | 나중에 다시 볼 그룹 표시 | 중 | DB schema, results tree, tools page |
| 작업 계획 시뮬레이터 | 삭제 전 예상 결과를 더 구체적으로 표시 | 중 | `preflight.py`, `results_flow`, `operation_log_dialog.py` |
| 빈 폴더 후처리 통합 | 삭제 후 새로 비게 된 폴더 자동 정리 | 중 | `empty_folder_finder.py`, `operation_flow_controller.py`, tools UI |

#### 추천 상세

1. 컬렉션 비교 모드
   - 예: `원본 사진 폴더`와 `외장 백업 폴더`를 비교해서 "백업 쪽에만 있는 중복"만 정리
   - 일반 중복 탐지보다 사용 시나리오가 더 명확하다.
   - 스캔 루트를 그룹 개념으로 취급하는 모델이 필요하다.

2. 폴더 병합 마법사
   - 현재는 중복 폴더를 "찾는 것"은 가능하지만, 실제 병합 UX는 약하다.
   - 병합 전 preview가 필요하다.
   - 충돌 파일 처리 전략:
     - skip
     - rename
     - keep newer
     - quarantine moved files

3. 빈 폴더 후처리 통합
   - 실제 사용자 흐름은 "중복 삭제 -> 빈 폴더 발생 -> 후처리 정리"다.
   - 지금은 별도 도구이므로 흐름이 끊긴다.
   - 삭제 완료 후 "새로 빈 폴더가 된 경로 탐지" 옵션은 체감 가치가 높다.

### 7.3 3순위: 고급 사용자/장기 로드맵용 기능

| 기능 | 가치 | 난이도 | 비고 |
|---|---|---|---|
| 폴더 병합 마법사 | 중복 폴더 그룹 병합/충돌 해결 | 상 | preview와 충돌 전략 필요 |
| 아카이브 내부 스캔 | zip 내부까지 분석 | 상 | 성능/UX 복잡도 큼 |
| 리포트 대시보드 확장 | 용량 절감 추이, 작업 이력 분석 | 중상 | 현재 Insights를 확장하는 방향 |

1순위와 2순위의 핵심 안전 기능은 2026-04-28 기준 대부분 구현되었으므로, 이후에는 폴더 병합/아카이브 스캔처럼 더 큰 UX 설계가 필요한 기능을 별도 단계로 다루는 편이 낫다.

### 7.4 구현 상태 메모 (2026-04-28 업데이트)

이 문서의 초안 이후 아래 항목은 실제 코드에 반영되었다.

- 선택 정책 파이프라인 통합
  - 명시 규칙 -> safelist -> 컬렉션 우선순위 -> 속성 우선순위 -> fallback keep-one
- 예외 규칙/검토 상태 저장 및 관리
  - `scan_exemptions`, `review_marks`, `file_signatures`, `scan_file_state`
  - DB schema `v7`, 결과 JSON `version=3`, CSV export 반영
  - Tools Safelist/Ignore manager와 결과 트리 우클릭 예외 등록 액션 추가
- 결과 그룹 안전 분류
  - `src/core/result_groups.py` 공통 classifier 추가
  - UI badge, CSV `group_type/group_kind`, hardlink eligibility 정합화
  - `NAME_ONLY`, `FOLDER_DUP`, `similar_*`, `doc_similar_*` hardlink 차단
- Results 증분 검토 UX
  - delta filter(`new`, `changed`, `revalidated`)
  - `Session Compare` 다이얼로그의 결과 선택, bulk review mark, CSV export 액션
- 컬렉션 비교 모드
  - 폴더 선택 UI를 Path/Role 테이블로 교체
  - `primary` / `secondary` / `none` 역할을 설정, 프리셋, 예약 job snapshot에 반영
- 작업 계획/위험도/격리함 UX
  - `operation_plan` JSON v1 저장/불러오기와 path/size/mtime 검증
  - 결과 그룹 위험도 badge와 destructive preflight 위험도 요약
  - Quarantine status/date/size/path 필터와 pagination
  - scheduled/watch 이력의 `missing_folders`, `export_failed`, `watch_events` 구조 컬럼 표시
- 패키징/로컬 산출물 정합성
  - `PyDuplicateFinder.spec`에 `src.core.result_groups`, `src.ui.history_messages` hidden import 명시
  - 선택 의존성 `watchdog`/`pypdf`는 설치된 경우에만 collect하도록 조정
  - `.gitignore`에 로컬 DB sidecar, 결과 CSV/JSON, `operation_plan` JSON, temp 산출물 패턴 추가
- 다중 예약 작업 UI, watch mode, 삭제 후 빈 폴더 후처리, Similar-document 탐지, Insights 페이지는 2026-04-14 업데이트의 구현 상태를 유지한다.

현재 자동 회귀 기준선:

- `pyright src tests cli.py main.py` -> `0 errors, 0 warnings`
- `pytest -q` -> `145 passed`

## 8. 기존 추천 기능의 현재 상태

2026-04-14 초안에서 가장 효율이 좋다고 판단한 기능들의 2026-04-28 상태:

| 기능 | 현재 상태 |
|---|---|
| Safelist / Ignore list | 구현됨: Tools 관리 UI, 결과 트리 우클릭 등록, JSON/DB 호환 normalize |
| 보존 우선순위 정책 확장 | 구현됨: selection policy pipeline과 collection role 기반 보존 |
| 증분 스캔 결과 UI 노출 | 구현됨: delta filter와 Session Compare 액션 |
| 컬렉션 비교 모드 | 구현됨: Path/Role 테이블, preset/settings/scheduled snapshot 반영 |
| 빈 폴더 후처리 자동화 | 구현됨: 삭제/하드링크 후 operation flow에 연결 |

이 순서를 추천했던 이유:

- 기존 구조를 크게 깨지 않는다.
- 사용자 체감이 바로 난다.
- 파괴적 작업의 안전 모델과 잘 맞는다.
- 테스트 작성 포인트가 명확하다.

## 9. 기능별 구현 진입점

### 9.1 새 스캔 모드 추가

수정 후보:

- `src/core/scan_engine.py`
- `src/core/scanner/worker.py`
- 관련 mixin (`discovery.py`, `hashing.py`, `incremental.py`, `folder_duplicates.py`, `similar_images.py`)
- `cli.py`
- `src/ui/pages/scan_page.py`
- `src/ui/main_window_parts/scan_flow/legacy.py`
- `src/ui/main_window_parts/settings_flow/legacy.py`
- `src/core/preset_manager.py`

### 9.2 새 결과 메타데이터 추가

수정 후보:

- `src/core/result_schema.py`
- `src/ui/exporting.py`
- `src/ui/components/results_tree/*`
- `src/ui/main_window_parts/results_flow/legacy.py`

### 9.3 새 정리 작업 추가

수정 후보:

- `src/core/preflight.py`
- `src/core/operation_queue.py`
- `src/core/history.py`
- `src/core/quarantine_manager.py`
- `src/ui/dialogs/preflight_dialog.py`
- `src/ui/dialogs/operation_log_dialog.py`
- `src/ui/main_window_parts/tools_flow/legacy.py`

### 9.4 새 저장 모델 추가

수정 후보:

- `src/core/cache_manager/schema.py`
- 관련 저장 mixin (`sessions.py`, `operations.py`, `quarantine.py`, `jobs.py`, `scan_storage.py`)
- schema migration 테스트

## 10. 기능 추가 시 지켜야 할 개발 원칙

이 프로젝트는 이미 일관된 규칙이 있다. 기능을 늘릴수록 더 엄격히 지켜야 한다.

1. Core는 UI에 의존하지 않기
   - `src/core`는 `QtWidgets`에 기대지 않는 방향 유지

2. 파괴적 작업은 반드시 안전 흐름 따르기
   - `Preflight -> OperationWorker -> Log -> Undo/Quarantine`

3. 새 UI 텍스트는 i18n 키로 넣기
   - 하드코딩 금지

4. 결과 포맷/캐시 스키마 변경 시 하위 호환 고려
   - `result_schema.py`
   - `cache_manager/schema.py`

5. 새 기능은 CLI/GUI 중 하나에만 고립시키지 않기
   - 가능하면 둘 다 지원

6. `legacy.py`에 기능을 직접 과도하게 쌓지 않기
   - 새 기능은 helper/controller/service 분리 우선

## 11. 현재 검증 상태

현재 기준:

1. 정적 타입 검사
   - `pyright src tests cli.py main.py` -> `0 errors, 0 warnings`

2. 워크스페이스 로컬 temp 경로를 사용한 전체 회귀
   - `pytest -q` -> `145 passed`

즉, 2026-04-28 기준으로 기능 안정화 범위의 정적 타입 검사와 전체 회귀 테스트가 모두 통과한다.

## 12. 결론

이 프로젝트는 이미 "중복 파일 탐색기"를 넘어서
"안전한 정리 도구 + 운영 도구 + 고급 스캔 플랫폼"
성격을 갖고 있다.

따라서 앞으로의 확장 방향은 아래가 가장 적절하다.

1. 더 많이 찾는 것보다 더 잘 고르게 만들기
2. 삭제보다 검토와 시뮬레이션을 강화하기
3. 세션/이력/정책을 누적해서 점점 자동화하기

2026-04-28 안정화 작업으로 `Safelist / Ignore list`, 증분 결과 UI, 컬렉션 역할, 작업 계획 저장, 위험도 표시, Quarantine 필터링은 구현되었다.

가장 현실적인 다음 작업은 아래 둘이다.

- A안: 폴더 병합 마법사 설계 및 preview/충돌 전략 구현
- B안: 대규모 결과 UX를 더 가볍게 만들기 위한 결과 테이블/가상화 개선

둘 다 현재 구조와 궁합이 좋지만, 파괴적 작업이 포함되는 A안은 preflight/operation log/undo 모델을 먼저 더 구체화한 뒤 진행하는 편이 안전하다.

