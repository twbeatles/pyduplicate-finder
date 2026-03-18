# Manual Verify Scripts

`tests/verify_backup_collision.py` and `tests/verify_image_hash.py` are manual verification scripts.
They are not part of the default `pytest` suite by design.

## Run Commands

```bash
python tests/verify_backup_collision.py
python tests/verify_image_hash.py
```

## When To Run

1. Before release candidates that modify `src/core/history.py` or `src/core/quarantine_manager.py`.
2. After algorithm/performance changes in `src/core/image_hash.py`.

## Pass Criteria

1. `verify_backup_collision.py`: all created files are uniquely quarantined and fully restorable.
2. `verify_image_hash.py`: grouping executes successfully and finds expected similar groups.

## Additional Manual Checks (2026-02-26)

1. JSON compatibility round-trip:
   - `cli.py --output-json`로 생성한 v2 JSON을 GUI에서 불러오기
   - GUI에서 다시 저장한 JSON을 재로딩해 그룹/파일 수 일치 확인
2. Scheduler input validation:
   - 설정 화면에서 `25:99` 같은 잘못된 시간 입력 시 저장 차단/오류 표시 확인
3. Cache cleanup policy:
   - 설정 화면의 세션 보존 개수/해시 보존 일수 변경 후 앱 재시작 시 cleanup 정책 반영 확인
4. Preview stability under rapid selection:
   - 결과 트리에서 빠르게 파일 선택을 바꿔도 UI 예외/멈춤 없이 미리보기 갱신 확인

## Static Quality Checks (2026-03-09)

1. Pyright/Pylance baseline:
   - `pyright src tests cli.py main.py`
   - 기대값: `0 errors`
2. Encoding integrity:
   - `pytest -q tests/test_source_encoding_integrity.py`
   - 기대값: UTF-8 decode/`U+FFFD`/known mojibake pattern 검사 통과

## Packageization Checks (2026-03-18)

1. Public facade regression:
   - `pytest -q tests/test_public_api_facades.py`
   - 기대값: packageized 모듈에서도 기존 공개 import 경로와 핵심 export 유지
2. Full regression baseline:
   - `pytest -q`
   - 기대값: `111 passed`
3. GUI smoke after package split:
   - `python main.py`
   - 기대값: 앱이 정상 기동되고 스캔/결과/도구/설정 페이지 전환, 테마 전환, 결과 필터 입력이 예외 없이 동작
