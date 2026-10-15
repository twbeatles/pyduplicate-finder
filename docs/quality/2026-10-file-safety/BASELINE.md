# BASELINE — 2026-10-15 실파일 안전 검증 기준선 (추가 검증 반영)

- HEAD: `c7bf9a5aae8f8a2e2c47330ffe443151ac74981f` (착수 시 최신)
- 제품 수정: `src/core/quarantine_manager.py` 15줄 추가 (FS-03: 이동 성공 후 DB 갱신 실패 시
  목적지 경로 보고 — 아래 "추가 검증" 참조). 그 외 src/ 수정 없음.
- OS: Windows (실행 호스트)
- Workspace FS: D: exFAT / 테스트 스크래치: C: NTFS (TEMP dir) — 하드링크·inode 검증은 NTFS 스크래치에서 수행
- Python: 3.15.0
- Rust `pydup_core`: Python 바인딩 휠 미설치 (`is_rust_available() == False`, `auto` → `python`)
  → Python↔Rust parity PASS 주장 불가, 명시적 BLOCKED. 강제 `rust` 요청은 `RustCoreUnavailable`로 fail-closed.
  Rust 네이티브 단위 테스트는 별도 GREEN (`cargo test`: 4 passed, 0 failed) — 바인딩 parity만 BLOCKED.
- 기존 테스트(변경 전 수집): 208 collected
- 전체 실행(본 작업 최종): 257 collected → 232 passed, 25 skipped(전부 기존 사유), 실패 0
  → 내역: 세션 착수 시 기존분 183 passed · 본 작업 품질 스위트 30 passed ·
     동시 진행 타 작업스트림(GUI, 범위 밖) 19 passed. 본 작업으로 인한 회귀 0.
- 신규 품질 스위트: `tests/quality/` 30 tests
  - 기본 등급(1KB): 30 passed (최종 2회 연속; 작성 중 29건 기준 3회 연속 무실패)
  - 대용량 등급(16MiB, `PYDUP_QUALITY_LARGE=1`): 30 passed (8.0s)
  - 실제 CLI 프로세스 E2E: `cli.py --byte-compare --output-json` v3 실출력 1 group/2 members 확인,
    committed test(`test_cli_e2e_json.py`)로 고정
- 정적 검사: `pyright tests/quality scripts/quality_mutation_check.py` → 0 errors.
  전체 `pyright` 5 errors는 전부 기존·환경 사유 (미설치 import 3건 + 타 작업중 UI 파일 2건), 신규 파일 무관.
- Mutation: 9 실행 · 9 검출(KILLED) · revert SHA 전부 일치 · 실행 후 tracked tree clean
- 원본 loss: 0 (모든 파괴적 연산은 per-test 격리 루트 내부, root guard 통과분만)
