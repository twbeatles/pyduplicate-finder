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
