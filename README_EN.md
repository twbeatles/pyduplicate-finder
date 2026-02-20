# 🔍 PyDuplicate Finder Pro

[![한국어](https://img.shields.io/badge/lang-한국어-red.svg)](README.md)

**PyDuplicate Finder Pro** is a high-performance duplicate file management tool built with Python (PySide6). It leverages advanced multi-threading and smart caching to quickly and accurately scan for duplicate files even in large file systems, providing safe Undo capabilities.

---

## ✨ Key Features

### 🚀 High Performance
- **Ultra-Fast Scanning**: Recursive `os.scandir` engine for significantly faster file traversal compared to `os.walk`.
- **Optimized Hashing (BLAKE2b)**: Uses `BLAKE2b` algorithm optimized for 64-bit systems, faster and more secure than MD5.
- **Smart Caching & Batch Processing**: `SQLite WAL` mode with batch processing handles hundreds of thousands of files seamlessly.
- **Resume Interrupted Scans**: File lists and hash progress are cached so scans can resume after a restart.
- **Smooth UI**: Incremental rendering of results keeps the app responsive even with massive datasets.

### 🛡️ Safety & Precision
- **System Protection**: Automatically skips critical system folders (Windows, Program Files, etc.) to prevent accidental damage.
- **Physical Duplicate Prevention (Inode Check)**: Prevents counting symbolic links or shortcuts as duplicates of the same physical file.
- **Safe Delete & Robust Undo**: Asynchronous delete/restore operations keep UI responsive when processing thousands of files.
- **Recycle Bin Option**: Move files to system Recycle Bin instead of permanent deletion.
- **File Lock Detection**: Automatically detects files in use by other processes before deletion.
- **Persistent Quarantine + Retention**: Undoable deletes are kept in persistent Quarantine and cleaned by configured retention rules (age/size).

### 🎨 Modern UI & User Experience
- **Multiple Scan Modes**: 
    - **Similar Image Detection (pHash)**: Finds visually similar images (resized, recompressed, etc.)
    - **Filename Comparison**: Quickly finds files with the same name regardless of content.
- **Exclude Patterns**: Skip unwanted folders/files like `node_modules`, `.git`, `*.tmp` using wildcard patterns (*, ?).
- **Scan Presets**: Save and load frequently used scan configurations.
- **Result Save/Load**: Export scan results to JSON and reload later.
- **Session Restore**: Detects the latest session and lets you resume or start a new scan.
- **Intuitive Tree View**: Expand/collapse all groups, right-click context menu for quick actions.
- **Custom Shortcuts**: Configure keyboard shortcuts for all functions.
- **Multi-language Support**: Full Korean and English interface support.

### 🧰 Tools
- **Quarantine Management**: Files deleted in undoable mode are moved to Quarantine; restore or permanently purge them later.
- **Selection Rules**: Define ordered KEEP/DELETE rules using fnmatch-style wildcards and apply them to groups/results.
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
├── claude.md                # AI context (Claude)
├── gemini.md                # AI context (Gemini)
├── src/
│   ├── core/                # Business logic (UI-independent)
│   │   ├── scanner.py           # Multi-threaded scan engine
│   │   ├── cache_manager.py     # SQLite cache management
│   │   ├── history.py           # Undo/Redo transactions
│   │   ├── file_ops.py          # Async file operations
│   │   ├── image_hash.py        # Similar image detection (pHash)
│   │   ├── file_lock_checker.py # File lock detection
│   │   ├── preset_manager.py    # Scan preset management
│   │   └── empty_folder_finder.py # Empty folder detection
│   ├── ui/                  # GUI layer
│   │   ├── main_window.py       # Main window
│   │   ├── theme.py             # Theme stylesheets
│   │   ├── empty_folder_dialog.py
│   │   ├── controllers/         # UI orchestration controllers
│   │   │   ├── scan_controller.py
│   │   │   ├── scheduler_controller.py
│   │   │   ├── ops_controller.py
│   │   │   ├── operation_flow_controller.py
│   │   │   └── navigation_controller.py
│   │   ├── components/
│   │   │   ├── results_tree.py  # Results tree widget
│   │   │   ├── sidebar.py       # Sidebar navigation
│   │   │   └── toast.py         # Toast notifications
│   │   ├── pages/
│   │   │   ├── scan_page.py      # Scan page (UI)
│   │   │   ├── results_page.py   # Results page (UI)
│   │   │   ├── tools_page.py     # Tools page (UI)
│   │   │   └── settings_page.py  # Settings page (UI)
│   │   └── dialogs/
│   │       ├── preset_dialog.py
│   │       ├── exclude_patterns_dialog.py
│   │       ├── selection_rules_dialog.py
│   │       ├── preflight_dialog.py
│   │       └── operation_log_dialog.py
│   │       └── shortcut_settings_dialog.py
│   └── utils/
│       └── i18n.py              # Internationalization strings
```

---

## 📥 Installation

### Prerequisites
- Python 3.9 or higher

### Dependencies
| Package | Purpose |
|---------|---------|
| PySide6 | Qt GUI framework |
| imagehash | Similar image detection (pHash) |
| Pillow | Image processing |
| send2trash | Recycle Bin functionality |
| psutil | File lock process detection |

### Installation Steps

1. **Clone the Repository**
   ```bash
   git clone https://github.com/your-username/PyDuplicateFinder.git
   cd PyDuplicateFinder
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

### 2. Search Settings
- **Add Location**: Use "Add Folder" or Drag & Drop to add search targets.
- **Filter Options**:
    | Option | Description |
    |--------|-------------|
    | Filename Only | Compare names only, skip content hashing (ultra-fast) |
    | Similar Image Detection | Analyze visual similarity (0.1~1.0 threshold) |
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
| Selection Rules | Pattern-based KEEP/DELETE auto-selection |
| Operations Log | Operation history with details + CSV/JSON export |
| Hardlink Consolidation | (Advanced) Save disk space via hardlinks |
| Headless CLI Scan | Run scans without GUI and export JSON/CSV outputs |

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

## ✅ Implementation Status (2026-02-20)

The following items are now implemented in code:

- Advanced scan options exposed in GUI: mixed mode, duplicate-folder detection, incremental rescan, baseline session selector
- CLI extensions: `--mixed-mode`, `--detect-folder-dup`, `--incremental-rescan`, `--baseline-session`
- Delete dry-run summary: selected/visible counts, estimated reclaim size, per-group preview before destructive flow
- Retry scope expansion: retries now cover hardlink/restore/purge failures in addition to delete failures
- i18n cleanup: core hardcoded messages (Undo/Redo/Quarantine/History) migrated to translation keys
- Scheduled scan (baseline): daily/weekly scheduling from Settings with optional JSON/CSV auto-export
- Results/export enhancements: better `FOLDER_DUP` labels and CSV columns `group_kind`, `bytes_reclaim_est`, `baseline_delta`
- Architecture split phase 2:
  - `src/core/scan_engine.py` + `src/ui/controllers/scan_controller.py` + `src/ui/controllers/scheduler_controller.py`
  - Operation flow extracted to `src/ui/controllers/operation_flow_controller.py`
  - Navigation flow extracted to `src/ui/controllers/navigation_controller.py`

Planned follow-up refactors:

- Further decomposition of heavy logic from `src/core/scanner.py`
- Broader controller extraction from `src/ui/main_window.py`

## Performance Refactor Notes (2026-02)

- Hashing hot path now consumes pre-collected `(path, size, mtime)` tuples to avoid repeated `os.stat` calls.
- Hash/session cache lookup is processed in chunks to reduce memory spikes on large scans.
- Results tree rendering accepts injected metadata and applies filtering inside the widget for faster UI response.
- Selection persistence now uses delta upsert/delete instead of full-table rewrite on each change.
- Operation restore/purge flows now use batch quarantine item fetch with throttled progress updates.
