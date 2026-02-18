# PyDuplicate Finder Pro - Feature Ideas (Draft)

## Status Snapshot (2026-02-18)

Implemented from this backlog:
- Advanced GUI scan options wired to core (`mixed_mode`, `detect_duplicate_folders`, `incremental_rescan`, baseline session)
- CLI flags for advanced scan options
- Delete dry-run summary before destructive operations
- Retry flow extension beyond delete operations
- Core i18n cleanup for operation/quarantine/history messages
- Scheduled scan foundation (settings + DB tables + periodic trigger + auto export)
- Folder-duplicate result labeling and enriched CSV schema
- Initial modularization (`scan_engine`, `scan_controller`, `ops_controller`)

Still open:
- Full extraction of scan logic into a pure engine
- Deeper split of `main_window` orchestration across controllers

This document proposes add-on features that fit the current architecture.
It is based on reading `README.md`, `CLAUDE.md`, and key modules under `src/`.

## Baseline (What Exists Today)

Core principles and constraints (from `CLAUDE.md`, reinforced by the code):
- Strict separation: `src/core` contains business logic and should not depend on `PySide6.QtWidgets`.
- UI strings should go through `src/utils/i18n.py` (`strings.tr(...)`).
- Long-running work uses threads (`QThread`) + cancellation flags + progress signals.
- SQLite cache uses WAL + thread-local connections.

Implemented capabilities (high-level):
- Duplicate scanning modes: content-based duplicates (BLAKE2b), content+name, name-only, optional byte-by-byte verification.
- Similar image detection: pHash + BK-Tree + Union-Find grouping.
- Safety: system folder protection, file lock detection, delete-to-trash option, undoable delete via persistent quarantine, disk-space preflight checks.
- Persistence: scan sessions (resume), cached file lists/hashes, saved results/selected paths.
- UX foundation: sidebar navigation (Scan/Results/Tools/Settings), incremental rendering for huge results, preview panel, exporting to CSV.

Key reference files (implementation anchors):
- Scan engine: `src/core/scanner.py`
- Cache/session DB: `src/core/cache_manager.py`
- Safety delete + undo/redo: `src/core/history.py`, `src/core/quarantine_manager.py`, `src/core/preflight.py`
- Operation logging/queue: `src/core/operation_queue.py`
- Similar images: `src/core/image_hash.py`
- Empty folder tooling: `src/core/empty_folder_finder.py`
- Auto-selection rules: `src/core/selection_rules.py`, `src/ui/dialogs/selection_rules_dialog.py`
- UI pages: `src/ui/pages/scan_page.py`, `src/ui/pages/results_page.py`, `src/ui/pages/tools_page.py`, `src/ui/pages/settings_page.py`

## Documentation Gaps (Worth Fixing First)

These are not new features, but they unlock adoption and reduce support load.

1) Update README to mention already-implemented “Tools” features
- Why: The app already contains Quarantine management, Selection Rules, Operations log, Preflight, and Hardlink consolidation flows, but `README.md` barely mentions them.
- Likely files: `README.md`, `README_EN.md`
- Risk/size: S / low.

2) Keep one canonical file for duplicated filenames
- Observation: There are duplicate-looking files like `src/ui/main_window (1).py` and `src/utils/i18n (1).py`.
- Why: Confusing for contributors; increases chance of editing the wrong file.
- Likely files: `src/ui/main_window (1).py`, `src/utils/i18n (1).py`
- Risk/size: S-M / medium (need to ensure nothing imports the “(1)” copies).

## Feature Backlog (Additions That Fit Current Architecture)

Legend:
- Size: S / M / L (implementation + test effort)
- Risk: Low / Med / High

### A. Scanning & Detection

1) “Follow symlinks” option (off by default)
- What: Add a scan option to follow symlinks (with strong safety rails: max depth, loop detection).
- Why: Some users store content via symlinked libraries; current scan uses `follow_symlinks=False`.
- Likely files: `src/core/scanner.py`, `src/ui/pages/scan_page.py`, `src/utils/i18n.py`
- Size/Risk: M / Med.

2) Hidden/system file filters
- What: Toggle to skip hidden files and OS metadata files (`.DS_Store`, `Thumbs.db`, etc.).
- Why: Reduces noise and speeds up scans.
- Likely files: `src/core/scanner.py` (filtering), `src/ui/pages/scan_page.py`
- Size/Risk: S / Low.

3) Include-patterns (in addition to exclude-patterns)
- What: Add optional include globs (only scan if matches). Keep current exclude list.
- Why: Useful for “scan only images/videos”, “scan only project folders”, etc.
- Likely files: `src/core/scanner.py`, `src/ui/pages/scan_page.py`, `src/ui/dialogs/exclude_patterns_dialog.py` (or new dialog)
- Size/Risk: M / Low.

4) Duplicate folder (directory) detection
- What: Identify duplicate directories by hashing directory manifests (file names + sizes + file hashes).
- Why: Users often have duplicated album folders / backups.
- Likely files: new `src/core/dir_dedup.py` (recommended), `src/core/scanner.py` (integration), UI additions in Results.
- Size/Risk: L / Med.

5) “Near-duplicate” text detection (optional)
- What: For text files, show similarity score (e.g., based on normalized lines) to find near-duplicates.
- Why: Helps detect duplicated config files with small differences.
- Constraint: No new deps required; can use stdlib `difflib`.
- Likely files: new `src/core/text_similarity.py`, UI preview integration in `src/ui/pages/results_page.py`.
- Size/Risk: M / Med.

6) Content-based ignore rules (path + extension + size window)
- What: Extend exclusion logic to support size ranges (e.g., ignore files < 4KB, or > 50GB) and extension sets.
- Why: Avoid hashing extreme sizes and noise.
- Likely files: `src/core/scanner.py`
- Size/Risk: S-M / Low.

### B. Performance & Scalability

7) Persistent scan index for “changed files only” rescans
- What: On subsequent runs, avoid walking unchanged directories aggressively by recording directory mtimes and/or a compact snapshot.
- Why: Huge speed-up for repeated scans.
- Likely files: `src/core/cache_manager.py` (new tables), `src/core/scanner.py` (reconciliation), UI scan options.
- Size/Risk: L / High (correctness + filesystem edge cases).

8) Smarter hashing strategy for huge files
- What: Add a mode that defaults to partial-hash + byte-compare only when needed, with user-visible policy.
- Why: Full hash on 100GB files is slow; current partial threshold exists but can be made configurable.
- Likely files: `src/core/scanner.py`, `src/ui/pages/scan_page.py`
- Size/Risk: M / Med.

9) Improve progress reporting quality
- What: Show per-stage timing, throughput (files/sec, MB/sec), and candidate counts.
- Why: Makes long scans feel controllable; helps diagnosing slow disks.
- Likely files: `src/core/scanner.py` (emit structured metrics), `src/core/cache_manager.py` (persist), `src/ui/main_window.py` (display).
- Size/Risk: M / Low.

### C. Safety, Operations, and “No Data Loss” UX

10) Quarantine retention scheduler (auto purge by age/size)
- What: Automatically apply retention rules at startup and/or periodically.
- Why: The quarantine is persistent and can grow indefinitely; there is already `apply_retention(...)`.
- Likely files: `src/core/quarantine_manager.py`, `src/ui/main_window.py` (startup hook), `src/ui/pages/settings_page.py` (settings UX)
- Size/Risk: S-M / Low.

11) Hardlink consolidation: stronger preflight + clearer rollback story
- What: Expand preflight checks (permissions, cross-volume, locked files, already-hardlinked) and show exact “bytes saved” estimate before executing.
- Why: Hardlink is powerful but risky; the app already has an advanced hardlink pipeline.
- Likely files: `src/core/preflight.py`, `src/core/operation_queue.py`, `src/ui/dialogs/preflight_dialog.py`, `src/ui/dialogs/operation_log_dialog.py`
- Size/Risk: M / Med.

12) “Verify before delete” policy knob
- What: If byte-compare is OFF, display a warning when deleting duplicates for some file types/sizes, and optionally re-verify selected files on demand.
- Why: Hash collisions are rare but user trust matters.
- Likely files: `src/ui/main_window.py`, `src/core/scanner.py` (optional verification helper)
- Size/Risk: M / Low.

13) Safer conflict restores (restore preview)
- What: When restoring from quarantine and destination exists, show what name will be used and allow user choice.
- Why: Current restore uses a conflict filename; making it explicit reduces confusion.
- Likely files: `src/core/quarantine_manager.py`, `src/ui/pages/tools_page.py` / dialogs
- Size/Risk: M / Low.

14) Operation queue: retry failed items
- What: When an operation is partial/failed, offer “retry failed” (with updated lock checks).
- Why: File locks and transient errors are common.
- Likely files: `src/core/operation_queue.py`, `src/ui/pages/tools_page.py`, `src/ui/dialogs/operation_log_dialog.py`
- Size/Risk: M / Low.

### D. Results UX (High Impact)

15) “Keep candidate” visualization per group
- What: Highlight which file will be kept (oldest/newest/rules-based), and show estimated reclaimable size.
- Why: Users want confidence before deleting.
- Likely files: `src/ui/components/results_tree.py`, `src/core/selection_rules.py`, `src/ui/main_window.py`
- Size/Risk: M / Low.

16) Rule simulation preview
- What: In Selection Rules dialog, add a preview that shows how rules would classify the current results (per group summary).
- Why: Reduces rule mistakes.
- Likely files: `src/ui/dialogs/selection_rules_dialog.py`, `src/core/selection_rules.py`, `src/ui/main_window.py`
- Size/Risk: M / Med.

17) Side-by-side compare
- What: For two selected items, show side-by-side comparison.
  - Images: side-by-side preview + zoom.
  - Text: diff view (stdlib `difflib`).
- Why: Makes “which one to keep” easy.
- Likely files: `src/ui/pages/results_page.py`, `src/ui/main_window.py`
- Size/Risk: M-L / Med.

18) Group-level actions in context menu
- What: Add “check/uncheck all”, “apply rules to group”, “hardlink consolidate group”, etc. (some already have i18n keys).
- Why: Faster workflow.
- Likely files: `src/ui/components/results_tree.py`, `src/ui/main_window.py`
- Size/Risk: S / Low.

19) Missing-file markers on loaded results
- What: When loading results JSON later, mark paths that no longer exist.
- Why: Results are persisted but filesystem changes.
- Likely files: `src/ui/main_window.py`, `src/ui/components/results_tree.py`
- Size/Risk: S / Low.

20) “Filter aware delete” improvements
- What: When filter is active, show a stronger confirmation that hidden checked files are included (some messaging exists).
- Why: Prevent surprise deletes.
- Likely files: `src/ui/main_window.py`, `src/utils/i18n.py`
- Size/Risk: S / Low.

### E. Similar Image Mode Improvements

21) Similar-image result metadata
- What: Show image dimensions/format and similarity score between neighbors.
- Why: Makes clusters explainable.
- Likely files: `src/core/image_hash.py` (already has `get_image_info`), `src/ui/pages/results_page.py`
- Size/Risk: M / Low.

22) Mixed-mode scan: duplicates + similar images in one run
- What: Run normal duplicate scan and similar image scan together and merge into results with tags.
- Why: Many users want one “scan everything” flow.
- Likely files: `src/core/scanner.py` (pipeline refactor), UI changes to represent group types.
- Size/Risk: L / High (long-running and result semantics).

### F. Internationalization & Consistency

23) Localize operation/preflight messages
- What: Some core messages (preflight issues, operation log messages) are plain English.
- Why: UI already supports ko/en; these are shown in dialogs.
- Likely files: `src/core/preflight.py`, `src/core/operation_queue.py`, `src/utils/i18n.py`, dialogs/pages that display them.
- Size/Risk: M / Low.

24) Structured error codes instead of raw strings
- What: Emit error codes from core (e.g., `locked`, `missing`, `disk_space`) and let UI map to i18n.
- Why: Keeps core UI-independent and makes localization consistent.
- Likely files: `src/core/preflight.py`, `src/core/operation_queue.py`, `src/ui/dialogs/preflight_dialog.py`, `src/utils/i18n.py`
- Size/Risk: M / Med.

### G. Developer / Maintenance Features

25) Headless scan CLI (no UI)
- What: Provide a CLI command that runs scans using `src/core` and exports JSON/CSV.
- Why: Enables scheduled tasks and CI-like scanning on servers.
- Constraint: Keep UI-free; reuse core and exporting module if possible.
- Likely files: new `cli.py` (repo root), `src/core/scanner.py`, `src/ui/exporting.py` (or new core exporter).
- Size/Risk: M / Low.

26) Automated regression tests for core modules
- What: Add tests for CacheManager schema, selection rules behavior, quarantine restore, and scan resume.
- Why: Protects against concurrency regressions.
- Likely files: new `tests/` package.
- Size/Risk: M / Med.

## Suggested “Next 3” (Fast Value)

If you want a short, safe iteration cycle, these three deliver quickly:
1) Quarantine retention scheduler (Feature #10)
2) Keep candidate visualization + reclaim size (Feature #15)
3) Localize preflight/operation messages (Feature #23)

They are small-to-medium in scope, align with existing architecture, and improve trust/UX.
