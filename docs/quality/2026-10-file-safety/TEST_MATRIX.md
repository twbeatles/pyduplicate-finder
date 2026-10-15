# TEST MATRIX — 시나리오 단위 (독립 oracle 기준)

독립 oracle: `hashlib` 스트리밍 SHA-256 + 스트리밍 바이트 비교 + `os.stat` 파일 ID.
프로덕션 분류기/선택 정책으로는 기대값을 계산하지 않음. `SKIP`은 `PASS`에 합산하지 않음.

## Phase 0 — 안전 하네스

| ID | 내용 | 테스트 |
|---|---|---|
| SAFE-01 | 루트 내부 허용·`..`/절대경로/루트자체 거부 | `test_safety_guard.py::test_root_guard_accepts_inside_paths` 등 3건 |
| SAFE-02 | symlink 탈출 거부 | `test_safety_guard.py::test_root_guard_refuses_symlink_escape` |

## Phase 1 — 정확 중복 (DUP)

| ID | 시나리오 | 독립 기대값 | 테스트 | 결과 |
|---|---|---|---|---|
| DUP-01 | 동일 바이트 ↔ 동일 이름 다른 바이트 | 바이트 동일 쌍만 그룹 | `test_dup_exact.py::test_dup01...` | PASS |
| DUP-02 | 빈 파일·동일 크기 다른 내용·부분해시 충돌형 | false positive 0, 바이트 게이트 | `test_dup02_empty...`, `test_dup02_seeded_hash_collision...` | PASS |
| DUP-03 | hardlink·symlink | 동일 inode 중복 집계 금지, 루트 외 확장 금지 | `test_dup03...` | PASS |
| DUP-04 | Rust 상태·명시적 python fallback | 동일 매니페스트 결과 집합 동일; Rust 미설치=parity BLOCKED | `test_dup_backend.py` 2건 | PASS(단위) + parity BLOCKED |
| DUP-05 | 탐색↔해싱 사이 바이트 변경 | stale 미신뢰·fresh 해시 | `test_dup05...` | PASS |
| DUP-06 | cancel→resume·캐시 손상 | clean scan과 동일, 오염 캐시 무시 | `test_dup_backend.py` 3건 | PASS |
| DUP-07 | selection/safelist/ignore·hardlink 적격 | KEEP 삭제 후보 제외, 그룹종별 적격 고정 | `test_dup_policy_schema.py` 3건 | PASS |
| DUP-08 | CLI JSON v3·legacy loader·GUI 그룹 | 직렬화↔재로드 의미 동일 | `test_dup08...` 2건 + CLI 실프로세스 E2E 1건 | PASS |

결정론 케이스 세트(`fixtures_cases.py`): 동일 바이트·동명이종·빈 파일·한글/이모지·대소문자·동일크기이종·
부분충돌·숨김·읽기전용·mtime skew·hardlink·symlink·중첩경로·고유파일 = 30 시나리오, 1KB 등급 기본 + 16MiB 등급 opt-in(`PYDUP_QUALITY_LARGE=1`).

## Phase 2 — 삭제·격리·복원·하드링크 (FS)

| ID | 실험 | 불변식 | 테스트 | 결과 |
|---|---|---|---|---|
| FS-01 | 격리→새 인스턴스 복원 | SHA-256/크기 복구, DB 일치, 격리본 잔류 없음 | `test_fs01...` | PASS |
| FS-02 | DB insert 오류(예외/0 반환) | 원본 복귀 또는 복구가능 orphan 보고, 양쪽 소실=FAIL | `test_fs02...` 2건 | PASS |
| FS-03 | 이동 성공 후 상태 갱신 오류 | 거짓 성공 표시 금지, 목적지 위치 보고로 복구 가능 | `test_fs03...` | PASS (제품 수정: 실패 시 dest 경로 반환, 하위호환) |
| FS-04 | 충돌 복원 | 신파일 보존 + 충돌명 복원, 양 SHA 확인 | `test_fs04...` | PASS |
| FS-05 | 하드링크 통합·Undo | 바이트 복원, file ID/link 불변식 | `test_fs05...` | PASS |
| FS-06 | 계획 후 내용 변경 | fresh stat 기록 고정 (path/size/mtime 계약) | `test_fs06...` | PASS |
| FS-07 | 경계 취소 반복 | before/after/recoverable만 허용 | `test_fs07...` | PASS |
| FS-08 | 혼합 실패 분리 | 성공/실패 분리 표시, 원본 삭제 0 | `test_fs08...` | PASS |
| FS-09 | retention 경계 | live purge 금지, 대상 정확 | `test_fs09...` | PASS |
| FS-10 | worker 실경로 종단간 | 실파일+실DB 검증 (가짜 결과 금지) | `test_fs10...` | PASS |

## Phase 3 — Mutation (전부 KILLED, 증거: MUTATION_EVIDENCE.md)

M1 바이트비교 생략→DUP-02 / M2 캐시 무조건 신뢰→DUP-05·06 / M3 inode dedup 제거→DUP-03 /
M4 INSERT 실패 무시→FS-02 / M5 덮어쓰기 복원→FS-04 / M6 stale 검사 생략→FS-06 /
M7 전그룹 hardlink 허용→DUP-07·FS-05 / M8 retention 반전→FS-09 / M9 무조건 completed→FS-08·10.
9/9 KILLED, revert SHA 일치, 실행 후 tracked tree clean.

## Phase 4 — CI 게이트

- 기존 `rust-audit.yml` 유지 (Rust 변경 전용).
- 신규 `python-quality.yml`: `src/**·tests/**·cli.py` 변경 시 Windows+Linux pytest 전체 실행.
- Rust wheel 실설치·PyO3 parity는 wheel provenance 검사 후 별도 실행 (본 환경 BLOCKED).
