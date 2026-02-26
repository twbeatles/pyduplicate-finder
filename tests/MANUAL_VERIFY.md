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
