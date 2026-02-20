# IMPLEMENTATION_AUDIT.md

작성일: 2026-02-20  
최종 업데이트: 2026-02-20  
대상 프로젝트: `d:\google antigravity\duplicate_finder`  
범위: 기능 구현 리스크 + 추가 필요사항(초기 감사 문서, 이후 이행 현황 갱신 포함)

## 1) Audit Scope & Method

- 참조 문서: `claude.md`, `README.md`, `README_EN.md`
- 참조 코드: `src/core/*`, `src/ui/main_window.py`, `tests/*`
- 점검 방식:
1. 정적 점검(핵심 경로 라인 단위 확인)
2. 테스트 실행 기준선 확인(`pytest -q`)
3. 경계 시나리오 재현(스케줄러 due 판단)

기준선 결과:
- 초기 감사 시점 테스트: `25 passed`
- 현재(이행 반영 후) 테스트: `46 passed`
- 예외 처리 탐지: 저장소 내 광범위 `except` 패턴 약 258건
- 대형 파일: `src/ui/main_window.py` 3079 lines, `src/core/scanner.py` 1177 lines

## 2) 핵심 리스크 (P0/P1)

### P0-1. 스케줄러 최초 실행 시 예약 시각 이전에도 즉시 실행될 수 있음

- 증상:
  - `last_run_at`가 없으면 현재 시간이 예약 슬롯 이전이어도 `is_due=True`가 될 수 있음.
- 영향:
  - 앱 시작 직후 또는 설정 적용 직후, 의도하지 않은 즉시 예약 스캔 실행 가능.
- 근거 라인:
  - `src/core/scheduler.py:48`
  - `src/core/scheduler.py:67`
  - `src/core/scheduler.py:68`
  - `src/ui/main_window.py:2713`
- 재현 조건/관찰:
  - 일간 `23:00`, 현재 `10:00`, `last_run_at=None`에서도 `True` 반환 확인.
- 권고안:
1. `last_run_at is None`일 때는 `compute_next_run` 기준으로 최초 실행 시점을 엄격히 판단.
2. `is_due`에서 "현재 슬롯 도달 여부"와 "초기 부팅 여부"를 분리.
- 테스트안:
1. `test_is_due_first_run_before_time_returns_false`
2. `test_is_due_first_run_after_time_returns_true`
3. `test_is_due_weekly_first_run_before_weekday_time_returns_false`

### P1-1. 예약 실행 로그 `session_id`와 실제 스캔 세션 정합성 불일치 가능

- 증상:
  - 예약 실행 시작 시점의 `session_id`가 스캔 시작 후 생성/갱신된 실제 세션과 다를 수 있음.
- 영향:
  - `scan_job_runs` 감사 추적 시 실행-세션 매핑 혼선.
- 근거 라인:
  - `src/ui/main_window.py:2748`
  - `src/ui/main_window.py:1027`
  - `src/core/cache_manager.py:1467`
- 재현 조건/관찰:
  - 스케줄러 틱에서 run 레코드 생성 후 `start_scan()` 내부에서 세션 결정.
- 권고안:
1. run 생성 시점 연기(세션 확보 후 생성) 또는
2. 실행 중 세션 확정 후 `scan_job_runs.session_id` 업데이트 경로 추가.
- 테스트안:
1. 예약 스캔 통합 테스트에서 run의 `session_id == current_session_id` 검증.

### P1-2. 작업 결과가 "all skipped"여도 `completed`로 기록될 수 있음

- 증상:
  - 실패/성공 모두 비어 있고 skipped만 있는 경우 `completed` 판정 가능.
- 영향:
  - 사용자에게 "성공 완료"로 오인될 수 있고 운영 로그 해석이 어려워짐.
- 근거 라인:
  - `src/core/operation_queue.py:197`
  - `src/core/operation_queue.py:225`
  - `src/core/operation_queue.py:381`
  - `src/core/operation_queue.py:443`
- 재현 조건/관찰:
  - 존재하지 않는 경로만 전달 시 `skipped`만 누적되는 경로 존재.
- 권고안:
1. 상태 판정에 `skipped`를 포함해 `no_effect` 또는 `partial` 상태 도입.
2. 메시지도 "처리됨=0, 건너뜀=N" 형태로 명확화.
- 테스트안:
1. `delete_trash` skipped-only 입력 시 기대 상태 검증.
2. `hardlink_consolidate` cross-volume/missing-only 입력 시 기대 상태 검증.

### P1-3. 복구(restore) 예외 시 operation item 로그 누락 가능

- 증상:
  - `restore` 루프에서 예외 발생 시 `res.failed`는 기록되지만 `items_batch` 누락 가능.
- 영향:
  - 작업 상세 감사 로그에서 실패 항목 누락(추적성 저하).
- 근거 라인:
  - `src/core/operation_queue.py:272`
  - `src/core/operation_queue.py:288`
- 재현 조건/관찰:
  - `except` 분기에서 `items_batch.append(...)`가 수행되지 않는 경로 존재.
- 권고안:
1. `except` 분기에도 최소한의 실패 row를 `items_batch`에 적재.
2. 실패 row에 `item_id`, reason(예외 문자열), 타임스탬프 보존.
- 테스트안:
1. `cache_manager.get_quarantine_item` 예외 모킹 시 operation items에 fail row 생성 검증.

## 3) 중요 개선 항목 (P2)

### P2-1. `HistoryManager` 취소 상태 반영 누락 가능성

- 증상:
  - `_delete_to_quarantine` 경로에서 `cancelled` 플래그가 갱신되지 않음.
- 영향:
  - 부분 취소/중단 상황에서 메시지/상태가 실제와 다를 수 있음.
- 근거 라인:
  - `src/core/history.py:151`
  - `src/core/history.py:153`
  - `src/core/history.py:191`
- 권고안:
1. `move_to_quarantine` 결과와 입력 개수 비교 또는 취소 콜백 결과를 통해 `cancelled` 반영.
- 테스트안:
1. `check_cancel`이 중간에 True를 반환하는 케이스에서 취소 메시지 검증.

### P2-2. 캐시 재사용 스캔 경로에서 `follow_symlinks` 일관성 부족

- 증상:
  - `_scan_files_from_cache`의 `os.stat(path)`는 `follow_symlinks` 옵션을 직접 반영하지 않음.
- 영향:
  - 일반 스캔 경로와 캐시 경로 간 동작 차이 가능성.
- 근거 라인:
  - `src/core/scanner.py:626`
  - 비교 기준: `src/core/scanner.py:519`
- 권고안:
1. 캐시 경로도 `os.stat(path, follow_symlinks=self.follow_symlinks)`로 통일.
- 테스트안:
1. 심볼릭 링크 포함 세션에서 캐시 재개/신규 스캔 결과 일치성 검증.

### P2-3. 광범위 예외 처리로 진단 가능성 저하

- 증상:
  - 예외를 포괄적으로 삼키는 패턴이 다수.
- 영향:
  - 실제 오류 원인 추적 난이도 상승, 잠재 회귀 조기 탐지 어려움.
- 근거 라인:
  - 저장소 탐지 기준 약 258건
  - 집중 구간: `src/ui/main_window.py` (3079 lines)
- 권고안:
1. 사용자 무해 구간/핵심 로직 구간 예외 정책 분리.
2. 핵심 경로(`scheduler`, `operation_queue`, `cache_manager`)부터 구조화 로깅 도입.
- 테스트안:
1. 실패 주입 테스트에서 오류 코드/메시지/로그 일관성 검증.

## 4) 문서/구현 드리프트

### D-1. 자동 정리 설명과 현재 격리(Quarantine) 구조 간 표현 불일치 가능

- 증상:
  - README/컨텍스트 문서는 `atexit` 기반 임시 폴더 정리를 강조.
  - 실제 구현은 persistent quarantine를 중심으로 동작.
- 영향:
  - 사용자가 "종료 시 자동 삭제"로 오해할 가능성.
- 근거 라인:
  - `README.md:24`
  - `README_EN.md:24`
  - `claude.md:88`
  - `src/core/quarantine_manager.py:37`
  - `src/core/history.py:33`
- 권고안:
1. README/컨텍스트 문서에 "persistent quarantine" 동작을 명시.
2. 임시 정리와 영구 격리의 경계를 분리 설명.
- 테스트안:
1. 앱 재시작 후 격리 항목 유지 여부를 수동 검증 절차로 문서화.

### D-2. `FEATURE_IDEAS.md`와 구현 상태 시점 불일치 위험

- 증상:
  - 아이디어 문서의 일부 항목은 구현 완료/미구현 상태가 시점에 따라 어긋날 수 있음.
- 영향:
  - 우선순위/백로그 관리 왜곡 가능.
- 근거:
  - 구현 상태 요약은 `README.md` 기준 최신 반영.
  - 별도 아이디어 문서는 정기 동기화 규칙 부재.
- 권고안:
1. "구현 상태 소스 오브 트루스"를 `README` 또는 별도 changelog로 단일화.
2. 아이디어 문서에 "last verified date" 추가.
- 테스트안:
1. 릴리스 체크리스트에 문서 정합성 점검 항목 추가.

## 5) 추가해야 할 테스트/보강 항목

1. 스케줄러 경계 테스트
- `scheduler.is_due` 최초 실행/예약 이전/주간 경계 케이스 추가.

2. 작업 상태 판정 테스트
- `operation_queue`의 skipped-only 케이스 상태/메시지 검증.

3. 예약 스캔 통합 테스트
- `_scheduler_tick -> start_scan -> scan_job_runs` 세션/상태 정합성 검증.

4. 수동 검증 스크립트 정규화
- `tests/verify_*.py`를 pytest 편입 또는 명시적 수동 검증 문서로 분리.

## 6) 실행 가능한 개선 백로그

### 단기(즉시)

1. 스케줄러 due 로직 보정(P0)
2. skipped-only 상태 판정 보정(P1)
3. restore 예외 시 operation item 로깅 보강(P1)
4. 예약 run/session_id 정합성 보강(P1)

### 중기

1. 예외 처리 표준화(코드/메시지/로깅)
2. 스케줄러/작업큐/예약 플로우 통합 테스트 확대
3. 문서 정합성 릴리스 게이트 도입

### 장기

1. `main_window` 오케스트레이션 추가 분리(컨트롤러 확장) [진행: 2차 분리 반영]
2. 핵심 코어 경로의 오류 코드 기반 인터페이스 정리

## 7) 즉시 수행 순서 (Top 5)

1. `scheduler.is_due` 최초 실행 판정 수정 + 테스트 3종 추가
2. `operation_queue` skipped-only 상태 모델 정의(`no_effect` 또는 `partial`) + 테스트
3. `restore` 예외 시 operation item fail row 강제 기록
4. 예약 run 생성 시점/세션 매핑 정합성 수정 + 통합 테스트
5. README/컨텍스트 문서의 quarantine/자동정리 설명 동기화

## 8) 가정 및 기본값

- 언어: 한국어
- 범위: 버그+개선 종합
- 초기 작성 시점 기준으로는 분석/권고 문서이며 코드 변경은 포함하지 않았음
- 라인 참조는 작성 시점 워크트리 기준

## 9) 후속 이행 현황 (2026-02-20)

- 구조 분해 2차 반영:
1. `src/ui/controllers/operation_flow_controller.py` 추가(작업 큐/진행/완료 처리 분리)
2. `src/ui/controllers/navigation_controller.py` 추가(사이드바 네비게이션 분리)
3. `src/ui/main_window.py`의 `_enqueue_operations`, `_start_operation`, `_on_op_finished`, `_on_page_changed` 등을 컨트롤러 위임 구조로 전환
- 테스트 보강:
1. `tests/test_operation_flow_controller.py` 추가
2. `tests/test_navigation_controller.py` 추가
3. 전체 테스트 `46 passed` 확인
