from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt, Signal, QTimer, Slot
from PySide6.QtGui import QAction, QCursor
from src.utils.i18n import strings
from datetime import datetime
import os

class ResultsTreeWidget(QTreeWidget):
    """
    Custom TreeWidget for displaying duplicate scan results.
    Handles batch population, formatting, and context menus.
    """
    files_checked = Signal(list) # Emits list of checked file paths
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels([
            strings.tr("col_path"),
            strings.tr("col_size"),
            strings.tr("col_mtime"),
            strings.tr("col_ext")
        ])
        self.setColumnWidth(0, 500)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        
        # Batch processing state
        self._populate_timer = QTimer(self)
        self._populate_timer.timeout.connect(self._process_batch)
        self._result_iterator = None
        self._rendered_count = 0
        self._total_results = 0
        
        # Connect internal signals
        self.itemChanged.connect(self._on_item_changed)
    
    def populate(self, results):
        """
        Populate the tree with scan results (batched).
        results: dict { (hash, size, type): [paths] }
        """
        self.clear()
        if not results:
            return

        self._result_iterator = iter(results.items())
        self._rendered_count = 0
        self._total_results = len(results)
        
        # Reset timer
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
            # Optional: Emit a signal that population is done if needed
            
    def _add_group_item(self, key, paths):
        # key: (hash_str, size, type/extra...)
        # Note: key structure from scanner.py might vary (size, hash, type) or just (hash, size)
        # We need to be robust.
        
        # Heuristic to find size/hash
        size = 0
        hash_str = "???"
        
        if len(key) >= 2:
            # Assuming size is int, hash is str
            if isinstance(key[0], int):
                size = key[0]
                hash_str = str(key[1])
            elif isinstance(key[1], int):
                size = key[1]
                hash_str = str(key[0])

        size_str = self._format_size(size)
        
        group_item = QTreeWidgetItem(self)
        
        # New I18n Keys usage
        label_group = strings.tr("term_duplicate_group") 
        label_files = strings.tr("term_files")
        
        # Safe slicing
        hash_disp = hash_str[:8]
        
        group_item.setText(0, f"📂 {label_group} ({len(paths)} {label_files}) - {hash_disp}...")
        group_item.setText(1, size_str)
        group_item.setBackground(0, Qt.darkGray)
        group_item.setForeground(0, Qt.white)
        group_item.setExpanded(True)

        for p in paths:
            child = QTreeWidgetItem(group_item)
            child.setText(0, p)
            child.setText(1, size_str)
            child.setText(3, os.path.splitext(p)[1])
            
            try:
                mtime = os.path.getmtime(p)
                dt = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                child.setText(2, dt)
            except:
                child.setText(2, "-")

            child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
            child.setCheckState(0, Qt.Unchecked)
            child.setData(0, Qt.UserRole, p)

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024: return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def _on_item_changed(self, item, column):
        # Handle checkbox logic if needed (e.g. emit selection change)
        pass

    def get_checked_files(self):
        """Returns list of paths checked by user."""
        checked = []
        iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.Checked)
        while iterator.value():
            item = iterator.value()
            path = item.data(0, Qt.UserRole)
            if path: # It's a file item
                checked.append(path)
            iterator += 1
        return checked
