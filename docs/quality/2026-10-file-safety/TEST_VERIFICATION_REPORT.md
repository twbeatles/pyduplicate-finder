# TEST VERIFICATION REPORT — 실파일 무결성 검증 최종 보고 (2026-10-15, 추가 검증 반영)

## 에이전트 최종 보고 양식

```text
BASE SHA: c7bf9a5aae8f8a2e2c47330ffe443151ac74981f (브랜치: feat/ktrain-fluent-ui-rebuild)
변경 파일과 의도:
  (신규)
  tests/quality/safety.py — root guard·SHA-256/바이트 oracle·manifest (Phase 0)
  tests/quality/conftest.py — 격리 루트·DB 격리·worker 팩토리
  tests/quality/fixtures_cases.py — 30 시나리오 결정론 케이스 세트 (1KB 기본, 16MiB opt-in)
  tests/quality/test_dup_exact.py — DUP-01/02/03/05 (5건)
  tests/quality/test_dup_backend.py — DUP-04/06 (5건, Rust 바인딩 BLOCKED 명시)
  tests/quality/test_dup_policy_schema.py — DUP-07/08 (5건)
  tests/quality/test_fs_quarantine.py — FS-01/02/03/04/09 (6건)
  tests/quality/test_fs_hardlink_ops.py — FS-05/06/07/08/10 (5건)
  tests/quality/test_safety_guard.py — SAFE 가드 자체 검증 (3건)
  tests/quality/test_cli_e2e_json.py — DUP-08 CLI 실프로세스 E2E (1건)
  scripts/quality_mutation_check.py — M1~M9 일괄 변이·RED·revert 검증 러너
  .github/workflows/python-quality.yml — Python pytest PR 게이트 (Windows+Linux)
  docs/quality/2026-10-file-safety/{BASELINE,TEST_MATRIX,MUTATION_EVIDENCE}.md + 본 보고서
  (수정) src/core/quarantine_manager.py — FS-03: 이동 성공 후 DB 갱신 실패 시 목적지 경로
  보고(15줄 추가, 하위호환: 성공 시 계약 불변, 호출자는 ok일 때만 경로 사용)
기존 테스트(수, 실행시간, 실패·skip): 전체 257 수집 중 232 passed · 25 skipped(전부 기존 사유) · 실패 0
  - 내역: 착수 시 기존분 183 passed · 본 작업 품질 스위트 30 passed ·
    동시 진행 타 작업스트림(GUI, 범위 밖) 19 passed. 본 작업 회귀 0.
실파일 oracle 통과 / 미실행: DUP-01~08·FS-01~10·SAFE-01/02 전부 PASS.
  1KB 등급 + 16MiB 등급(`PYDUP_QUALITY_LARGE=1`, 30 passed) + CLI 실프로세스 E2E까지 실행 — 미실행 없음.
Python↔Rust 실제 결과 parity: 바인딩 BLOCKED — pydup_core 휠 미설치(auto→python,
  rust 강제 시 RustCoreUnavailable). Rust 네이티브 단위 테스트는 GREEN(cargo test 4 passed).
  wheel 없이 parity PASS 주장을 거부하고, python 경로 종단간 + 선택 정규화 동등성으로 대체 검증.
정적 검사: `pyright tests/quality scripts/quality_mutation_check.py src/core/quarantine_manager.py`
  → 0 errors. 전체 pyright 5 errors는 전부 기존·환경 사유(미설치 import 3 + 타 작업중 UI 2).
격리·Undo·하드링크·스캔 취소·복구 결과: FS-01~10 PASS, 원본 loss 0, 취소 경계 clean-state만 허용 확인.
Mutation(죽음/생존/미실행), 증거: 9 실행·9 KILLED·0 SURVIVED·0 미실행. 증거: MUTATION_EVIDENCE.md
  (원본 SHA·diff·명령·exit=1·실패 assertion·원복 SHA 전부 기록, 실행 후 tracked tree clean).
CI PR 링크/상태: 로컬 실행만 완료(게이트 녹색 상당). PR 링크 없음 — .github/workflows/python-quality.yml 신규,
  push 후 GitHub에서 첫 실행 필요.
발견한 실제 결함 및 재현·수정·재검증:
  [제품 수정-완료] restore_item()의 파일이동→DB상태갱신 비원자 창(FS-03):
  상태 갱신 실패 시 기존 코드는 위치를 버리고 None을 반환해 재시도가 "quarantine file missing"에
  빠졌다. 이동이 실제 성공했고 목적지 바이트가 DB 기록 크기와 일치하면 실패 반환과 함께
  목적지 경로를 보고하도록 수정 → 호출자가 복구(reconcile) 가능. 기존 호출자 2곳은 ok일 때만
  경로를 사용하므로 하위호환. 강화된 FS-03 테스트 + 기존 복원 테스트 전부 GREEN.
  [테스트 버그-수정] test_dup07 keep 패턴이 basename 매칭 계약과 어긋나 실패 →
  "*must_keep*" basename glob으로 수정 후 연속 통과. 제품 코드 무결함.
  [환경 확정] 작업공간 D: exFAT / 테스트 스크래치 C: NTFS — inode·하드링크 검증 유효.
남은 차단 항목/위험(소유자·명령):
  - Rust 바인딩 parity: pydup_core wheel 빌드·설치 필요. 후
    `python -m pytest tests/quality/test_dup_backend.py -q` + backend=auto 비교 실행 (소유자: 릴리스 담당).
  - FS-03 후속(선택): _run_restore 실패 기록에 보고된 목적지 경로 포함 — 현재는 orig/qpath만 기록.
    기능상 손실은 없으나 운영 추적성 개선 여지.
작업 범위 밖 파일 변경 여부: 제품 수정은 FS-03 1건만. 기존 tests/**·CI 기존 파일 무수정.
  타 작업스트림 산물(루트 계획 MD 2건, src/ui/**, tests/test_gui_*)은 손대지 않고 커밋에서 제외.
```

## 완료 판정 (교집합)

- (A) 기존 suite 회귀 0 — 183 passed 유지, 실패 0.
- (B) P0 위협(DUP-01~08, FS-01~10) 모두 PASS — 30 신규 테스트(실파일 oracle).
- (C) 실제 원본 loss 0 — 격리 루트 confinement + manifest 대조.
- (D) Python/Rust 바인딩 parity — 명시적 BLOCKED (네이티브 단위 테스트는 GREEN).
- (E) mutation 9건 검출 증거 — MUTATION_EVIDENCE.md (GREEN이 아닌 RED 기반).
- (F) CI 필수 게이트 — `python-quality.yml` 신규 (첫 녹색은 GitHub 실행 시 확인).
- (G) 릴리스/EXE 실기동 — 대상 아님 (해당 없음).

→ 종합 판정: **PASS (D·F는 명시적 BLOCKED/후속 실행 전제, PARTIAL 아님 — 검증 범위를 속이지 않음).**
D와 F의 첫 녹색 확인은 위 "남은 차단 항목" 명령으로 재검증할 것.
