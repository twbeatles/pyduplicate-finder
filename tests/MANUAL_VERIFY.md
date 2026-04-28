# Manual Verify Scripts

`tests/verify_backup_collision.py` and `tests/verify_image_hash.py` are manual verification scripts.
They are intentionally excluded from the default `pytest` suite.

## Run Commands

```bash
python tests/verify_backup_collision.py
python tests/verify_image_hash.py
```

## When To Run

1. Before release candidates that modify `src/core/history.py` or `src/core/quarantine_manager.py`.
2. After algorithm or performance changes in `src/core/image_hash.py`.

## Pass Criteria

1. `verify_backup_collision.py`: all created files are uniquely quarantined and fully restorable.
2. `verify_image_hash.py`: grouping executes successfully and finds the expected similar-image groups.

## Additional Manual Checks (2026-02-26)

1. JSON compatibility round-trip:
   - Load a v2 JSON file created by `cli.py --output-json` into the GUI.
   - Save it again from the GUI and confirm group and file counts remain stable.
2. Scheduler input validation:
   - Enter an invalid time such as `25:99` in Settings and confirm save is blocked with a user-facing error.
3. Cache cleanup policy:
   - Change session/hash cleanup settings and confirm startup cleanup immediately follows the updated policy.
4. Preview stability under rapid selection:
   - Move quickly across results and confirm preview updates without UI exceptions or freezes.

## Static Quality Checks (2026-03-09)

1. Pyright/Pylance baseline:
   - `pyright src tests cli.py main.py`
   - Expected result: `0 errors` when project dependencies are installed.
2. Encoding integrity:
   - `pytest -q tests/test_source_encoding_integrity.py`
   - Expected result: UTF-8 decode, `U+FFFD`, and known mojibake checks all pass.

## Packageization Checks (2026-03-18)

1. Public facade regression:
   - `pytest -q tests/test_public_api_facades.py`
   - Expected result: packageized modules preserve the public import paths and exports.
2. Full regression baseline:
   - `pytest -q`
   - Historical package-split baseline at the time: `111 passed`
3. GUI smoke after package split:
   - `python main.py`
   - Expected result: the app starts normally and scan/results/tools/settings navigation, theme switching, and result filtering work without exceptions.

## Additional Manual Checks (2026-04-12)

1. Weekly scheduler first-run behavior:
   - Create a weekly schedule for a weekday that already passed this week.
   - Confirm the next-run label and due-check wait for the next scheduled slot instead of starting immediately.
2. Zero-byte duplicate policy:
   - Scan a folder with two empty files using `min_size_kb=0` and confirm they are grouped as duplicates.
   - Repeat with `min_size_kb>0` and confirm the empty files are excluded.
3. Save/load result bundle restoration:
   - Save results with checked items, then reload the JSON and confirm checked state, file metadata, missing badges, and incremental delta markers are restored.
4. Scheduled export partial-failure bookkeeping:
   - Configure scheduled JSON/CSV export to a non-writable output path and confirm the run is finalized as `partial`.
   - Confirm the recorded message includes `export_failed:<format>` and any `missing_folders:<n>` suffix.
5. Quarantine retention scale:
   - Seed more than 5,000 quarantined rows in a test DB and confirm age/size retention still purges beyond the first page.

## Additional Manual Checks (2026-04-14)

1. Insights page refresh:
   - Open the `Insights` page after at least one scan and confirm session metrics, reclaim estimate, failure rate, quarantine usage, and scheduled run history populate without exceptions.
2. Session compare and delta filter:
   - Run an incremental rescan with a valid baseline.
   - Confirm the Results page delta filter (`all/new/changed/revalidated`) changes visible rows correctly.
   - Open `Compare Sessions` and confirm the summary counts match the filtered file list.
3. Multi-job scheduler UI:
   - Create two named jobs with different folders or output directories.
   - Confirm each job persists independently, can be selected back into the form, and `Run Now` executes the selected snapshot instead of current transient UI state.
4. Watch mode rerun:
   - Enable watch mode for a small test folder, finish an initial scan, then create or edit a file.
   - Confirm one incremental rerun is queued after debounce.
   - While that scan is running, create another file and confirm only one pending rerun remains queued.
5. Post-delete empty-folder cleanup:
   - Enable the setting for post-delete empty folder cleanup.
   - Delete or hardlink-consolidate files that leave intermediate parent folders empty.
   - Confirm only newly empty parents under the selected roots are removed and that a separate operation-log entry is created.
6. Similar-document dependency policy:
   - Remove or temporarily break `pypdf` in a controlled environment and request similar-document scanning on a folder containing PDFs.
   - Confirm GUI and CLI both fail fast with a clear dependency error instead of silently skipping PDF text extraction.

## Additional Manual Checks (2026-04-28)

1. Safelist / Ignore manager:
   - Open Tools and create exact-path, path-glob, and content-hash exemption rules.
   - Confirm search, edit, delete, and result-tree context-menu creation all persist to the same rule table.
2. Hardlink eligibility safety:
   - Scan exact duplicates, name-only duplicates, folder duplicates, similar images, and similar documents.
   - Confirm hardlink consolidation is available only for exact duplicate groups.
3. DB session restore parity:
   - Complete a scan, mark review states, set collection roles, save selected paths, then restart.
   - Confirm DB auto restore preserves file metadata, existence flags, selection reason, exemption status, review state, collection role, and baseline delta.
4. Operation plan validation:
   - Save a selected delete plan, modify or remove one referenced file, then load the plan.
   - Confirm stale/missing entries are excluded and still-valid entries remain selected.
5. Scheduled/watch structured history:
   - Trigger a scheduled run with missing folders and export failure, and a watch rerun with multiple coalesced events.
   - Confirm `missing_folders`, `export_failed`, and `watch_events` appear in dedicated history columns.
6. CLI unsupported options:
   - Run `python cli.py <folder> --watch` and `python cli.py <folder> --post-cleanup-empty-dirs`.
   - Confirm both fail with exit code `2` and clear stderr guidance.

## Current Automated Baseline

1. Full suite:
   - `pytest -q`
   - Expected result in this workspace: `145 passed`
2. Static typing:
   - `pyright src tests cli.py main.py`
   - Expected result in this workspace: `0 errors, 0 warnings`
3. Build smoke:
   - `pyinstaller PyDuplicateFinder.spec --clean`
   - Expected result: `dist/PyDuplicateFinderPro.exe` is produced successfully.
