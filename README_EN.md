# 🔍 PyDuplicate Finder Pro

[![한국어](https://img.shields.io/badge/lang-한국어-red.svg)](README.md)

**PyDuplicate Finder Pro** is a high-performance duplicate file management tool combining Python (PySide6) and a native Rust core (`pydup_core`). It leverages advanced multi-threading (Rayon) and smart caching to quickly and accurately scan for duplicate files even in large file systems, providing safe Undo capabilities.

---

## ✨ Key Features

### 🚀 High Performance with Native Rust Core
- **Native Rust Engine (`pydup_core`)**: PyO3 C-extension accelerates core I/O and hashing pipelines, **reducing scan time by 50.7% (2.03x faster)** on 10,000 files.
- **Ultra-Fast Parallel Hashing (BLAKE2b + Rayon)**: `BLAKE2b` hashing running on a Rayon thread pool releases the Python GIL, eliminating UI stutter during large scans.
- **Precision Byte Streaming Compare**: 1 MiB streaming buffer byte-by-byte comparison (`files_equal`) guarantees zero false positives.
- **High-Speed File Traversal (Native Discovery)**: Fast recursive traversal and precompiled `globset` pattern matching quickly index massive folder trees.
- **Smart Caching & Batch Processing**: `SQLite WAL` mode with batch processing handles hundreds of thousands of files seamlessly.
- **Seamless Python Fallback**: Automatically and transparently falls back to pure Python if the native module is unavailable.
- **Resume Interrupted Scans**: File lists and hash progress are cached so scans can resume after a restart.
- **Smooth UI**: Incremental rendering of results keeps the app responsive even with massive datasets.

### 🛡️ Safety & Precision
- **System Protection**: Automatically skips critical system folders (Windows, Program Files, etc.) to prevent accidental damage.
- **Physical Duplicate Prevention (Inode Check)**: Prevents counting symbolic links or shortcuts as duplicates of the same physical file.
- **Safe Delete & Robust Undo**: Asynchronous delete/restore operations keep UI responsive when processing thousands of files.
- **Recycle Bin Option**: Move files to system Recycle Bin instead of permanent deletion.
- **File Lock Detection**: Automatically detects files in use by other processes before deletion.
- **Persistent Quarantine + Retention**: Undoable deletes are kept in persistent Quarantine and cleaned by configured retention rules (age/size).
- **Safe Result Group Classification**: Exact duplicates, name-only groups, folder duplicates, similar images, and similar documents share one classifier; similar/name/folder groups are excluded from hardlink consolidation.

### 🎨 Modern UI & User Experience
- **Multiple Scan Modes**: 
    - **Similar Image Detection (pHash)**: Finds visually similar images (resized, recompressed, etc.)
    - **Similar Document Detection (SimHash)**: Groups near-duplicate `.txt`, `.md`, `.csv`, `.json`, `.py`, and `.pdf` files.
    - **Filename Comparison**: Quickly finds files with the same name regardless of content.
- **Exclude Patterns**: Skip unwanted folders/files like `node_modules`, `.git`, `*.tmp` using wildcard patterns (*, ?).
- **Scan Presets**: Save and load frequently used scan configurations.
- **Result Save/Load**: Export scan results to JSON and reload later.
  - New saves use the common `version=3` schema, and the loader remains backward-compatible with legacy / v2 / v3 JSON formats.
  - File-level state (`selection_reason`, `exemption_status`, `review_state`, `collection_role`, `baseline_delta`) is persisted.
- **Session Restore**: Detects the latest session and lets you resume or start a new scan.
- **Intuitive Tree View**: Expand/collapse all groups, right-click context menu for quick actions.
- **Insights Dashboard**: Dedicated page for recent scan sessions, reclaim estimates, failure rate, quarantine usage, and scheduled run history.
- **Session Compare**: Filter incremental `new / changed / revalidated` deltas and continue directly to result selection, bulk review-state changes, or CSV export.
- **Collection Role Table**: Manage scan folders in a Path/Role table and persist `primary`, `secondary`, or `none` roles into selection policy and scheduled job snapshots.
- **Watch Mode**: Monitor selected folders and queue an incremental rescan when changes are detected.
- **Custom Shortcuts**: Configure keyboard shortcuts for all functions.
- **Multi-language Support**: Full Korean and English interface support.

### 🧰 Tools
- **Quarantine Management**: Files deleted in undoable mode are moved to Quarantine; restore or permanently purge them later.
- **Safelist / Ignore Management**: Add, edit, delete, and search path/hash/glob exemptions from Tools, or add rules directly from the result-tree context menu.
- **Selection Rules**: Define ordered KEEP/DELETE rules using fnmatch-style wildcards and apply them to groups/results.
- **Operation Plan Save/Load**: Save selected delete plans as `operation_plan` JSON v1 and validate path/size/mtime on load, excluding stale or missing entries.
- **Operations Log**: Tracks operations (delete/restore/purge/hardlink, etc.) and supports per-item details plus CSV/JSON export.
- **Preflight Checks**: Runs safety checks (locks/permissions/volume constraints) before advanced operations.
- **Hardlink Consolidation (Advanced)**: Consolidate duplicates via hardlinks to reduce disk usage (optional).

---

## 📁 Project Structure

```
duplicate_finder/
├── main.py                  # Application entry point
├── requirements.txt         # Dependencies
├── PyDuplicateFinder.spec   # PyInstaller build config
├── pyrightconfig.json       # Pylance/Pyright static type-check config (Python 3.14)
├── .editorconfig            # UTF-8/EOL guardrails
├── claude.md                # AI context (Claude)
├── gemini.md                # AI context (Gemini)
├── scripts/
│   ├── build_rust_core.ps1  # Rust core (pydup_core) wheel build & pip install script
│   └── test_rust_core.ps1   # Rust cargo test & clippy verification script
├── rust/
│   └── pydup_core/          [Native Rust Core]
│       ├── Cargo.toml
│       └── src/
│           ├── lib.rs       # PyO3 entry point & GIL release
│           ├── hashing.rs   # BLAKE2b partial/full/batch parallel hashing (Rayon)
│           ├── byte_compare.rs # 1MiB streaming byte comparison
│           ├── discovery.rs # Fast filesystem traversal & filtering
│           ├── cancellation.rs # AtomicBool cancellation token
│           └── models.rs    # HashResult data model
├── src/
│   ├── core/                # Business logic (UI-independent)
│   │   ├── native/              # Rust pydup_core bridge & Python fallback
│   │   ├── scanner/             # ScanWorker facade + split discovery/hash/incremental/similar-image stages
│   │   │   ├── __init__.py
│   │   │   ├── worker.py
│   │   │   └── ...
│   │   ├── cache_manager/       # CacheManager facade + split DB/schema/session/quarantine/jobs modules
│   │   │   ├── __init__.py
│   │   │   ├── database.py
│   │   │   └── ...
│   │   ├── history.py           # Undo/Redo transactions
│   │   ├── result_schema.py     # Result JSON v3 schema + compatibility loader
│   │   ├── result_groups.py     # Result group classification/risk/hardlink eligibility
│   │   ├── image_hash.py        # Similar image detection (pHash)
│   │   ├── document_hash.py     # Similar document detection (SimHash / PDF extraction)
│   │   ├── scan_types.py        # selection/exemption/review/collection types
│   │   ├── file_lock_checker.py # File lock detection
│   │   ├── preset_manager.py    # Scan preset management
│   │   └── empty_folder_finder.py # Empty folder detection
│   ├── ui/                  # GUI layer
│   │   ├── main_window.py       # Main window
│   │   ├── main_window_parts/   # SOLID split modules for main window responsibilities
│   │   │   ├── ui_shell/            # build/translate/theme/navigation submixins
│   │   │   ├── scan_flow/           # folders/lifecycle/config submixins
│   │   │   ├── results_flow/        # rendering/selection/filtering/preview/actions/persistence
│   │   │   ├── settings_flow/       # persistence/session_restore/dialogs/cache_settings
│   │   │   ├── tools_flow/          # quarantine/operations/rules/hardlink
│   │   │   ├── schedule_flow.py
│   │   │   └── typing_contract/     # split host protocols + aggregate contract
│   │   ├── theme/               # palette/token/stylesheet split
│   │   ├── empty_folder_dialog.py
│   │   ├── controllers/         # UI orchestration controllers
│   │   │   ├── scan_controller.py
│   │   │   ├── scheduler_controller.py
│   │   │   ├── watch_controller.py
│   │   │   ├── ops_controller.py
│   │   │   ├── operation_flow_controller.py
│   │   │   ├── navigation_controller.py
│   │   │   ├── results_controller.py
│   │   │   └── preview_controller.py
│   │   ├── components/
│   │   │   ├── results_tree/    # Results tree facade + populate/filter/state split
│   │   │   ├── sidebar.py       # Sidebar navigation
│   │   │   └── toast.py         # Toast notifications
│   │   ├── pages/
│   │   │   ├── scan_page.py      # Scan page (UI)
│   │   │   ├── results_page.py   # Results page (UI)
│   │   │   ├── tools_page.py     # Tools page (UI)
│   │   │   ├── insights_page.py  # Insights page (UI)
│   │   │   └── settings_page.py  # Settings page (UI)
│   │   └── dialogs/
│   │       ├── preset_dialog.py
│   │       ├── exclude_patterns_dialog.py
│   │       ├── session_compare_dialog.py
│   │       ├── selection_rules_dialog.py
│   │       ├── preflight_dialog.py
│   │       ├── operation_log_dialog.py
│   │       └── shortcut_settings_dialog.py
│   └── utils/
│       └── i18n/                # split catalog_en/catalog_ko/service modules
```

---

## 📊 Performance Benchmark

Scan performance benchmark on 10,000 files (500 duplicate groups):

| Metric | Python Backend | Native Rust Backend | Improvement |
|---|---:|---:|---:|
| **Scan Time (`scan_time_sec`)** | **4.411 s** | **2.176 s** | **50.7% faster (2.03x speedup)** |
| **Tree Render Time (`render_time`)** | 0.960 s | 0.906 s | No UI rendering bottleneck |
| **Duplicate Group Accuracy** | 500 groups | 500 groups | 100% Identical |
| **Indexed Metadata Count** | 10,000 files | 10,000 files | 100% Identical |

---

## 📥 Installation

### Prerequisites
- Python 3.9 or higher
- Rust toolchain (if compiling native Rust core from source: `cargo`, `maturin`)

### Dependencies
| Package | Purpose |
|---------|---------|
| PySide6 | Qt GUI framework |
| pydup_core | Native Rust acceleration engine (PyO3 + Rayon + BLAKE2b) |
| imagehash | Similar image detection (pHash) |
| Pillow | Image processing |
| send2trash | Recycle Bin functionality |
| psutil | File lock process detection |
| watchdog | Real-time folder watching |
| pypdf | PDF text extraction for similar-document scan |

### Installation Steps

1. **Clone the Repository**
   ```bash
   git clone https://github.com/twbeatles/pyduplicate-finder.git
   cd pyduplicate-finder
   ```

2. **Create Virtual Environment (Recommended)**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **(Optional) Build Native Rust Core**
   ```powershell
   # Windows
   powershell -ExecutionPolicy Bypass -File scripts\build_rust_core.ps1
   ```
   *Note: If the native Rust core is not built, the app gracefully falls back to pure Python without error.*

---

## 📖 Usage Guide

### 1. Run the Program
```bash
python main.py
```

### (Optional) Run a headless CLI scan
```bash
python cli.py "D:/Data" "E:/Photos" --extensions jpg,png --output-json result.json --output-csv result.csv
```
- `--similarity-threshold` only accepts values in `0.0`~`1.0`. Out-of-range input is rejected with CLI error (`SystemExit 2`).
- When `--similar-image` or `--mixed-mode` is requested, missing `imagehash`/`Pillow` dependencies cause immediate fail-fast exit.
- `--mixed-mode` implicitly enables the similar-image pass (no separate `--similar-image` flag required).
- `--watch` and `--post-cleanup-empty-dirs` are GUI-only workflows; in CLI they fail fast with exit code `2` and a clear stderr message.

### (Optional) Run strict-mode CLI scan with telemetry
```bash
python cli.py "D:/Data" --strict-mode --strict-max-errors 0 --output-json result.json
```

### 2. Search Settings
- **Add Location**: Use "Add Folder" or Drag & Drop to add search targets.
- **Filter Options**:
    | Option | Description |
    |--------|-------------|
    | Filename Only | Compare names only, skip content hashing (ultra-fast) |
    | Similar Image Detection | Analyze visual similarity (0.1~1.0 threshold) |
    | Strict Mode | Marks scan as `partial` when error count exceeds threshold |
    | Use Recycle Bin | Move to Recycle Bin instead of permanent delete |
    | Skip hidden/system files | Skips dotfiles and OS metadata files |
    | Follow symlinks | Follows symbolic links (loop detection enabled) |
    | Include patterns | If set, only matching files are scanned |
    | Exclude Patterns | Set wildcard patterns (*, ?) to skip during scan |

### 3. Scan & Review
- **Start Scan**: Click to begin high-speed scanning.
- **Cancel Scan**: Stop anytime during scanning.
- **Resume Scan**: On relaunch, the app asks whether to resume an interrupted scan.
- **Review Results**:
    - View duplicate groups in the left tree view
    - Use `+`/`-` buttons to expand/collapse all
    - Click a file to see **Preview** in the right panel

### 4. Organize & Delete
- **Auto Select (Smart)**: Keep oldest file as original, select rest for deletion
- **Delete Selected**: Safely delete after lock detection
- **Undo**: Press `Ctrl+Z` to restore (except when using Recycle Bin)

### 5. Advanced Features
| Feature | Description |
|---------|-------------|
| Save/Load Results | Manage scan results as JSON files |
| Preset Management | Save/load frequently used configurations |
| Shortcut Settings | Customize keyboard shortcuts |
| Find Empty Folders | Scan and batch delete empty folders |
| Quarantine | Restore/purge files deleted in undoable mode |
| Safelist / Ignore Management | CRUD/search for path/hash/glob exemptions, plus result-tree context actions |
| Selection Rules | Pattern-based KEEP/DELETE auto-selection |
| Operations Log | Operation history with details + CSV/JSON export |
| Operation Plan Save/Load | Save selected delete plans as JSON and validate path/size/mtime on load |
| Result Risk Badges | Group risk badges plus destructive-action preflight risk summary |
| Hardlink Consolidation | (Advanced) Save disk space via hardlinks |
| Scheduled Scan Snapshot | Scheduled runs use saved config snapshot (`scan_jobs.config_json`); if some folders are missing, run valid folders only; if all are missing, mark run as `skipped(no_valid_folders)` |
| Multi-job Scheduling | Create/edit/delete/run named jobs and inspect recent run history |
| Watch Mode | Queue debounce-based incremental rescans after folder changes |
| Insights | Review recent sessions, reclaim estimates, failure rate, quarantine usage, and scheduled runs |
| Session Compare | Inspect `new`, `changed`, `revalidated` delta markers in a dedicated dialog |
| Quarantine Filtering/Pagination | Manage large quarantine sets with status/date/size/path filters and page navigation |
| Cache Retention Policy | Configure session keep count (`cache/session_keep_latest`) and hash cache retention days (`cache/hash_cleanup_days`) and apply immediately |
| Headless CLI Scan | Run scans without GUI and export JSON/CSV outputs |

### Result JSON format (manual/scheduled/CLI)
- New format: `{"meta": {...}, "results": {...}}`
- Backward compatible loading: legacy `{"<group_key>": [...]}` is still accepted.
- `meta` includes:
  - `scan_status` (`completed` or `partial`)
  - `metrics` (`files_scanned`, `files_hashed`, `files_skipped_error`, `files_skipped_locked`, `errors_total`)
  - `warnings` (for example `strict_mode_threshold_exceeded`)

---

## 🏗️ Building Executable

Create a standalone `.exe` file:
```bash
pyinstaller PyDuplicateFinder.spec
```
Output: `dist/PyDuplicateFinderPro.exe`

---

## 🔧 Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.9+ |
| GUI | PySide6 (Qt for Python) |
| Caching | SQLite (WAL mode) |
| Hashing | BLAKE2b |
| Image Analysis | pHash (imagehash) |
| Parallel Processing | concurrent.futures.ThreadPoolExecutor |

---

## 🤝 Contributing
Contributions are welcome! Performance improvements and bug reports are always appreciated.

## 📝 License
MIT License

## ✅ Implementation Status (2026-02-26)

The following items are now implemented in code:

- Advanced scan options exposed in GUI: mixed mode, duplicate-folder detection, incremental rescan, baseline session selector
- CLI extensions: `--mixed-mode`, `--detect-folder-dup`, `--incremental-rescan`, `--baseline-session`
- CLI validation: `--similarity-threshold` is constrained to `0.0~1.0` (out-of-range input rejected)
- Delete dry-run summary: selected/visible counts, estimated reclaim size, per-group preview before destructive flow
- Retry scope expansion: retries now cover hardlink/restore/purge failures in addition to delete failures
- i18n cleanup: core hardcoded messages (Undo/Redo/Quarantine/History) migrated to translation keys
- Scheduled scan (baseline): daily/weekly scheduling from Settings with optional JSON/CSV auto-export
- Scheduled execution policy: run from saved snapshot (`scan_jobs.config_json`) rather than current UI state; folder handling is `run valid folders only / all missing -> skipped(no_valid_folders)`
- Results/export enhancements: better `FOLDER_DUP` labels and CSV columns `group_kind`, `bytes_reclaim_est`, `baseline_delta`
- Unified result JSON schema path introduced; the current save target is `version=3`, while the loader supports legacy GUI/legacy CLI/v2/v3 formats
- Safer quarantine path: DB insert failure now triggers rollback to original path (prevents orphaned files)
- Preview concurrency hardening: cache updates are lock-protected (`RLock`) and preview signal is connected with `Qt.QueuedConnection`
- Preset schema alignment: writes `schema_version=2` and upgrades old presets by merging missing defaults
- Strict schedule validation: invalid `HH:MM (00:00-23:59)` input is blocked with user-facing error
- Cache/session cleanup policy: startup cleanup now follows configurable `session_keep_latest` and `hash_cleanup_days`
- Incremental CSV detail: file-level `baseline_delta` now records `new|changed|revalidated`
- Similar-image dependency policy: GUI/CLI both fail fast when required deps are unavailable
- Architecture split phase 2:
  - `src/core/scan_engine.py` + `src/ui/controllers/scan_controller.py` + `src/ui/controllers/scheduler_controller.py`
  - Operation flow extracted to `src/ui/controllers/operation_flow_controller.py`
  - Navigation flow extracted to `src/ui/controllers/navigation_controller.py`

Planned follow-up refactors:

- Shrink `legacy.py` delegation layers into thinner service/domain objects over time
- Packageize `schedule_flow.py` too if its size/ownership warrants the same pattern

## ✅ Implementation Status (2026-02-28)

The duplicate scan audit plan is now fully implemented:

- Cancel reliability hardened across full-hash, folder-duplicate, and mixed-mode stages.
  - Cancel now consistently emits `scan_cancelled`, stores session as `paused`, and avoids false `scan_finished`.
- Protected root folder guard added at scan-root level.
  - Protected roots are skipped entirely with explicit progress/status message.
- Extension normalization fixed.
  - `.txt` and `txt` now behave identically.
- Error telemetry added and exposed to UI/CLI/exported JSON.
  - Hashing and similar-image worker errors are no longer silently swallowed.
- Strict mode added (UI + CLI).
  - `--strict-mode`, `--strict-max-errors`
  - threshold exceeded => scan status `partial` (results still returned, CLI exit code remains `0`).
- Scan config hash canonicalization added for better baseline reuse.
  - normalized/sorted folders, extensions, include/exclude patterns.
- Baseline policy unchanged by design.
  - only `completed` sessions are baseline candidates (`partial` excluded).
- Manual/scheduled JSON export updated with `meta` while preserving backward compatibility on load.

## ✅ Implementation Status (2026-03-09)

- Main window was split by SOLID responsibilities while preserving public compatibility:
  - `src/ui/main_window.py` is now a lightweight assembly/compat layer.
  - Feature logic moved to `src/ui/main_window_parts/{ui_shell,scan_flow,results_flow,settings_flow,tools_flow}/` packages plus `schedule_flow.py`.
- Dynamic widget typing contract was added:
  - `src/ui/main_window_parts/typing_contract/` defines `TYPE_CHECKING` attributes and host protocols.
  - `reportAttributeAccessIssue` remains strict; issues are fixed in code rather than relaxed in config.
- Pylance regression guardrails were locked:
  - Added `pyrightconfig.json` (scope: `src`, `tests`, `cli.py`, `main.py`; Python 3.14; key diagnostics set to `error`).
- Encoding regression guardrails were strengthened:
  - Added `.editorconfig` UTF-8/EOL rules.
  - `tests/test_source_encoding_integrity.py` checks UTF-8 decode, replacement-char bans, and known mojibake patterns.
- Baseline checks:
  - `pyright src tests cli.py main.py` remains at `0 errors`.
  - (As of 2026-03-09) full `pytest` could still terminate with `-1073740791`; this was tracked as a pre-existing baseline issue.

## ✅ Implementation Status (2026-03-11)

- CLI lifecycle hardening:
  - CLI now runs `ScanWorker.run()` synchronously instead of creating a dedicated Qt event loop.
  - This reduces process-global Qt lifecycle conflicts in CLI/GUI mixed usage.
- CLI mixed-mode behavior alignment:
  - `--mixed-mode` now always implies the similar-image pass (`--similar-image` is no longer required separately).
- File lock detection hardening:
  - Windows lock checks were updated to avoid zero-byte false-unlocked behavior.
- Incremental rescan reliability:
  - Deep subtree skipping based only on directory mtime was removed to reduce missed-file risk after baseline scans.
- Regression verification:
  - Full `pytest -q` baseline: `104 passed`.

## ✅ Implementation Status (2026-03-18)

- Large single-module packageization completed:
  - `src/core/cache_manager/`: `database`, `schema`, `sessions`, `scan_storage`, `operations`, `quarantine`, `hash_cache`, `jobs`
  - `src/core/scanner/`: `worker`, `discovery`, `hashing`, `incremental`, `similar_images`, `folder_duplicates`, `filters`, `metrics`, `state`
  - `src/utils/i18n/`: `catalog_en`, `catalog_ko`, `catalogs`, `service`
  - `src/ui/theme/`: `palettes`, `tokens`, `stylesheet`
  - `src/ui/components/results_tree/`: `populate`, `filtering`, `state`, `appearance`, `constants`
- Main-window responsibility split phase 2 completed:
  - `src/ui/main_window_parts/{ui_shell,scan_flow,results_flow,settings_flow,tools_flow}/` converted to submixin packages
  - `src/ui/main_window_parts/typing_contract/` split into `scan/results/settings/tools/ui_shell/schedule/navigation/operation_flow` host protocols
- Public import compatibility preserved:
  - `CacheManager`, `ScanWorker`, `IMAGE_HASH_AVAILABLE`, `I18n`, `strings`, `ModernTheme`, `DuplicateFinderApp`, `ResultsTreeWidget`
- Regression/stability guardrails:
  - added `tests/test_public_api_facades.py`
  - current full baseline: `pytest -q` -> `111 passed`
- Packaging alignment:
  - `PyDuplicateFinder.spec` now uses `collect_submodules(...)` for the packageized module trees

## Performance Refactor Notes (2026-02)

- Hashing hot path now consumes pre-collected `(path, size, mtime)` tuples to avoid repeated `os.stat` calls.
- Hash/session cache lookup is processed in chunks to reduce memory spikes on large scans.
- Results tree rendering accepts injected metadata and applies filtering inside the widget for faster UI response.
- Selection persistence now uses delta upsert/delete instead of full-table rewrite on each change.
- Operation restore/purge flows now use batch quarantine item fetch with throttled progress updates.

## Performance Refactor Notes (2026-02-21)

- Added `ResultsTreeWidget.files_checked_delta(added, removed, selected_count)` while preserving `files_checked(list)` for compatibility.
- Results tree now uses dynamic batch rendering, filter short-circuit, and cached group summaries for faster large-result interaction.
- Introduced `ResultsController` and `PreviewController` to split selection/preview orchestration from `main_window` and reduce UI-thread blocking.
- Preview loading now uses async workers plus LRU caching to keep scrolling/selection responsive.
- Scanner now pre-compiles include/exclude matchers, throttles session progress DB writes independently from UI progress emits, and deduplicates session hash batch writes.
- Folder-duplicate full-hash computation now reuses the parallel hash pipeline instead of per-file synchronous hashing.
- Final `file_meta` is trimmed to result-referenced paths to lower memory peak on large scans.
- Operation queue now uses throttled progress for trash deletes and reduces repeated `exists/getsize/getmtime` calls in trash/hardlink paths.
- CSV export supports optional `file_meta` injection to avoid repeated filesystem stats when metadata is already available.

## Benchmark & Regression Guardrails

- Added deterministic performance regression tests:
  - `tests/test_scanner_perf_path.py`
  - `tests/test_results_tree_perf.py`
  - `tests/test_exporting.py`
  - `tests/test_main_window_selection_perf.py`
- Added local benchmark script (JSON output): `tests/benchmarks/bench_perf.py`

Example:

```bash
python tests/benchmarks/bench_perf.py --files 200000 --groups 5000 --output bench_perf.json
```

## Documentation Sync (2026-04-12)

- Weekly first-run scheduling semantics were corrected.
  - A newly enabled weekly job now waits for the next configured weekday/time slot instead of firing immediately when the configured day already passed.
- Zero-byte duplicates are now included only when `min_size_kb` is `0`.
- Result JSON `version=2` remains backward-compatible and can now persist `meta.selected_paths`, `meta.file_meta` (`size`, `mtime`, `exists`), and `meta.baseline_delta_map` (`new|changed|revalidated`).
- Loading saved JSON in the GUI now restores checked items, file metadata, missing-file badges, and incremental delta markers.
- Scheduled auto-export no longer reports a false full success.
  - If the scan completed but JSON/CSV export failed, the run is finalized as `partial`.
  - Run messages may include structured suffixes such as `missing_folders:1` and `export_failed:csv`.
- CLI `--quiet` now suppresses all successful stdout, including progress lines, completion summary, and `Saved JSON/CSV` messages. Errors and cancellation still go to `stderr`.
- Quarantine retention now walks the full quarantine set in batches, so age/size cleanup is no longer limited to the first 5,000 rows.
- Packaging review note: `PyDuplicateFinder.spec` already covers the modules touched by this update, so no hidden-import change was required.
- Current regression baseline: `pytest -q` -> `122 passed`.

## Documentation Sync (2026-04-14)

- Database schema version is now `6`.
  - Added `scan_exemptions`, `review_marks`, and `file_signatures`.
- Result JSON now saves as `version=3`.
  - Adds file-level state: `selection_reason`, `exemption_status`, `review_state`, `collection_role`, `baseline_delta`.
  - Loader remains compatible with legacy / v2 / v3.
- Selection policy pipeline was unified.
  - Explicit rules -> safelist -> collection role -> attribute priority -> fallback keep-one.
- Multi-job scheduler UI is now implemented.
  - Create, edit, delete, and run named jobs.
  - Recent run history is shown per job.
- Added the `Insights` page.
  - Shows recent sessions, reclaim estimates, failure rate, quarantine usage, and scheduled run history.
- Added a `Session Compare` dialog and delta filter for incremental scans.
- Watch mode is now connected to real rerun behavior.
  - Uses `watchdog` when available and falls back to polling when unavailable.
  - File changes detected during an active scan are coalesced into a single pending rerun.
- Post-delete empty-folder cleanup is now executed from the operation flow and logged separately.
- Similar-document detection is now available for `.txt`, `.md`, `.csv`, `.json`, `.py`, and `.pdf`.
  - `pypdf` is used for PDF text extraction.
- Automated baseline in this workspace at that point:
  - `pytest -q` -> `131 passed, 1 skipped`

## Documentation Sync (2026-04-28)

- Database schema version is now `7`.
  - Added `scan_file_state` so DB session restore now matches JSON v3 restore for `file_meta`, existence, selection reason, exemption status, review state, collection role, and baseline delta.
- Restored the `pyright src tests cli.py main.py` baseline.
  - Added core `CacheManager`/`ScanWorker` mixin host protocols, filled UI host protocol gaps, and kept optional `watchdog` runtime fallback while satisfying static analysis.
- Result group classification is centralized in `src/core/result_groups.py`.
  - UI badges, CSV `group_type/group_kind`, and hardlink eligibility now use the same classifier.
  - `NAME_ONLY`, `FOLDER_DUP`, `similar_*`, and `doc_similar_*` are excluded from hardlink consolidation.
- Safelist / Ignore policy is consistent end-to-end.
  - Canonical status is `"safelisted"`; legacy `"safelist"` is normalized on JSON/DB load.
  - Incremental baseline-known paths and cached-resume scans now apply the same ignore/exemption/metadata restore policy as normal scans.
  - Content-hash exemptions use exact full BLAKE2b hashes only; content-hash actions are disabled for name-only/similar groups.
- User-facing workflow additions:
  - Tools Safelist/Ignore manager, result-tree exemption context actions, folder Path/Role table, Session Compare actions, risk badges/preflight summary, `operation_plan` JSON v1 save/load, and Quarantine filters/pagination.
  - Scheduled/watch history splits `missing_folders`, `export_failed`, and `watch_events` into structured columns.
- CLI unsupported options now fail fast.
  - `--watch` and `--post-cleanup-empty-dirs` return exit code `2` with a clear stderr message.
- Packaging/local artifact alignment:
  - `PyDuplicateFinder.spec` explicitly includes new runtime helpers (`src.core.result_groups`, `src.ui.history_messages`) as hidden imports and collects `watchdog`/`pypdf` only when installed.
  - `.gitignore` ignores local DB sidecars, result CSV/JSON files, `operation_plan` JSON files, and temp artifacts.
- Current automated baseline in this workspace:
  - `pyright src tests cli.py main.py` -> `0 errors, 0 warnings`
  - `pytest -q` -> `145 passed`
