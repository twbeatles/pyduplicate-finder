from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QHeaderView
from PySide6.QtCore import Qt, Signal, QTimer, Slot
from PySide6.QtGui import QAction, QCursor, QBrush, QColor, QFont
from src.utils.i18n import strings
from src.ui.theme import ModernTheme
from datetime import datetime
import os

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
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setAlternatingRowColors(True)
        self.setIndentation(24)
        self.setAnimated(True)
        self.setUniformRowHeights(True)
        self.setTextElideMode(Qt.ElideMiddle)
        
        # Batch processing state
        self._populate_timer = QTimer(self)
        self._populate_timer.timeout.connect(self._process_batch)
        self._result_iterator = None
        self._rendered_count = 0
        self._total_results = 0
        self._selected_paths = set()
        self._suppress_item_changed = False
        
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

    def populate(self, results, selected_paths=None):
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
        self._suppress_item_changed = True
        self._result_iterator = iter(results.items())
        self._rendered_count = 0
        self._total_results = len(results)
        
        # Start batch processing
        self._populate_timer.start(0)

    def _process_batch(self):
        BATCH_SIZE = 50
        count = 0
        
        try:
            while count < BATCH_SIZE:
                key, paths = next(self._result_iterator)
                self._add_group_item(key, paths)
                count += 1
                self._rendered_count += 1
            
        except StopIteration:
            self._populate_timer.stop()
            self._suppress_item_changed = False
            
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
                try:
                    sizes.append(os.path.getsize(p))
                except Exception:
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
            group_item.setData(0, Qt.UserRole + 1, key)
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
            filename = os.path.basename(p)
            icon = self._get_file_icon(p)
            # User requested full path display
            child.setText(0, f"  {icon} {p}")
            child.setToolTip(0, p)  # Full path in tooltip
            
            file_size = sizes[idx] if idx < len(sizes) else None
            child.setText(1, self._format_size(file_size) if file_size is not None else "—")
            child.setText(3, os.path.splitext(p)[1].upper())
            
            try:
                mtime = os.path.getmtime(p)
                dt = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                child.setText(2, dt)
            except:
                child.setText(2, "—")

            child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
            if p in self._selected_paths:
                child.setCheckState(0, Qt.Checked)
            else:
                child.setCheckState(0, Qt.Unchecked)
            child.setData(0, Qt.UserRole, p)

    def begin_bulk_check_update(self):
        self._suppress_item_changed = True

    def end_bulk_check_update(self):
        self._suppress_item_changed = False
        # Emit a single update for the UI to refresh counts.
        try:
            self.files_checked.emit(self.get_checked_files())
        except Exception:
            pass

    def get_group_paths(self, group_item) -> list:
        """Return file paths for a group (top-level) item."""
        paths = []
        try:
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                p = child.data(0, Qt.UserRole)
                if p:
                    paths.append(p)
        except Exception:
            pass
        return paths

    def set_group_checked(self, group_item, checked: bool):
        """Check/uncheck all children in a group efficiently."""
        state = Qt.Checked if checked else Qt.Unchecked
        self.begin_bulk_check_update()
        try:
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                child.setCheckState(0, state)
        finally:
            self.end_bulk_check_update()

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
        self.files_checked.emit(self.get_checked_files())

    def get_checked_files(self):
        """Returns list of paths checked by user."""
        checked = []
        iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.Checked)
        while iterator.value():
            item = iterator.value()
            path = item.data(0, Qt.UserRole)
            if path:
                checked.append(path)
            iterator += 1
        return checked
