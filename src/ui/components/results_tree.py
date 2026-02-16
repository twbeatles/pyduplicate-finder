from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt, Signal, QTimer, Slot
from PySide6.QtGui import QAction, QCursor, QBrush, QColor, QFont
from src.utils.i18n import strings
from src.ui.theme import ModernTheme
from datetime import datetime
import os


_ROLE_BASE = int(Qt.ItemDataRole.UserRole)
_ROLE_PATH = _ROLE_BASE
_ROLE_GROUP_KEY = _ROLE_BASE + 1
_ROLE_EXISTS = _ROLE_BASE + 2
_ROLE_GROUP_BASE_LABEL = _ROLE_BASE + 3
_ROLE_SIZE_BYTES = _ROLE_BASE
_ROLE_LOWER_PATH = _ROLE_BASE + 4

class ResultsTreeWidget(QTreeWidget):
    """
    Custom TreeWidget for displaying duplicate scan results.
    Handles batch population, formatting, and context menus.
    Enhanced with improved styling and row heights.
    """
    files_checked = Signal(list)  # Emits list of checked file paths
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels([
            strings.tr("col_path"),
            strings.tr("col_size"),
            strings.tr("col_mtime"),
            strings.tr("col_ext")
        ])
        
        # Enhanced column setup
        self.setColumnWidth(0, 500)
        self.setColumnWidth(1, 100)
        self.setColumnWidth(2, 140)
        self.setColumnWidth(3, 80)
        
        # Enable column resizing
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setAlternatingRowColors(True)
        self.setIndentation(24)
        self.setAnimated(True)
        self.setUniformRowHeights(True)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        
        # Batch processing state
        self._populate_timer = QTimer(self)
        self._populate_timer.timeout.connect(self._process_batch)
        self._result_iterator = None
        self._rendered_count = 0
        self._total_results = 0
        self._selected_paths = set()
        self._checked_paths = set()
        self._suppress_item_changed = False
        self._file_meta_map = {}
        self._existence_map = {}
        
        self.current_theme_mode = "light"
        
        # Extension-based icons for file types
        self.EXTENSION_ICONS = {
            # Images
            'jpg': '🖼️', 'jpeg': '🖼️', 'png': '🖼️', 'gif': '🖼️', 
            'bmp': '🖼️', 'webp': '🖼️', 'svg': '🖼️', 'ico': '🖼️',
            # Videos
            'mp4': '🎬', 'mkv': '🎬', 'avi': '🎬', 'mov': '🎬',
            'wmv': '🎬', 'flv': '🎬', 'webm': '🎬',
            # Audio
            'mp3': '🎵', 'wav': '🎵', 'flac': '🎵', 'aac': '🎵',
            'ogg': '🎵', 'wma': '🎵', 'm4a': '🎵',
            # Documents
            'pdf': '📕', 'doc': '📘', 'docx': '📘', 'xls': '📗',
            'xlsx': '📗', 'ppt': '📙', 'pptx': '📙', 'txt': '📝',
            # Archives
            'zip': '📦', 'rar': '📦', '7z': '📦', 'tar': '📦', 'gz': '📦',
            # Code
            'py': '🐍', 'js': '📜', 'html': '🌐', 'css': '🎨', 'json': '📋',
        }

        # Connect internal signals
        self.itemChanged.connect(self._on_item_changed)
    
    def _get_file_icon(self, filepath):
        """Get appropriate emoji icon based on file extension."""
        ext = os.path.splitext(filepath)[1].lower().lstrip('.')
        return self.EXTENSION_ICONS.get(ext, '📄')
    
    def set_theme_mode(self, mode):
        """Updates the theme mode and refreshes item colors if needed."""
        self.current_theme_mode = mode
        colors = ModernTheme.get_palette(mode)
        
        # Re-apply colors to all top-level items (groups)
        root = self.invisibleRootItem()
        bg_color = QColor(colors['group_bg'])
        fg_color = QColor(colors['group_fg'])
        
        for i in range(root.childCount()):
            item = root.child(i)
            for col in range(4):
                item.setBackground(col, QBrush(bg_color))
                item.setForeground(col, QBrush(fg_color))

    def populate(self, results, selected_paths=None, file_meta=None, existence_map=None):
        """
        Populate the tree with scan results (batched).
        results: dict { (hash, size, type): [paths] }
        """
        # Issue #R1: Stop any ongoing batch rendering before clearing
        self._populate_timer.stop()
        
        self.clear()
        if not results:
            return

        self._selected_paths = set(selected_paths or [])
        self._checked_paths = set(self._selected_paths)
        self._file_meta_map = dict(file_meta or {})
        self._existence_map = dict(existence_map or {})
        self._suppress_item_changed = True
        self._result_iterator = iter(results.items())
        self._rendered_count = 0
        self._total_results = len(results)
        
        # Start batch processing
        self._populate_timer.start(0)

    def _format_reclaim(self, bytes_total: int) -> str:
        try:
            b = int(bytes_total or 0)
        except Exception:
            b = 0
        return self._format_size(b)

    def _update_group_summary(self, group_item: QTreeWidgetItem) -> None:
        """Update group header text based on current check states."""
        if not group_item:
            return

        total = int(group_item.childCount() or 0)
        if total <= 0:
            return

        checked = 0
        reclaim = 0
        keep_name = ""
        missing = 0

        for j in range(total):
            child = group_item.child(j)
            if not child:
                continue
            p = child.data(0, _ROLE_PATH)
            exists = bool(child.data(0, _ROLE_EXISTS))
            if not exists:
                missing += 1
            if child.checkState(0) == Qt.CheckState.Checked:
                checked += 1
                try:
                    reclaim += int(child.data(1, _ROLE_SIZE_BYTES) or 0)
                except Exception:
                    pass
            else:
                if not keep_name and p:
                    try:
                        keep_name = os.path.basename(str(p))
                    except Exception:
                        keep_name = ""

        unchecked = total - checked

        # Preserve the base label stored on the group item.
        base = group_item.data(0, _ROLE_GROUP_BASE_LABEL) or group_item.text(0)
        base = str(base)

        suffix_parts = []
        if keep_name and unchecked == 1 and checked > 0:
            suffix_parts.append(strings.tr("label_keep").format(name=keep_name))
        if checked > 0 and reclaim > 0:
            suffix_parts.append(strings.tr("label_reclaim").format(size=self._format_reclaim(reclaim)))
        if missing > 0:
            suffix_parts.append(strings.tr("badge_missing_count").format(count=missing))

        suffix = "" if not suffix_parts else "  •  " + "  |  ".join(suffix_parts)
        group_item.setText(0, base + suffix)

    def _process_batch(self):
        BATCH_SIZE = 50
        count = 0

        if self._result_iterator is None:
            self._populate_timer.stop()
            self._suppress_item_changed = False
            return
        
        try:
            while count < BATCH_SIZE:
                key, paths = next(self._result_iterator)
                self._add_group_item(key, paths)
                count += 1
                self._rendered_count += 1
            
        except StopIteration:
            self._populate_timer.stop()
            self._suppress_item_changed = False
            # Ensure group headers reflect initial selection state.
            try:
                root = self.invisibleRootItem()
                for i in range(root.childCount()):
                    self._update_group_summary(root.child(i))
            except Exception:
                pass
            
    def _add_group_item(self, key, paths):
        """Add a duplicate group to the tree."""
        # Parse key to get hash/name label and mode flags
        hash_str = "???"
        is_name_only = False
        is_similar = False
        is_byte_compare = False
        if isinstance(key, (tuple, list)) and key:
            if key[0] == "NAME_ONLY":
                is_name_only = True
                if len(key) > 1:
                    hash_str = str(key[1])
            else:
                for part in key:
                    if isinstance(part, str) and part.startswith("similar_"):
                        is_similar = True
                        group_id = part.split("_", 1)[1] if "_" in part else part
                        hash_str = strings.tr("label_similar_group").format(id=group_id)
                        break
                if hash_str == "???":
                    for part in key:
                        if not isinstance(part, int):
                            hash_str = str(part)
                            break
            is_byte_compare = any(
                isinstance(part, str) and part.startswith("byte_") for part in key
            )

        # Determine group size from actual files (supports name-only/similar mixed sizes)
        size_from_key = None
        if isinstance(key, (tuple, list)):
            for part in key:
                if isinstance(part, int):
                    size_from_key = part
                    break

        sizes = []
        if size_from_key is not None and not is_name_only and not is_similar:
            sizes = [size_from_key] * len(paths)
            size_str = self._format_size(size_from_key)
        else:
            for p in paths:
                meta = self._file_meta_map.get(p)
                if meta and len(meta) >= 1:
                    try:
                        sizes.append(int(meta[0]))
                    except Exception:
                        sizes.append(None)
                else:
                    sizes.append(None)

            valid_sizes = [s for s in sizes if s is not None]
            size_str = "—"
            if valid_sizes:
                first_size = valid_sizes[0]
                if all(s == first_size for s in valid_sizes):
                    size_str = self._format_size(first_size)
                else:
                    size_str = strings.tr("term_size_varies")
        
        # Create group item
        group_item = QTreeWidgetItem(self)
        # Store group key for group-level actions (separate from file item path stored in Qt.UserRole).
        try:
            group_item.setData(0, _ROLE_GROUP_KEY, key)
        except Exception:
            pass
        
        # Localized labels
        label_group = strings.tr("term_name_group") if is_name_only else strings.tr("term_duplicate_group") 
        label_files = strings.tr("term_files")
        
        # Truncated hash for display
        if is_name_only or is_similar:
            hash_disp = hash_str
        else:
            hash_disp = hash_str[:8] if len(hash_str) >= 8 else hash_str
        
        suffix = "" if (is_name_only or is_similar) else "..."
        badges = []
        if is_name_only:
            badges.append(strings.tr("badge_name_only"))
        if is_similar:
            badges.append(strings.tr("badge_similar"))
        if is_byte_compare:
            badges.append(strings.tr("badge_byte_compare"))
        badge_text = f" [{', '.join(badges)}]" if badges else ""

        group_item.setText(
            0,
            f"📁 {label_group} ({len(paths)} {label_files}) • {hash_disp}{suffix}{badge_text}"
        )
        group_item.setText(1, size_str)

        # Store base group label for later suffix updates (keep/reclaim/missing).
        try:
            group_item.setData(0, _ROLE_GROUP_BASE_LABEL, group_item.text(0))
        except Exception:
            pass
        
        # Apply theme styling to group
        colors = ModernTheme.get_palette(self.current_theme_mode)
        bg_brush = QBrush(QColor(colors['group_bg']))
        fg_brush = QBrush(QColor(colors['group_fg']))
        
        # Bold font for group headers
        font = group_item.font(0)
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        
        for i in range(4):
            group_item.setBackground(i, bg_brush)
            group_item.setForeground(i, fg_brush)
            group_item.setFont(i, font)
            
        group_item.setExpanded(True)

        # Add file items
        for idx, p in enumerate(paths):
            child = QTreeWidgetItem(group_item)
            
            # Display full path with type-specific icon
            icon = self._get_file_icon(p)
            if p in self._existence_map:
                exists = bool(self._existence_map.get(p))
            elif p in self._file_meta_map:
                exists = True
            else:
                exists = True
            missing_badge = f" [{strings.tr('badge_missing')}]" if not exists else ""
            # User requested full path display
            child.setText(0, f"  {icon} {p}{missing_badge}")
            child.setToolTip(0, p)  # Full path in tooltip
            
            file_size = sizes[idx] if idx < len(sizes) else None
            child.setText(1, self._format_size(file_size) if file_size is not None else "—")
            # Cache raw size for reclaim calculations.
            try:
                child.setData(1, _ROLE_SIZE_BYTES, int(file_size or 0))
            except Exception:
                pass
            child.setText(3, os.path.splitext(p)[1].upper())
            
            mtime = None
            meta = self._file_meta_map.get(p)
            if meta and len(meta) >= 2:
                mtime = meta[1]
            if mtime is not None:
                try:
                    dt = datetime.fromtimestamp(float(mtime)).strftime('%Y-%m-%d %H:%M')
                    child.setText(2, dt)
                except Exception:
                    child.setText(2, "—")
            else:
                child.setText(2, "—")

            # Mark missing files with a muted color.
            if not exists:
                try:
                    for col in range(4):
                        child.setForeground(col, QBrush(QColor("#999999")))
                except Exception:
                    pass

            child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if p in self._selected_paths:
                child.setCheckState(0, Qt.CheckState.Checked)
            else:
                child.setCheckState(0, Qt.CheckState.Unchecked)
            child.setData(0, _ROLE_PATH, p)
            child.setData(0, _ROLE_LOWER_PATH, str(p or "").lower())
            try:
                child.setData(0, _ROLE_EXISTS, 1 if exists else 0)
            except Exception:
                pass
            if p in self._selected_paths:
                self._checked_paths.add(str(p))
            else:
                self._checked_paths.discard(str(p))

        # Initial group summary (keep/reclaim/missing).
        self._update_group_summary(group_item)

    def begin_bulk_check_update(self):
        self._suppress_item_changed = True

    def end_bulk_check_update(self):
        self._suppress_item_changed = False
        checked = set()
        iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value()
            path = item.data(0, _ROLE_PATH)
            if path:
                checked.add(str(path))
            iterator += 1
        self._checked_paths = checked
        # Emit a single update for the UI to refresh counts.
        try:
            self.files_checked.emit(list(self._checked_paths))
        except Exception:
            pass

    def get_group_paths(self, group_item) -> list[str]:
        """Return file paths for a group (top-level) item."""
        paths: list[str] = []
        try:
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                p = child.data(0, _ROLE_PATH)
                if p:
                    paths.append(str(p))
        except Exception:
            pass
        return paths

    def set_group_checked(self, group_item, checked: bool):
        """Check/uncheck all children in a group efficiently."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.begin_bulk_check_update()
        try:
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                child.setCheckState(0, state)
        finally:
            self.end_bulk_check_update()
        try:
            self._update_group_summary(group_item)
        except Exception:
            pass

    def _format_size(self, size):
        """Format file size with appropriate units."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _on_item_changed(self, item, column):
        """Handle checkbox state changes."""
        if self._suppress_item_changed:
            return
        if column != 0:
            return
        try:
            path = item.data(0, _ROLE_PATH)
            if path:
                path = str(path)
                if item.checkState(0) == Qt.CheckState.Checked:
                    self._checked_paths.add(path)
                else:
                    self._checked_paths.discard(path)
        except Exception:
            pass
        try:
            parent = item.parent()
            if parent is not None:
                self._update_group_summary(parent)
        except Exception:
            pass
        self.files_checked.emit(list(self._checked_paths))

    def get_checked_files(self):
        """Returns list of paths checked by user."""
        return list(self._checked_paths)

    def apply_filter(self, text: str) -> tuple[int, int]:
        query = str(text or "").strip().lower()
        root = self.invisibleRootItem()
        total_files = 0
        visible_files = 0
        for i in range(root.childCount()):
            group = root.child(i)
            group_visible = False
            for j in range(group.childCount()):
                item = group.child(j)
                total_files += 1
                lower_path = item.data(0, _ROLE_LOWER_PATH) or ""
                matched = (not query) or (query in str(lower_path))
                item.setHidden(not matched)
                if matched:
                    group_visible = True
                    visible_files += 1
            group.setHidden(not group_visible)
        return visible_files, total_files
