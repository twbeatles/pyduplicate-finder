# Duplicate Scan Feature Audit (2026-02-27)

## 1) Scope

- Requested focus: duplicate file scan implementation risks and missing improvements.
- References reviewed:
  - `claude.md`
  - `README_EN.md`
  - `src/core/scanner.py`
  - `src/core/scan_engine.py`
  - `src/core/cache_manager.py`
  - `src/ui/main_window.py`
  - `cli.py`
  - scanner/cache related tests under `tests/`

## 2) Validation Performed

- Static code review (core scan flow + UI session/resume flow + cache/session persistence).
- Existing regression tests run:
  - `pytest -q tests/test_scan_engine.py tests/test_scanner_follow_symlinks.py tests/test_scanner_perf_path.py tests/test_cache_path.py`
  - Result: `9 passed`
- Targeted runtime repro scripts executed for high-risk scenarios (cancel/protect/ext filter).

## 3) Findings (Priority Ordered)

### P0-1. Cancel can be ignored in later scan stages, but scan still emits `scan_finished`

- Evidence (code):
  - `src/core/scanner.py:930-948` full-hash stage has no cancel gate after `_calculate_hashes_parallel(..., is_quick_scan=False)`.
  - `src/core/scanner.py:949-964` folder-dup and mixed-mode stages have no `self._stop_event` check after sub-stage returns.
  - `src/core/scanner.py:965-977` completion path still marks `completed` and emits `scan_finished`.
- Runtime repro (confirmed):
  - Injected cancellation during full-hash stage produced `{'finished': 1, 'cancelled': 0}`.
  - Injected cancellation during mixed-mode similar-image stage produced `{'finished': 1, 'cancelled': 0}`.
  - Injected cancellation during folder-dup stage produced `{'finished': 1, 'cancelled': 0}`.
- Why this matters:
  - `README_EN.md:165-166` promises stop/resume behavior.
  - Users can believe scan completed normally while it was actually interrupted.
  - Session status may become `completed` instead of `paused`, corrupting resume semantics.
- Recommendation:
  1. Add centralized cancel checkpoint helper and call it after every expensive stage (`full hash`, `folder dup`, `mixed image`).
  2. On cancel: set session `status='paused'`, emit `scan_cancelled`, and return immediately.
  3. Add regression tests for cancel at each stage.

### P0-2. `protect_system` can be bypassed when the selected scan root itself is protected

- Evidence (code):
  - `src/core/scanner.py:455-467` directly calls `_scandir_recursive(folder)` without root-level protected-folder guard.
  - `src/core/scanner.py:369-371` protected check is only applied when descending into directory entries.
  - Files directly under a protected root path can still be yielded (`src/core/scanner.py:395-404`).
- Runtime repro (confirmed):
  - Forced protected root => `is_protected_root=True` while `_scandir_recursive(root)` still returned files.
- Why this matters:
  - Contradicts safety claim in `README_EN.md:19`.
  - Highest-risk class: scanning system root selected by mistake.
- Recommendation:
  1. Add root-folder guard in `_scan_files` and incremental path (`if is_protected(folder): continue`).
  2. Add explicit warning/progress message when root is skipped due protection.
  3. Add unit test: protected root should yield zero files.

### P1-1. Extension filter fails for dot-prefixed extensions (e.g. `.txt`)

- Evidence (code):
  - Stored as-is: `self.extensions = set(ext.lower().strip() for ext in extensions)` (`src/core/scanner.py:56`).
  - Compared as dot-stripped: `ext.lower().replace('.', '')` (`src/core/scanner.py:399-401`).
- Runtime repro (confirmed):
  - `extensions=['txt']` scans file.
  - `extensions=['.txt']` scans zero files.
- Why this matters:
  - User input often includes dot format (`.jpg`, `.png`).
  - Leads to false negative scans.
- Recommendation:
  1. Normalize once in constructor: strip leading dot and whitespace.
  2. Share same normalization in CLI and GUI config pipeline.
  3. Add regression tests for both `txt` and `.txt` forms.

### P1-2. Hashing/worker exceptions are swallowed, causing silent result loss

- Evidence (code):
  - `src/core/scanner.py:805-806` and `1137-1138` use broad `except Exception: pass` in worker futures.
- Why this matters:
  - Corrupted/locked files can disappear from duplicate grouping without any user-visible signal.
  - Hard to debug trust issues in scan outputs.
- Recommendation:
  1. Count and report skipped/error files per stage.
  2. Add debug logging with capped sample paths.
  3. Surface summary in status/operation log.

### P2-1. Resume/baseline hash may miss semantically identical configs due non-canonical fields

- Evidence (code):
  - Config hash uses raw UI values from `_get_current_config` (`src/ui/main_window.py:2549-2570`).
  - Extensions kept as raw string; folder order and spacing differences change hash.
- Why this matters:
  - Same effective scan intent may fail to reuse baseline/resume cache.
  - Leads to unnecessary full rescans.
- Recommendation:
  1. Canonicalize hash config (normalized folder paths sorted, extensions parsed/sorted/lowercased).
  2. Keep UI representation unchanged, but hash on normalized projection only.

## 4) Suggested Additions (Feature/Quality)

1. Add stage-level cancel checkpoints and tests:
   - cancel during full hash
   - cancel during folder duplicate detection
   - cancel during mixed-mode similar image phase
2. Add safety tests:
   - protected root folder must be skipped entirely
3. Add input normalization tests:
   - extensions with and without dot should behave identically
4. Add scan integrity telemetry:
   - `files_scanned`, `files_hashed`, `files_skipped_error`, `files_skipped_locked`
   - expose in UI summary and exported JSON meta
5. Add optional strict mode:
   - if hash/scan errors exceed threshold, mark scan status as partial/failure instead of completed

## 5) Alignment vs Documentation

- `README_EN.md` and `claude.md` emphasize:
  - cancel safety (`scan_cancelled` semantics)
  - system protection
- Current implementation has concrete gaps for both (P0 items).
- These should be addressed before expanding scan modes, because they affect result trust and safety guarantees.

## 6) Immediate Fix Order

1. P0-1 cancel correctness across all post-collect stages.
2. P0-2 protected-root enforcement.
3. P1-1 extension normalization.
4. P1-2 error observability (at least summary counters + logs).
5. Add regression tests for all above before additional feature work.

## 7) Implementation Completion (2026-02-28)

All proposed items in this audit are now implemented.

- P0-1 cancel correctness: fixed
  - Added stage-level cancel handling after quick/full hash, folder-duplicate, and mixed similar-image stages.
  - Cancel path now persists session `paused` and emits `scan_cancelled`.
- P0-2 protected-root enforcement: fixed
  - Added root-level protected-folder skip in both full and incremental collection paths.
- P1-1 extension normalization: fixed
  - Extension inputs are canonicalized to lowercase dotless tokens.
- P1-2 error observability: fixed
  - Replaced silent future exception swallow with telemetry+logging counters.
  - Added lock-vs-error classification and capped error samples.
- P2-1 canonical config hash: fixed
  - Folder/extension/include/exclude normalization + sorting before hash.
- Additional requested enhancements: fixed
  - Strict mode in UI/CLI (`partial` status on threshold breach).
  - JSON meta export (`scan_status`, `metrics`, `warnings`) with backward-compatible loading.

### Added Regression Tests

- `tests/test_scanner_cancel_paths.py`
- `tests/test_scanner_protection_root.py`
- `tests/test_scanner_extension_normalization.py`
- `tests/test_scanner_telemetry.py`
- `tests/test_scanner_strict_mode.py`
- `tests/test_scan_hash_config_canonicalization.py`
- `tests/test_cli_strict_and_meta.py`
