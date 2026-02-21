from __future__ import annotations

from datetime import datetime
import os
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
)

from src.ui.theme import ModernTheme
from src.utils.i18n import strings


_ROLE_BASE = int(Qt.ItemDataRole.UserRole)
_ROLE_PATH = _ROLE_BASE
_ROLE_GROUP_KEY = _ROLE_BASE + 1
_ROLE_EXISTS = _ROLE_BASE + 2
_ROLE_GROUP_BASE_LABEL = _ROLE_BASE + 3
_ROLE_LOWER_PATH = _ROLE_BASE + 4
_ROLE_MTIME = _ROLE_BASE + 5
_ROLE_GROUP_ID = _ROLE_BASE + 6

# Kept on column=1 with Qt.UserRole for backward compatibility with main_window.
_ROLE_SIZE_BYTES = _ROLE_BASE


class ResultsTreeWidget(QTreeWidget):
    files_checked = Signal(list)  # backward-compatible full list
    files_checked_delta = Signal(list, list, int)  # added, removed, selected_count

    EXTENSION_ICONS = {
        # Images
        "jpg": "[IMG]",
        "jpeg": "[IMG]",
        "png": "[IMG]",
        "gif": "[IMG]",
        "bmp": "[IMG]",
        "webp": "[IMG]",
        "svg": "[IMG]",
        "ico": "[IMG]",
        # Videos
        "mp4": "[VID]",
        "mkv": "[VID]",
        "avi": "[VID]",
        "mov": "[VID]",
        "wmv": "[VID]",
        "flv": "[VID]",
        "webm": "[VID]",
        # Audio
        "mp3": "[AUD]",
        "wav": "[AUD]",
        "flac": "[AUD]",
        "aac": "[AUD]",
        "ogg": "[AUD]",
        "wma": "[AUD]",
        "m4a": "[AUD]",
        # Documents
        "pdf": "[DOC]",
        "doc": "[DOC]",
        "docx": "[DOC]",
        "xls": "[DOC]",
        "xlsx": "[DOC]",
        "ppt": "[DOC]",
        "pptx": "[DOC]",
        "txt": "[TXT]",
        # Archives
        "zip": "[ARC]",
        "rar": "[ARC]",
        "7z": "[ARC]",
        "tar": "[ARC]",
        "gz": "[ARC]",
        # Code
        "py": "[PY]",
        "js": "[JS]",
        "html": "[HTML]",
        "css": "[CSS]",
        "json": "[JSON]",
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setHeaderLabels(
            [
                strings.tr("col_path"),
                strings.tr("col_size"),
                strings.tr("col_mtime"),
                strings.tr("col_ext"),
            ]
        )

        self.setColumnWidth(0, 500)
        self.setColumnWidth(1, 100)
        self.setColumnWidth(2, 140)
        self.setColumnWidth(3, 80)

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

        self._populate_timer = QTimer(self)
        self._populate_timer.timeout.connect(self._process_batch)

        self._result_iterator = None
        self._rendered_count = 0
        self._total_results = 0
        self._selected_paths: set[str] = set()
        self._checked_paths: set[str] = set()
        self._suppress_item_changed = False
        self._file_meta_map: dict[str, tuple[int, float]] = {}
        self._existence_map: dict[str, bool] = {}
        self._group_states: dict[int, dict] = {}
        self._next_group_id = 1

        self._populate_target_ms = 8.0
        self._last_filter_query: str | None = None
        self._last_filter_counts = (0, 0)

        self.current_theme_mode = "light"

        self.itemChanged.connect(self._on_item_changed)

    def _get_file_icon(self, filepath: str) -> str:
        ext = os.path.splitext(filepath)[1].lower().lstrip(".")
        return self.EXTENSION_ICONS.get(ext, "[FILE]")

    def set_theme_mode(self, mode: str) -> None:
        self.current_theme_mode = mode
        colors = ModernTheme.get_palette(mode)
        bg_color = QColor(colors["group_bg"])
        fg_color = QColor(colors["group_fg"])
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            for col in range(4):
                item.setBackground(col, QBrush(bg_color))
                item.setForeground(col, QBrush(fg_color))

    def populate(self, results, selected_paths=None, file_meta=None, existence_map=None):
        self._populate_timer.stop()
        self.clear()
        if not results:
            self._checked_paths = set()
            self._selected_paths = set()
            self._group_states = {}
            self._last_filter_query = None
            self._last_filter_counts = (0, 0)
            return

        self._selected_paths = set(selected_paths or [])
        self._checked_paths = set(self._selected_paths)
        self._file_meta_map = dict(file_meta or {})
        self._existence_map = dict(existence_map or {})
        self._group_states = {}
        self._next_group_id = 1
        self._last_filter_query = None
        self._last_filter_counts = (0, 0)

        self._suppress_item_changed = True
        self._result_iterator = iter(results.items())
        self._rendered_count = 0
        self._total_results = len(results)

        self._populate_timer.start(0)

    def _format_reclaim(self, bytes_total: int) -> str:
        return self._format_size(int(bytes_total or 0))

    def _update_group_summary(self, group_item: QTreeWidgetItem) -> None:
        if not group_item:
            return

        gid = int(group_item.data(0, _ROLE_GROUP_ID) or 0)
        state = self._group_states.get(gid)
        if not state:
            return

        total = int(state.get("total") or 0)
        if total <= 0:
            return

        checked = int(state.get("checked") or 0)
        reclaim = int(state.get("reclaim") or 0)
        missing = int(state.get("missing") or 0)
        unchecked_paths = set(state.get("unchecked_paths") or set())
        unchecked = max(0, total - checked)

        keep_name = ""
        if unchecked == 1 and checked > 0 and unchecked_paths:
            try:
                keep_name = os.path.basename(next(iter(unchecked_paths)))
            except Exception:
                keep_name = ""

        base = group_item.data(0, _ROLE_GROUP_BASE_LABEL) or group_item.text(0)
        base = str(base)

        suffix_parts = []
        if keep_name:
            suffix_parts.append(strings.tr("label_keep").format(name=keep_name))
        if checked > 0 and reclaim > 0:
            suffix_parts.append(strings.tr("label_reclaim").format(size=self._format_reclaim(reclaim)))
        if missing > 0:
            suffix_parts.append(strings.tr("badge_missing_count").format(count=missing))

        suffix = "" if not suffix_parts else "  ?? " + "  |  ".join(suffix_parts)
        group_item.setText(0, base + suffix)

    def _process_batch(self):
        if self._result_iterator is None:
            self._populate_timer.stop()
            self._suppress_item_changed = False
            return

        count = 0
        start = time.perf_counter()
        budget = max(1.0, float(self._populate_target_ms)) / 1000.0
        max_batch = 300

        try:
            while count < max_batch:
                key, paths = next(self._result_iterator)
                self._add_group_item(key, list(paths or []))
                count += 1
                self._rendered_count += 1
                if count >= 16 and (time.perf_counter() - start) >= budget:
                    break
        except StopIteration:
            self._populate_timer.stop()
            self._suppress_item_changed = False
            root = self.invisibleRootItem()
            for i in range(root.childCount()):
                self._update_group_summary(root.child(i))

    def _add_group_item(self, key, paths):
        hash_str = "???"
        is_name_only = False
        is_similar = False
        is_folder_dup = False
        is_byte_compare = False

        if isinstance(key, (tuple, list)) and key:
            if key[0] == "NAME_ONLY":
                is_name_only = True
                if len(key) > 1:
                    hash_str = str(key[1])
            elif key[0] == "FOLDER_DUP":
                is_folder_dup = True
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
            is_byte_compare = any(isinstance(part, str) and part.startswith("byte_") for part in key)

        size_from_key = None
        if isinstance(key, (tuple, list)):
            for part in key:
                if isinstance(part, int):
                    size_from_key = part
                    break

        sizes = []
        if size_from_key is not None and not is_name_only and not is_similar and not is_folder_dup:
            sizes = [int(size_from_key)] * len(paths)
            size_str = self._format_size(int(size_from_key))
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
            size_str = "??"
            if valid_sizes:
                first_size = valid_sizes[0]
                if all(s == first_size for s in valid_sizes):
                    size_str = self._format_size(first_size)
                else:
                    size_str = strings.tr("term_size_varies")

        group_item = QTreeWidgetItem(self)
        gid = int(self._next_group_id)
        self._next_group_id += 1
        group_item.setData(0, _ROLE_GROUP_ID, gid)
        group_item.setData(0, _ROLE_GROUP_KEY, key)

        if is_folder_dup:
            label_group = strings.tr("term_folder_group")
        else:
            label_group = strings.tr("term_name_group") if is_name_only else strings.tr("term_duplicate_group")
        label_files = strings.tr("term_files")

        if is_name_only or is_similar:
            hash_disp = hash_str
            suffix = ""
        else:
            hash_disp = hash_str[:8] if len(hash_str) >= 8 else hash_str
            suffix = "..."

        badges = []
        if is_name_only:
            badges.append(strings.tr("badge_name_only"))
        if is_similar:
            badges.append(strings.tr("badge_similar"))
        if is_folder_dup:
            badges.append(strings.tr("badge_folder_dup"))
        if is_byte_compare:
            badges.append(strings.tr("badge_byte_compare"))
        badge_text = f" [{', '.join(badges)}]" if badges else ""

        if is_folder_dup:
            bytes_total = 0
            folder_file_count = 0
            if isinstance(key, (tuple, list)):
                if len(key) > 2 and isinstance(key[2], int):
                    bytes_total = int(key[2] or 0)
                if len(key) > 3 and isinstance(key[3], int):
                    folder_file_count = int(key[3] or 0)
            size_tag = self._format_size(bytes_total) if bytes_total > 0 else "??"
            count_tag = f"{folder_file_count} {label_files}" if folder_file_count > 0 else f"{len(paths)} {label_files}"
            group_item.setText(0, f"[GROUP] {label_group} ({len(paths)} dirs / {count_tag} / {size_tag}){badge_text}")
        else:
            group_item.setText(0, f"[GROUP] {label_group} ({len(paths)} {label_files}) / {hash_disp}{suffix}{badge_text}")
        group_item.setText(1, size_str)
        group_item.setData(0, _ROLE_GROUP_BASE_LABEL, group_item.text(0))

        colors = ModernTheme.get_palette(self.current_theme_mode)
        bg_brush = QBrush(QColor(colors["group_bg"]))
        fg_brush = QBrush(QColor(colors["group_fg"]))

        font = group_item.font(0)
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)

        for i in range(4):
            group_item.setBackground(i, bg_brush)
            group_item.setForeground(i, fg_brush)
            group_item.setFont(i, font)
        group_item.setExpanded(True)

        state = {
            "total": len(paths),
            "checked": 0,
            "reclaim": 0,
            "missing": 0,
            "unchecked_paths": set(),
        }

        for idx, p in enumerate(paths):
            child = QTreeWidgetItem(group_item)
            icon = self._get_file_icon(p)

            if p in self._existence_map:
                exists = bool(self._existence_map.get(p))
            elif p in self._file_meta_map:
                exists = True
            else:
                exists = True

            missing_badge = f" [{strings.tr('badge_missing')}]" if not exists else ""
            child.setText(0, f"  {icon} {p}{missing_badge}")
            child.setToolTip(0, p)

            file_size = sizes[idx] if idx < len(sizes) else None
            child.setText(1, self._format_size(file_size) if file_size is not None else "??")
            child.setData(1, _ROLE_SIZE_BYTES, int(file_size or 0))
            child.setText(3, os.path.splitext(p)[1].upper())

            mtime = None
            meta = self._file_meta_map.get(p)
            if meta and len(meta) >= 2:
                mtime = meta[1]
            if mtime is not None:
                try:
                    dt = datetime.fromtimestamp(float(mtime)).strftime("%Y-%m-%d %H:%M")
                    child.setText(2, dt)
                except Exception:
                    child.setText(2, "??")
            else:
                child.setText(2, "??")
            mtime_value = float(mtime or 0.0) if mtime is not None else 0.0
            child.setData(2, _ROLE_MTIME, mtime_value)
            child.setData(2, Qt.UserRole, mtime_value)

            if not exists:
                state["missing"] += 1
                for col in range(4):
                    child.setForeground(col, QBrush(QColor("#999999")))

            child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            child.setData(0, _ROLE_PATH, p)
            child.setData(0, _ROLE_LOWER_PATH, str(p or "").lower())
            child.setData(0, _ROLE_EXISTS, 1 if exists else 0)

            if p in self._selected_paths:
                child.setCheckState(0, Qt.CheckState.Checked)
                self._checked_paths.add(str(p))
                state["checked"] += 1
                state["reclaim"] += int(file_size or 0)
            else:
                child.setCheckState(0, Qt.CheckState.Unchecked)
                self._checked_paths.discard(str(p))
                state["unchecked_paths"].add(str(p))

        self._group_states[gid] = state
        self._update_group_summary(group_item)

    def begin_bulk_check_update(self):
        self._suppress_item_changed = True

    def end_bulk_check_update(self):
        self._suppress_item_changed = False
        old_checked = set(self._checked_paths)

        checked = set()
        iterator = QTreeWidgetItemIterator(self, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value()
            path = item.data(0, _ROLE_PATH)
            if path:
                checked.add(str(path))
            iterator += 1
        self._checked_paths = checked

        self._rebuild_group_states()

        added = sorted(checked - old_checked)
        removed = sorted(old_checked - checked)
        if added or removed:
            self.files_checked_delta.emit(added, removed, len(self._checked_paths))

        self.files_checked.emit(list(self._checked_paths))

    def get_group_paths(self, group_item) -> list[str]:
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
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.begin_bulk_check_update()
        try:
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                child.setCheckState(0, state)
        finally:
            self.end_bulk_check_update()
        self._update_group_summary(group_item)

    def _format_size(self, size):
        if size is None:
            return "??"
        size = float(size)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _on_item_changed(self, item, column):
        if self._suppress_item_changed:
            return
        if column != 0:
            return

        added: list[str] = []
        removed: list[str] = []

        path = item.data(0, _ROLE_PATH)
        if path:
            path = str(path)
            now_checked = item.checkState(0) == Qt.CheckState.Checked
            was_checked = path in self._checked_paths
            if now_checked:
                self._checked_paths.add(path)
                if not was_checked:
                    added.append(path)
            else:
                self._checked_paths.discard(path)
                if was_checked:
                    removed.append(path)

        parent = item.parent()
        if parent is not None and (added or removed):
            self._update_group_state_on_item_toggle(parent, item)
            self._update_group_summary(parent)

        if added or removed:
            self.files_checked_delta.emit(added, removed, len(self._checked_paths))
        self.files_checked.emit(list(self._checked_paths))

    def get_checked_files(self):
        return list(self._checked_paths)

    def apply_filter(self, text: str) -> tuple[int, int]:
        query = str(text or "").strip().lower()
        if query == self._last_filter_query:
            return self._last_filter_counts

        root = self.invisibleRootItem()
        total_files = 0
        visible_files = 0
        for i in range(root.childCount()):
            group = root.child(i)
            group_visible = False
            for j in range(group.childCount()):
                item = group.child(j)
                total_files += 1
                lower_path = str(item.data(0, _ROLE_LOWER_PATH) or "")
                matched = (not query) or (query in lower_path)
                item.setHidden(not matched)
                if matched:
                    group_visible = True
                    visible_files += 1
            group.setHidden(not group_visible)

        self._last_filter_query = query
        self._last_filter_counts = (visible_files, total_files)
        return visible_files, total_files

    def _rebuild_group_states(self) -> None:
        states = {}
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            gid = int(group.data(0, _ROLE_GROUP_ID) or 0)
            if gid <= 0:
                continue

            total = int(group.childCount() or 0)
            st = {
                "total": total,
                "checked": 0,
                "reclaim": 0,
                "missing": 0,
                "unchecked_paths": set(),
            }

            for j in range(total):
                child = group.child(j)
                path = str(child.data(0, _ROLE_PATH) or "")
                exists = bool(child.data(0, _ROLE_EXISTS))
                if not exists:
                    st["missing"] += 1
                if child.checkState(0) == Qt.CheckState.Checked:
                    st["checked"] += 1
                    st["reclaim"] += int(child.data(1, _ROLE_SIZE_BYTES) or 0)
                elif path:
                    st["unchecked_paths"].add(path)

            states[gid] = st
            self._update_group_summary(group)

        self._group_states = states

    def _update_group_state_on_item_toggle(self, group_item: QTreeWidgetItem, item: QTreeWidgetItem) -> None:
        gid = int(group_item.data(0, _ROLE_GROUP_ID) or 0)
        if gid <= 0:
            return
        state = self._group_states.get(gid)
        if not state:
            return

        path = str(item.data(0, _ROLE_PATH) or "")
        if not path:
            return

        size = int(item.data(1, _ROLE_SIZE_BYTES) or 0)
        if item.checkState(0) == Qt.CheckState.Checked:
            state["unchecked_paths"].discard(path)
            state["checked"] = min(int(state.get("total") or 0), int(state.get("checked") or 0) + 1)
            state["reclaim"] = int(state.get("reclaim") or 0) + size
        else:
            state["unchecked_paths"].add(path)
            state["checked"] = max(0, int(state.get("checked") or 0) - 1)
            state["reclaim"] = max(0, int(state.get("reclaim") or 0) - size)
