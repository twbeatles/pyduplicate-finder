from __future__ import annotations

from .common import defaultdict, os, strings


class ScanIncrementalMixin:
    def _scan_files_incremental(self, base_session_id: int):
        size_map = defaultdict(list)
        file_count = 0
        revalidated_count = 0
        changed_count = 0
        new_count = 0
        missing_count = 0
        db_batch = []
        db_batch_size = 1000
        delta_map = {}

        base_known_paths = set()
        self._base_scan_dirs = self.cache_manager.load_scan_dirs(base_session_id)

        for path, cached_size, cached_mtime in self.cache_manager.iter_scan_files(base_session_id):
            if self._stop_event.is_set():
                break
            if not path:
                continue
            base_known_paths.add(path)

            if self.protect_system and self.is_protected(path):
                continue
            if self.skip_hidden and self._is_hidden_or_system_name(os.path.basename(path)):
                continue
            if self._should_exclude(path):
                continue
            if self.extensions:
                _, ext = os.path.splitext(path)
                if ext.lower().replace(".", "") not in self.extensions:
                    continue
            if not self._should_include(path):
                continue

            try:
                stat = os.stat(path, follow_symlinks=self.follow_symlinks)
            except OSError as e:
                missing_count += 1
                self._record_scan_error(path, e, stage="incremental_index", operation="stat_known")
                continue

            if stat.st_ino:
                inode_key = (stat.st_dev, stat.st_ino)
                if inode_key in self.seen_inodes:
                    continue
                self.seen_inodes.add(inode_key)

            size = int(stat.st_size)
            mtime = float(stat.st_mtime)
            if int(cached_size or -1) != size or float(cached_mtime or -1.0) != mtime:
                changed_count += 1
                delta_map[path] = "changed"
            else:
                revalidated_count += 1
                delta_map[path] = "revalidated"
            self._track_file_record(path, size, mtime, size_map, db_batch)
            self._record_scan_dir(os.path.dirname(path))

            if self.session_id and len(db_batch) >= db_batch_size:
                self.cache_manager.save_scan_files_batch(self.session_id, db_batch)
                db_batch.clear()

            file_count += 1
            if file_count % 1000 == 0:
                self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")

        for folder in self.folders:
            if self.protect_system and self.is_protected(folder):
                self._emit_progress(0, strings.tr("status_skip_protected_root").format(folder), force=True)
                continue
            self._record_scan_dir(folder)
            if self.follow_symlinks:
                try:
                    k = self._dir_key(folder)
                    if k in self._seen_dir_keys:
                        continue
                    self._seen_dir_keys.add(k)
                except Exception:
                    pass

            for entry in self._scandir_recursive(folder, base_dir_mtimes=self._base_scan_dirs):
                if self._stop_event.is_set():
                    break
                if entry.path in base_known_paths:
                    continue

                try:
                    stat = entry.stat(follow_symlinks=self.follow_symlinks)
                    if stat.st_ino == 0:
                        stat = os.stat(entry.path, follow_symlinks=self.follow_symlinks)

                    if stat.st_ino:
                        inode_key = (stat.st_dev, stat.st_ino)
                        if inode_key in self.seen_inodes:
                            continue
                        self.seen_inodes.add(inode_key)

                    size = int(stat.st_size)
                    mtime = float(stat.st_mtime)
                    self._track_file_record(entry.path, size, mtime, size_map, db_batch)
                    new_count += 1
                    delta_map[entry.path] = "new"

                    if self.session_id and len(db_batch) >= db_batch_size:
                        self.cache_manager.save_scan_files_batch(self.session_id, db_batch)
                        db_batch.clear()

                    file_count += 1
                    if file_count % 1000 == 0:
                        self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")
                except OSError as e:
                    self._record_scan_error(entry.path, e, stage="incremental_index", operation="stat_new")
                    continue

        if self.session_id and db_batch:
            self.cache_manager.save_scan_files_batch(self.session_id, db_batch)

        self.latest_baseline_delta_map = dict(delta_map)
        self.incremental_stats = {
            "revalidated": int(revalidated_count),
            "changed": int(changed_count),
            "new": int(new_count),
            "missing": int(missing_count),
            "total": int(file_count),
            "base_session_id": int(base_session_id or 0),
        }
        return size_map
