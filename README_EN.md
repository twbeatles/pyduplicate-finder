# 🔍 PyDuplicate Finder Pro

**PyDuplicate Finder Pro** is a high-performance duplicate file management tool based on Python (PySide6). It uses advanced multi-threading and smart caching technology to quickly and accurately scan for duplicate files even in large file systems, and provides safe Undo capabilities.

---

## ✨ Key Features

### 🚀 High Performance
- **Parallel Scanning (Multithreading)**: `ScanWorker` utilizes all CPU cores to calculate file hashes in parallel, delivering speeds over 5x faster than conventional methods.
- **Smart Caching**: Uses `SQLite WAL` mode to cache file hashes. Re-scanning previously analyzed files is nearly instantaneous.
- **Optimized I/O**: Uses large buffers (1MB) to maximize disk read speeds.

### 🛡️ Safety & Precision
- **System Protection**: Automatically excludes critical Windows/Linux system folders (e.g., Windows, Program Files) to prevent accidental damage.
- **Physical Duplicate Prevention (Inode Check)**: Prevents counting symbolic links or shortcuts as duplicates of the same physical file.
- **Safe Delete & Robust Undo**: Supports asynchronous delete/restore operations, keeping the UI responsive even when processing thousands of files.
- **Byte-by-Byte Comparison**: Optional 100% accurate comparison mode to eliminate any risk of hash collisions.

### 🎨 Modern UI & User Experience
- **Intuitive Design**: Modern flat design with Light and Dark mode support.
- **Usability**: Right-click context menu (Open, Open Folder, Copy Path), Drag & Drop support.
- **Empty Folder Finder**: Recursively finds and cleans up empty directories.
- **Export Results**: Save found duplicate groups to a CSV file for external management.
- **Preview**: Built-in preview for images and text/code files (with monospace font).
- **Multi-language Support**: Fully supports English and Korean interfaces.

---

## 📥 Installation

### Prerequisites
- Python 3.8 or higher

### Installation Steps

1. **Clone the Repository**
   ```bash
   git clone https://github.com/your-username/PyDuplicateFinder.git
   cd PyDuplicateFinder
   ```

2. **Create Virtual Environment (Recommended)**
   - Windows:
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```
   - macOS/Linux:
     ```bash
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

### 2. Search Settings
- **Add Location**: Use "Add Folder" or Drag & Drop to add search targets.
- **Filter Options**:
    - `Extensions`: Limit search to specific extensions (e.g., `jpg, png, mp4`). Leave empty for all.
    - `Min Size`: Ignore files smaller than a specific size.
    - `System Folder Protection`: Enabled by default (recommended).

### 3. Scan & Check Duplicates
- **Start Scan**: Click to begin high-speed scanning.
- **Check Results**:
    - View duplicate groups in the left tree view.
    - Click a file to see a **Preview** in the right panel.

### 4. Organize & Delete
- **Auto Select (Smart)**: Automatically selects files to keep (e.g., "Oldest Modified") in each group.
- **Delete Selected**: Moves selected duplicates to the Trash (or deletes depending on OS).
- **Undo**: Made a mistake? Click `Undo` in the toolbar (Ctrl+Z) to restore immediately.

### 5. Find Empty Folders
- Click the `Find Empty Folders` icon in the toolbar to scan for and clean up empty directories within your search targets.

---

## 🏗️ Building Executable
To create a standalone `.exe` file:
```bash
pyinstaller PyDuplicateFinder.spec
```
The output file will be located at `dist/PyDuplicateFinderPro.exe`.

---

## 🤝 Contributing
Contributions are welcome! If you have performance improvement ideas or bug reports, please open an issue.

## 📝 License
MIT License
