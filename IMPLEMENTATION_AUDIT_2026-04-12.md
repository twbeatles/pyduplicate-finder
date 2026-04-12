# Implementation Audit Follow-up (2026-04-12)

## Status

The implementation items from the 2026-04-12 audit were completed in this branch.

## Implemented Fixes

1. Weekly scheduler first-run semantics were corrected.
   - A newly enabled weekly job now waits for the next configured weekday/time slot instead of firing immediately after the target weekday already passed.
2. Zero-byte duplicate handling was aligned across live scan collection and cached-session reuse.
   - Empty files are included only when `min_size_kb == 0`.
3. Scheduled export failures now affect run bookkeeping correctly.
   - If scan execution completed but JSON/CSV export failed, the run is finalized as `partial`.
   - Run messages may now include `missing_folders:<n>` and `export_failed:<formats>`.
4. Scan cancel/failure rollback now restores the full prior result bundle.
   - Checked paths, `file_meta`, missing-file state, and `baseline_delta_map` are restored together.
5. Quarantine retention is no longer limited to the first 5,000 rows.
   - Batched oldest-first iteration now drives age/size cleanup.

## Additional Hardening Implemented

1. Result JSON `version=2` keeps backward compatibility while supporting richer optional metadata.
   - `meta.selected_paths`
   - `meta.file_meta` (`size`, `mtime`, `exists`)
   - `meta.baseline_delta_map` (`new|changed|revalidated`)
2. GUI result loading now restores selection state, file metadata, missing badges, and incremental delta state from saved JSON.
3. CLI `--quiet` now suppresses all successful stdout, including progress and save-summary lines.

## Packaging And Docs

1. `PyDuplicateFinder.spec` was reviewed.
   - No spec change was required because the touched modules were already included in the existing hidden-import set.
2. `README.md`, `README_EN.md`, `claude.md`, `gemini.md`, and `tests/MANUAL_VERIFY.md` were updated to reflect the new behavior.

## Verification

- `pytest -q` -> `122 passed`
- `pyright src tests cli.py main.py` was attempted in this workspace, but local dependency resolution is currently missing for `imagehash` and `send2trash`.
