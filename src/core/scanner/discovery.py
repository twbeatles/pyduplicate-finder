from __future__ import annotations

from .common import DEBUG_SCAN, defaultdict, logger, os, strings
from .contracts import ScanWorkerHost


class ScanDiscoveryMixin(ScanWorkerHost):
    def _scandir_recursive(self, path, base_dir_mtimes=None):
        self._record_scan_dir(path)
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if self._stop_event.is_set():
                        break

                    if self.skip_hidden and self._is_hidden_or_system_name(getattr(entry, "name", "") or ""):
                        continue
                    if self._should_exclude(entry.path):
                        continue
                    if self._should_ignore_path(entry.path):
                        continue

                    if entry.is_dir(follow_symlinks=self.follow_symlinks):
                        if self.protect_system and self.is_protected(entry.path):
                            continue

                        try:
                            dir_stat = entry.stat(follow_symlinks=self.follow_symlinks)
                            dir_mtime = float(dir_stat.st_mtime)
                        except Exception:
                            dir_mtime = None

                        self._record_scan_dir(entry.path, dir_mtime)
                        if base_dir_mtimes is not None:
                            pass

                        if self.follow_symlinks:
                            k = self._dir_key(entry.path)
                            if k in self._seen_dir_keys:
                                continue
                            self._seen_dir_keys.add(k)

                        yield from self._scandir_recursive(entry.path, base_dir_mtimes=base_dir_mtimes)
                    elif entry.is_file(follow_symlinks=self.follow_symlinks):
                        if self.extensions:
                            _, ext = os.path.splitext(entry.name)
                            if ext.lower().replace(".", "") not in self.extensions:
                                continue
                        if not self._should_include(entry.path):
                            continue
                        yield entry
        except OSError as e:
            self._record_scan_error(path, e, stage="collecting", operation="scandir")
            if DEBUG_SCAN:
                logger.warning("[scan] Scandir error: %s", e)
            return

    def _collect_image_candidate(self, path: str) -> None:
        if not (self.use_similar_image and hasattr(self, "image_hasher")):
            return
        try:
            _, ext = os.path.splitext(path)
            if ext.lower() in self.image_hasher.SUPPORTED_EXTENSIONS:
                self._image_files.append(path)
        except Exception:
            pass

    def _collect_document_candidate(self, path: str) -> None:
        if not (self.use_similar_document and hasattr(self, "document_hasher")):
            return
        try:
            if self.document_hasher.is_supported(path):
                self._document_files.append(path)
        except Exception:
            pass

    def _track_file_record(self, path: str, size: int, mtime: float, size_map, db_batch=None) -> None:
        self._file_meta[path] = (size, mtime)
        self._collect_image_candidate(path)
        self._collect_document_candidate(path)
        self._mark_path_exemption_status(path)
        self._path_collection_roles[path] = self._resolve_collection_role(path)
        self._inc_metric("files_scanned", 1)

        if size >= self.min_size and (size > 0 or self.min_size <= 0):
            size_map[size].append(path)

        if self.session_id and db_batch is not None:
            db_batch.append((path, size, mtime))

    def _scan_files(self):
        self._file_meta = {}
        self._image_files = []
        self._document_files = []
        self._current_scan_dirs = {}
        self._base_scan_dirs = {}
        self.latest_baseline_delta_map = {}
        self._path_collection_roles = {}
        self._path_exemption_status = {}

        self._emit_progress(0, strings.tr("status_collecting_files"), force=True)

        if self.session_id and self.use_cached_files:
            if self.cache_manager.has_scan_files(self.session_id):
                self._base_scan_dirs = self.cache_manager.load_scan_dirs(self.session_id)
                size_map = self._scan_files_from_cache(self.cache_manager.iter_scan_files(self.session_id))
                self._save_scan_dirs_snapshot()
                return size_map

        if self.incremental_rescan and self.base_session_id and not self.use_cached_files:
            size_map = self._scan_files_incremental(self.base_session_id)
            self._save_scan_dirs_snapshot()
            return size_map

        size_map = defaultdict(list)
        file_count = 0
        db_batch = []
        db_batch_size = 1000
        for folder in self.folders:
            if self.protect_system and self.is_protected(folder):
                self._emit_progress(0, strings.tr("status_skip_protected_root").format(folder), force=True)
                continue
            if self._should_ignore_path(folder):
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

            for entry in self._scandir_recursive(folder):
                if self._stop_event.is_set():
                    break

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
                    if self.session_id and len(db_batch) >= db_batch_size:
                        self.cache_manager.save_scan_files_batch(self.session_id, db_batch)
                        db_batch.clear()

                    file_count += 1
                    if file_count % 1000 == 0:
                        self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")
                except OSError as e:
                    self._record_scan_error(entry.path, e, stage="collecting", operation="stat")
                    continue

        if self.session_id and db_batch:
            self.cache_manager.save_scan_files_batch(self.session_id, db_batch)

        self._save_scan_dirs_snapshot()
        return size_map

    def _scan_files_from_cache(self, cached_entries):
        size_map = defaultdict(list)
        file_count = 0
        missing_paths = []
        update_entries = []
        for path, cached_size, cached_mtime in cached_entries:
            if self._stop_event.is_set():
                break
            if self.protect_system and self.is_protected(path):
                continue
            if self.skip_hidden and self._is_hidden_or_system_name(os.path.basename(path)):
                continue
            if self._should_exclude(path):
                continue
            if self._should_ignore_path(path):
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
                self._record_scan_error(path, e, stage="collecting", operation="stat_cached")
                missing_paths.append(path)
                continue

            if stat.st_ino:
                inode_key = (stat.st_dev, stat.st_ino)
                if inode_key in self.seen_inodes:
                    continue
                self.seen_inodes.add(inode_key)

            size = stat.st_size
            mtime = stat.st_mtime
            if size != cached_size or mtime != cached_mtime:
                update_entries.append((path, size, mtime))

            self._track_file_record(path, int(size), float(mtime), size_map)
            self._record_scan_dir(os.path.dirname(path))

            file_count += 1
            if file_count % 1000 == 0:
                self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")

        if self.session_id and update_entries:
            self.cache_manager.save_scan_files_batch(self.session_id, update_entries)
        if self.session_id and missing_paths:
            self.cache_manager.remove_scan_files(self.session_id, missing_paths)

        return size_map
