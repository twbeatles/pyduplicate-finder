from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import hashlib
import logging
import os
import platform
import time
import fnmatch
import threading
from collections import defaultdict
import concurrent.futures
from src.core.cache_manager import CacheManager
from src.utils.i18n import strings

# Debug logging flags (disabled by default in packaged apps)
DEBUG_SCAN = os.environ.get("PYDUPLICATEFINDER_DEBUG_SCAN", "").lower() in ("1", "true", "yes")

logger = logging.getLogger(__name__)

# 유사 이미지 탐지 (선택적)
_ImageHasher = None
try:
    from src.core.image_hash import ImageHasher as _ImageHasher, is_available as _image_hash_available
except ImportError:
    _ImageHasher = None

    def _image_hash_available() -> bool:
        return False


IMAGE_HASH_AVAILABLE = bool(_image_hash_available())

BUFFER_SIZE = 1024 * 1024  # 1MB buffer for faster I/O

class ScanWorker(QThread):
    progress_updated = Signal(int, str)
    stage_updated = Signal(str)  # stage code for UI
    scan_finished = Signal(object)  # dict of results, or None if cancelled
    scan_cancelled = Signal()  # Issue #3: Separate signal for cancellation
    scan_failed = Signal(str)  # error message

    def __init__(self, folders, check_name=False, min_size_kb=0, extensions=None,
                 protect_system=True, byte_compare=False, max_workers=None,
                 exclude_patterns=None, include_patterns=None,
                 skip_hidden=False, follow_symlinks=False,
                 name_only=False,
                 detect_duplicate_folders=False,
                 use_similar_image=False, similarity_threshold=0.9,
                 use_mixed_mode=False,
                 incremental_rescan=False, base_session_id=None,
                 session_id=None, use_cached_files=False):
        super().__init__()
        self.folders = folders
        self.check_name = check_name
        self.name_only = name_only  # 파일명만 비교 (내용 무시)
        self.min_size = min_size_kb * 1024  # KB to Bytes
        self.extensions = set(ext.lower().strip() for ext in extensions) if extensions else None
        self.protect_system = protect_system
        self.byte_compare = byte_compare
        self.exclude_patterns = exclude_patterns or []  # 제외 패턴 목록
        self.include_patterns = include_patterns or []  # 포함 패턴 목록 (optional)
        self.skip_hidden = bool(skip_hidden)
        self.follow_symlinks = bool(follow_symlinks)
        self.detect_duplicate_folders = bool(detect_duplicate_folders)
        self.use_similar_image = use_similar_image and IMAGE_HASH_AVAILABLE  # 유사 이미지 탐지
        self.use_mixed_mode = bool(use_mixed_mode)
        self.similarity_threshold = similarity_threshold
        self.incremental_rescan = bool(incremental_rescan)
        self.base_session_id = int(base_session_id) if base_session_id else None
        self._stop_event = threading.Event() # Thread-safe cancellation signal
        self._init_protected_paths()
        self.cache_manager = CacheManager()
        self.max_workers = max_workers or (os.cpu_count() or 4)
        self.session_id = session_id
        self.use_cached_files = use_cached_files
        
        # Physical file tracking (Dev, Inode)
        self.seen_inodes = set()

        # Directory loop detection (for follow_symlinks).
        self._seen_dir_keys = set()

        # Progress throttling
        self._last_progress_update_time = 0
        self._progress_update_interval = 0.1  # 100ms
        self._progress_mutex = QMutex()
        self._stage = None

        # Scan bookkeeping
        self._file_meta = {}  # path -> (size, mtime)
        self._image_files = []
        self._current_scan_dirs = {}  # normalized dir path -> mtime
        self._base_scan_dirs = {}
        self.latest_file_meta = {}
        self.incremental_stats = {}
        
        # 유사 이미지 탐지기
        if self.use_similar_image and _ImageHasher is not None:
            self.image_hasher = _ImageHasher()

    def _init_protected_paths(self):
        self.protected_paths = []
        if self.protect_system:
            if platform.system() == "Windows":
                # Typical Windows system paths (env-driven, avoids broken join like 'C:Windows')
                sys_drive = os.environ.get("SystemDrive", "C:")
                candidates = [
                    os.environ.get("WINDIR") or os.environ.get("SystemRoot"),  # e.g. C:\Windows
                    os.environ.get("ProgramFiles"),                            # e.g. C:\Program Files
                    os.environ.get("ProgramFiles(x86)"),                       # e.g. C:\Program Files (x86)
                    os.environ.get("ProgramData"),                             # e.g. C:\ProgramData
                    # Fallbacks (in case env vars are missing in a packaged/runtime context)
                    os.path.join(sys_drive + os.sep, "Windows"),
                    os.path.join(sys_drive + os.sep, "Program Files"),
                    os.path.join(sys_drive + os.sep, "Program Files (x86)"),
                    os.path.join(sys_drive + os.sep, "ProgramData"),
                ]
                self.protected_paths = [p for p in candidates if p]
            else:
                # Unix-like system paths
                self.protected_paths = [
                    '/bin', '/boot', '/dev', '/etc', '/lib', '/lib64', 
                    '/proc', '/root', '/run', '/sbin', '/sys', '/usr', '/var'
                ]
            # Normalize paths
            self.protected_paths = [self._normalize_path(p) for p in self.protected_paths]

    def _normalize_path(self, path: str) -> str:
        path = os.path.abspath(path)
        path = os.path.normpath(path)
        return os.path.normcase(path) if os.name == "nt" else path

    def is_protected(self, path):
        if not self.protect_system:
            return False
        try:
            norm_path = self._normalize_path(path)
            for p in self.protected_paths:
                # Avoid prefix bugs (e.g. C:\WindowsOld) and drive-mismatch errors.
                try:
                    if os.path.commonpath([norm_path, p]) == p:
                        return True
                except ValueError:
                    continue
        except:
            return False
        return False

    def _normalize_match(self, value: str) -> str:
        normalized = os.path.normpath(value).replace("\\", "/")
        if os.name == "nt":
            return normalized.lower()
        return normalized

    def _matches_any_pattern(self, path: str, patterns) -> bool:
        if not patterns:
            return False
        name = os.path.basename(path)
        name_match = name.lower() if os.name == "nt" else name
        path_match = self._normalize_match(path)

        for pattern in patterns:
            if not pattern:
                continue
            pattern_str = str(pattern)
            pattern_match = pattern_str.lower() if os.name == "nt" else pattern_str
            if fnmatch.fnmatchcase(name_match, pattern_match):
                return True
            if fnmatch.fnmatchcase(path_match, self._normalize_match(pattern_str)):
                return True
        return False

    def _should_exclude(self, path: str) -> bool:
        """제외 패턴과 일치하는지 확인"""
        return self._matches_any_pattern(path, self.exclude_patterns)

    def _should_include(self, path: str) -> bool:
        """포함 패턴이 설정된 경우, 포함 여부 확인 (파일 기준)."""
        if not self.include_patterns:
            return True
        return self._matches_any_pattern(path, self.include_patterns)

    def _is_hidden_or_system_name(self, name: str) -> bool:
        if not name:
            return False
        n = name.lower() if os.name == "nt" else name
        if n.startswith("."):
            return True
        if n in ("thumbs.db", "desktop.ini", ".ds_store"):
            return True
        return False

    def _dir_key(self, path: str):
        try:
            st = os.stat(path, follow_symlinks=True)
            if getattr(st, "st_ino", 0):
                return (st.st_dev, st.st_ino)
        except Exception:
            pass
        try:
            return self._normalize_path(os.path.realpath(path))
        except Exception:
            return self._normalize_path(path)

    def _record_scan_dir(self, dir_path: str, mtime=None) -> None:
        try:
            norm = self._normalize_path(dir_path)
            if mtime is None:
                mtime = os.path.getmtime(dir_path)
            self._current_scan_dirs[norm] = float(mtime)
        except Exception:
            pass

    def _save_scan_dirs_snapshot(self) -> None:
        if not self.session_id:
            return
        try:
            merged = dict(self._base_scan_dirs or {})
            merged.update(self._current_scan_dirs or {})
            entries = [(p, m) for p, m in merged.items() if p]
            self.cache_manager.clear_scan_dirs(self.session_id)
            self.cache_manager.save_scan_dirs_batch(self.session_id, entries)
        except Exception:
            pass

    def stop(self):
        self._stop_event.set()

    def _set_stage(self, stage: str, *, status=None, progress=None, progress_message=None):
        """Update current stage (and persist it if a session is active)."""
        if not stage:
            return

        self._stage = stage

        try:
            self.stage_updated.emit(stage)
        except Exception:
            pass

        if not self.session_id:
            return

        fields = {"stage": stage}
        if status is not None:
            fields["status"] = status
        if progress is not None:
            fields["progress"] = progress
        if progress_message is not None:
            fields["progress_message"] = progress_message

        try:
            self.cache_manager.update_scan_session(self.session_id, **fields)
        except Exception:
            pass

    def _emit_progress(self, value, message, force=False):
        """Thread-safe and throttled progress emission."""
        if self._stop_event.is_set(): return

        current_time = time.time()
        with QMutexLocker(self._progress_mutex):
            if force or (current_time - self._last_progress_update_time >= self._progress_update_interval):
                self.progress_updated.emit(value, message)
                self._last_progress_update_time = current_time
                if self.session_id:
                    self.cache_manager.update_scan_session(
                        self.session_id,
                        progress=value,
                        progress_message=message
                    )

    def get_file_hash(self, filepath, size=None, mtime=None, block_size=BUFFER_SIZE, partial=False):
        """
        Calculates file hash with Caching support.
        Returns: (hash_string, is_calculated_new)
        """
        # If size/mtime not provided, get them (should rarely happen in optimized flow)
        if size is None or mtime is None:
            try:
                stat = os.stat(filepath)
                size = stat.st_size
                mtime = stat.st_mtime
            except OSError:
                return None, False

        # Try Cache first
        cached = self.cache_manager.get_cached_hash(filepath, size, mtime)
        if cached:
            # cached is (partial_hash, full_hash)
            if partial and cached[0]:
                return cached[0], False
            if not partial and cached[1]:
                return cached[1], False

        # Calculate if not in cache (using BLAKE2b)
        hasher = hashlib.blake2b(digest_size=32) # Faster on 64-bit than MD5/SHA256
        try:
            with open(filepath, 'rb') as f:
                if partial:
                    # Partial Hash: First 4KB
                    buf = f.read(4096)
                    hasher.update(buf)
                    # Last 4KB
                    if size > 8192:
                        f.seek(-4096, os.SEEK_END)
                        buf = f.read(4096)
                        hasher.update(buf)
                else:
                    # Full Hash
                    while True:
                        if self._stop_event.is_set(): return None, False
                        buf = f.read(block_size)
                        if not buf: break
                        hasher.update(buf)
            
            digest = hasher.hexdigest()
            # Note: We do NOT update cache here inside the thread anymore.
            # We return it and let the main thread batch update it.
            return digest, True
        except OSError:
            return None, False

    def compare_files_byte_by_byte(self, file1, file2):
        """Returns True if files are identical byte-by-byte."""
        buf_size = BUFFER_SIZE
        try:
            with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
                while True:
                    if self._stop_event.is_set(): return False
                    b1 = f1.read(buf_size)
                    b2 = f2.read(buf_size)
                    if b1 != b2: return False
                    if not b1: return True # End of file
        except OSError:
            return False

    def _scandir_recursive(self, path, base_dir_mtimes=None):
        """Recursive os.scandir generator"""
        # print(f"DEBUG: Entering _scandir_recursive({path})")
        self._record_scan_dir(path)
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if self._stop_event.is_set(): break

                    if self.skip_hidden and self._is_hidden_or_system_name(getattr(entry, "name", "") or ""):
                        continue

                    if self._should_exclude(entry.path):
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
                            norm = self._normalize_path(entry.path)
                            base_mtime = base_dir_mtimes.get(norm)
                            if base_mtime is not None and dir_mtime is not None and float(base_mtime) == float(dir_mtime):
                                # Directory structure unchanged since base session; skip deep walk.
                                continue

                        if self.follow_symlinks:
                            k = self._dir_key(entry.path)
                            if k in self._seen_dir_keys:
                                continue
                            self._seen_dir_keys.add(k)

                        yield from self._scandir_recursive(entry.path, base_dir_mtimes=base_dir_mtimes)
                    elif entry.is_file(follow_symlinks=self.follow_symlinks):
                        # print(f"DEBUG: Yielding file {entry.name}")
                        if self.extensions:
                            # entry.name is filename
                            _, ext = os.path.splitext(entry.name)
                            if ext.lower().replace('.', '') not in self.extensions:
                                continue
                        if not self._should_include(entry.path):
                            continue
                        yield entry
        except OSError as e:
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

    def _track_file_record(self, path: str, size: int, mtime: float, size_map, db_batch) -> None:
        self._file_meta[path] = (size, mtime)
        self._collect_image_candidate(path)

        if size >= self.min_size and size > 0:
            size_map[size].append(path)

        if self.session_id:
            db_batch.append((path, size, mtime))

    def _scan_files(self):
        """Step 1: File collection and size filtering using cached os.scandir entries."""
        self._file_meta = {}
        self._image_files = []
        self._current_scan_dirs = {}
        self._base_scan_dirs = {}

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
        DB_BATCH_SIZE = 1000
        for folder in self.folders:
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
                    if self.session_id and len(db_batch) >= DB_BATCH_SIZE:
                        self.cache_manager.save_scan_files_batch(self.session_id, db_batch)
                        db_batch.clear()

                    file_count += 1
                    if file_count % 1000 == 0:
                        self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")
                except OSError:
                    continue

        if self.session_id and db_batch:
            self.cache_manager.save_scan_files_batch(self.session_id, db_batch)

        self._save_scan_dirs_snapshot()
        return size_map

    def _scan_files_incremental(self, base_session_id: int):
        """Incremental collection: stat known paths + walk changed directories only for new files."""
        size_map = defaultdict(list)
        file_count = 0
        revalidated_count = 0
        changed_count = 0
        new_count = 0
        missing_count = 0
        db_batch = []
        DB_BATCH_SIZE = 1000

        base_known_paths = set()
        self._base_scan_dirs = self.cache_manager.load_scan_dirs(base_session_id)

        # 1) Revalidate known files from base session.
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
                if ext.lower().replace('.', '') not in self.extensions:
                    continue
            if not self._should_include(path):
                continue

            try:
                stat = os.stat(path, follow_symlinks=self.follow_symlinks)
            except OSError:
                missing_count += 1
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
            else:
                revalidated_count += 1
            self._track_file_record(path, size, mtime, size_map, db_batch)
            self._record_scan_dir(os.path.dirname(path))

            if self.session_id and len(db_batch) >= DB_BATCH_SIZE:
                self.cache_manager.save_scan_files_batch(self.session_id, db_batch)
                db_batch.clear()

            file_count += 1
            if file_count % 1000 == 0:
                self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")

        # 2) Walk only changed directories to discover new paths.
        for folder in self.folders:
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

                    if self.session_id and len(db_batch) >= DB_BATCH_SIZE:
                        self.cache_manager.save_scan_files_batch(self.session_id, db_batch)
                        db_batch.clear()

                    file_count += 1
                    if file_count % 1000 == 0:
                        self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")
                except OSError:
                    continue

        if self.session_id and db_batch:
            self.cache_manager.save_scan_files_batch(self.session_id, db_batch)

        self.incremental_stats = {
            "revalidated": int(revalidated_count),
            "changed": int(changed_count),
            "new": int(new_count),
            "missing": int(missing_count),
            "total": int(file_count),
            "base_session_id": int(base_session_id or 0),
        }
        return size_map

    def _scan_files_from_cache(self, cached_entries):
        """Build size map from cached entries."""
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
            if self.extensions:
                _, ext = os.path.splitext(path)
                if ext.lower().replace('.', '') not in self.extensions:
                    continue
            if not self._should_include(path):
                continue
            try:
                stat = os.stat(path, follow_symlinks=self.follow_symlinks)
            except OSError:
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

            if size >= self.min_size and size > 0:
                size_map[size].append(path)

            self._file_meta[path] = (int(size), float(mtime))
            self._collect_image_candidate(path)
            self._record_scan_dir(os.path.dirname(path))

            file_count += 1
            if file_count % 1000 == 0:
                self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")

        if self.session_id and update_entries:
            self.cache_manager.save_scan_files_batch(self.session_id, update_entries)
        if self.session_id and missing_paths:
            self.cache_manager.remove_scan_files(self.session_id, missing_paths)

        return size_map

    def _calculate_hashes_parallel(self, candidates, is_quick_scan=True, seed_session_id=None):
        """Hash candidates using pre-collected (path, size, mtime) tuples."""
        QUICK_SCAN_THRESHOLD = 10 * 1024 * 1024
        HASH_CHUNK_SIZE = 800
        BATCH_SIZE = 100
        SESSION_BATCH_SIZE = 200
        MAX_PENDING_TASKS = self.max_workers * 4

        hash_map = defaultdict(list)
        total = len(candidates or [])
        processed = 0
        if total <= 0:
            return hash_map

        progress_step = max(10, min(500, total // 200 if total >= 200 else 10))
        db_batch = []
        session_hash_batch = []

        def _emit_hash_progress(force=False):
            if force or (processed % progress_step == 0) or processed == total:
                percent = int((processed / total) * 40) + (0 if is_quick_scan else 50)
                self._emit_progress(percent, strings.tr("status_hashing_progress").format(processed, total))

        def task_wrapper(fp, s, m, p):
            return fp, s, m, p, self.get_file_hash(fp, s, m, block_size=BUFFER_SIZE, partial=p)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for chunk_start in range(0, total, HASH_CHUNK_SIZE):
                if self._stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                chunk = candidates[chunk_start:chunk_start + HASH_CHUNK_SIZE]
                chunk_paths = [p for p, _s, _m in chunk]

                session_hashes = {}
                if self.session_id:
                    if is_quick_scan:
                        session_hashes = self.cache_manager.load_scan_hashes_for_paths(self.session_id, chunk_paths)
                    else:
                        session_hashes = self.cache_manager.load_scan_hashes_for_paths(
                            self.session_id,
                            chunk_paths,
                            hash_type="FULL",
                        )

                seed_hashes = {}
                if seed_session_id and int(seed_session_id) != int(self.session_id or 0):
                    try:
                        if is_quick_scan:
                            seed_hashes = self.cache_manager.load_scan_hashes_for_paths(seed_session_id, chunk_paths)
                        else:
                            seed_hashes = self.cache_manager.load_scan_hashes_for_paths(
                                seed_session_id,
                                chunk_paths,
                                hash_type="FULL",
                            )
                    except Exception:
                        seed_hashes = {}

                candidate_iter = iter(chunk)
                active_futures = set()

                def submit_task() -> bool:
                    nonlocal processed
                    if self._stop_event.is_set():
                        return False
                    try:
                        filepath, size, mtime = next(candidate_iter)
                    except StopIteration:
                        return False

                    partial = bool(is_quick_scan and int(size) >= QUICK_SCAN_THRESHOLD)
                    type_str = "PARTIAL" if partial else "FULL"

                    cached = None
                    if self.session_id:
                        cached = session_hashes.get((filepath, type_str))
                    if not cached and seed_hashes:
                        cached = seed_hashes.get((filepath, type_str))

                    if cached and cached[1] == size and cached[2] == mtime:
                        digest = cached[0]
                        if digest:
                            hash_map[(size, digest, type_str)].append(filepath)
                            if self.session_id:
                                session_hash_batch.append((filepath, size, mtime, type_str, digest))
                        processed += 1
                        _emit_hash_progress()
                        return True

                    future = executor.submit(task_wrapper, filepath, size, mtime, partial)
                    active_futures.add(future)
                    return True

                for _ in range(min(MAX_PENDING_TASKS, len(chunk))):
                    if not submit_task():
                        break

                while active_futures:
                    if self._stop_event.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                    done, _ = concurrent.futures.wait(
                        active_futures,
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                    for future in done:
                        active_futures.remove(future)
                        try:
                            filepath, size, mtime, partial, result_tuple = future.result()
                            digest, is_newly_calculated = result_tuple
                            if digest:
                                type_str = "PARTIAL" if partial else "FULL"
                                hash_map[(size, digest, type_str)].append(filepath)
                                if self.session_id:
                                    session_hash_batch.append((filepath, size, mtime, type_str, digest))
                                if is_newly_calculated:
                                    db_batch.append(
                                        (
                                            filepath,
                                            size,
                                            mtime,
                                            digest if partial else None,
                                            digest if not partial else None,
                                        )
                                    )
                        except Exception:
                            pass

                        if len(db_batch) >= BATCH_SIZE:
                            self.cache_manager.update_cache_batch(db_batch)
                            db_batch.clear()
                        if self.session_id and len(session_hash_batch) >= SESSION_BATCH_SIZE:
                            self.cache_manager.save_scan_hashes_batch(self.session_id, session_hash_batch)
                            session_hash_batch.clear()

                        processed += 1
                        _emit_hash_progress()
                        submit_task()

        if db_batch:
            self.cache_manager.update_cache_batch(db_batch)
        if self.session_id and session_hash_batch:
            self.cache_manager.save_scan_hashes_batch(self.session_id, session_hash_batch)
        _emit_hash_progress(force=True)
        return hash_map

    def run(self):
        try:
            start_time = time.time()
            self.seen_inodes.clear()
            self._set_stage(
                "collecting",
                status="running",
                progress=0,
                progress_message=strings.tr("status_collecting_files"),
            )

            # Similar-only legacy mode
            if self.use_similar_image and not self.use_mixed_mode:
                self._run_similar_image_scan()
                return

            if self.incremental_rescan and self.base_session_id:
                self._set_stage("incremental_index")

            # 1. File Collection
            size_map = self._scan_files()
            if self._stop_event.is_set():
                # Issue #3: Emit None to indicate cancellation (preserve previous results)
                if self.session_id:
                    self.cache_manager.update_scan_session(
                        self.session_id,
                        status="paused",
                        stage=self._stage or "collecting",
                    )
                self.scan_cancelled.emit()
                return
            if self.session_id:
                self.cache_manager.update_scan_session(self.session_id, stage="collected")
            self._set_stage("collected")

            final_duplicates = {}

            if self.name_only:
                name_groups = defaultdict(list)
                for paths in size_map.values():
                    if self._stop_event.is_set():
                        if self.session_id:
                            self.cache_manager.update_scan_session(
                                self.session_id,
                                status="paused",
                                stage=self._stage or "collecting",
                            )
                        self.scan_cancelled.emit()
                        return
                    for path in paths:
                        name = os.path.basename(path)
                        if not name:
                            continue
                        key = name.lower() if os.name == "nt" else name
                        name_groups[key].append(path)

                final_duplicates = {}
                for name_key, paths in name_groups.items():
                    if len(paths) > 1:
                        final_duplicates[("NAME_ONLY", name_key)] = paths

            else:
                # 2. Size Filter (Candidates)
                candidates = []
                for size, paths in size_map.items():
                    if len(paths) > 1:
                        for path in paths:
                            meta = self._file_meta.get(path)
                            if not meta:
                                continue
                            candidates.append((path, int(meta[0]), float(meta[1])))

                total_candidates = len(candidates)
                if total_candidates > 0:
                    self._set_stage("analyzing")
                    self._emit_progress(0, f"{strings.tr('status_analyzing')}: {total_candidates}", force=True)

                    # 3. Quick Scan (Parallel)
                    self._set_stage("hashing")
                    temp_hash_map = self._calculate_hashes_parallel(
                        candidates,
                        is_quick_scan=True,
                        seed_session_id=self.base_session_id if self.incremental_rescan else None,
                    )
                    if self._stop_event.is_set():
                        if self.session_id:
                            self.cache_manager.update_scan_session(
                                self.session_id,
                                status="paused",
                                stage=self._stage or "hashing",
                            )
                        self.scan_cancelled.emit()
                        return
                    if self.session_id:
                        self.cache_manager.update_scan_session(self.session_id, stage="hashing")
                    self._set_stage("hashing")

                    # 4. Full Scan & Byte Compare Resolution
                    groups_needing_full_hash = []
                    for key, paths in temp_hash_map.items():
                        if len(paths) < 2:
                            continue
                        size, _, hash_type = key
                        if hash_type == "PARTIAL":
                            groups_needing_full_hash.extend(paths)
                        else:
                            self._process_final_group(key[1], size, paths, final_duplicates)

                    if groups_needing_full_hash:
                        full_candidates = []
                        for path in groups_needing_full_hash:
                            meta = self._file_meta.get(path)
                            if not meta:
                                continue
                            full_candidates.append((path, int(meta[0]), float(meta[1])))

                        full_hash_results = self._calculate_hashes_parallel(
                            full_candidates,
                            is_quick_scan=False,
                            seed_session_id=self.base_session_id if self.incremental_rescan else None,
                        )

                        for key, paths in full_hash_results.items():
                            if len(paths) < 2:
                                continue
                            self._process_final_group(key[1], key[0], paths, final_duplicates)

            # 5. Optional duplicate-folder detection
            if self.detect_duplicate_folders and self._file_meta:
                self._set_stage("folder_dup")
                folder_groups = self._detect_duplicate_folders()
                if folder_groups:
                    final_duplicates.update(folder_groups)

            # 6. Mixed mode: append similar-image groups to the same result map.
            if self.use_similar_image and self.use_mixed_mode:
                similar_groups = self._run_similar_image_scan(
                    image_files=list(self._image_files),
                    emit_result=False,
                )
                if similar_groups:
                    final_duplicates.update(similar_groups)

            self._emit_progress(100, f"{strings.tr('status_done')}! ({time.time() - start_time:.2f}s)", force=True)
            self.latest_file_meta = dict(self._file_meta or {})
            if self.session_id:
                self.cache_manager.update_scan_session(
                    self.session_id,
                    status="completed",
                    stage="completed",
                    progress=100,
                    progress_message=strings.tr("status_done")
                )
            self._set_stage("completed")
            self.scan_finished.emit(final_duplicates)

        except Exception as e:
            import traceback
            traceback.print_exc()
            if self.session_id:
                self.cache_manager.update_scan_session(
                    self.session_id,
                    status="failed",
                    stage="error",
                    progress=0,
                    progress_message=f"Error: {e}"
                )
            self._emit_progress(0, strings.tr("err_scan_failed").format(e), force=True)
            self.scan_failed.emit(str(e))
        finally:
            # 스레드 종료 시 CacheManager 커넥션 정리
            self.cache_manager.close_all()
    
    def _run_similar_image_scan(self, image_files=None, emit_result=True):
        """유사 이미지 탐지 스캔 (similar-only 또는 mixed-mode 보조 단계)."""
        try:
            start_time = time.time()
            self._set_stage(
                "similar_image",
                status="running",
                progress=0,
                progress_message=strings.tr("status_collecting_files"),
            )

            if not hasattr(self, "image_hasher"):
                if emit_result:
                    self.scan_finished.emit({})
                return {}

            if image_files is None:
                image_extensions = {ext.lstrip('.') for ext in self.image_hasher.SUPPORTED_EXTENSIONS}
                self._emit_progress(0, strings.tr("status_collecting_files"), force=True)
                image_files = []
                for folder in self.folders:
                    for entry in self._scandir_recursive(folder):
                        if self._stop_event.is_set():
                            if self.session_id:
                                self.cache_manager.update_scan_session(
                                    self.session_id,
                                    status="paused",
                                    stage=self._stage or "similar_image",
                                )
                            self.scan_cancelled.emit()
                            return {}
                        _, ext = os.path.splitext(entry.name)
                        if ext.lower().replace('.', '') in image_extensions:
                            image_files.append(entry.path)

            image_files = [p for p in (image_files or []) if p]
            if len(image_files) < 2:
                if emit_result:
                    if self.session_id:
                        self.cache_manager.update_scan_session(
                            self.session_id,
                            status="completed",
                            stage="completed",
                            progress=100,
                            progress_message=strings.tr("status_done"),
                        )
                    self._set_stage("completed")
                    self.scan_finished.emit({})
                return {}

            self._emit_progress(10, strings.tr("status_found_images").format(len(image_files)), force=True)

            hash_results = {}
            total = len(image_files)
            processed = 0
            MAX_PENDING = self.max_workers * 4

            session_phashes = {}
            if self.session_id:
                session_phashes = self.cache_manager.load_scan_hashes_for_paths(
                    self.session_id,
                    image_files,
                    hash_type="PHASH",
                )
            seed_phashes = {}
            if self.base_session_id and int(self.base_session_id) != int(self.session_id or 0):
                seed_phashes = self.cache_manager.load_scan_hashes_for_paths(
                    self.base_session_id,
                    image_files,
                    hash_type="PHASH",
                )
            session_hash_batch = []

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {}
                file_iter = iter(image_files)
                active_futures = set()

                def submit_task():
                    nonlocal processed
                    try:
                        path = next(file_iter)
                    except StopIteration:
                        return False

                    try:
                        stat = os.stat(path, follow_symlinks=self.follow_symlinks)
                        size = int(stat.st_size)
                        mtime = float(stat.st_mtime)
                    except OSError:
                        processed += 1
                        return True

                    cached = session_phashes.get((path, "PHASH"))
                    if not cached and seed_phashes:
                        cached = seed_phashes.get((path, "PHASH"))

                    if cached and cached[1] == size and cached[2] == mtime:
                        h = cached[0]
                        if h:
                            hash_results[path] = h
                            if self.session_id:
                                session_hash_batch.append((path, size, mtime, "PHASH", h))
                        processed += 1
                        if processed % 10 == 0:
                            percent = int((processed / total) * 50) + 10
                            self._emit_progress(percent, strings.tr("status_hashing_image").format(processed, total))
                        return True

                    future = executor.submit(self.image_hasher.calculate_phash, path)
                    futures[future] = (path, size, mtime)
                    active_futures.add(future)
                    return True

                for _ in range(min(MAX_PENDING, total)):
                    if not submit_task():
                        break

                while active_futures:
                    if self._stop_event.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        if self.session_id:
                            self.cache_manager.update_scan_session(
                                self.session_id,
                                status="paused",
                                stage=self._stage or "similar_image",
                            )
                        if emit_result:
                            self.scan_cancelled.emit()
                        return {}

                    done, _ = concurrent.futures.wait(active_futures, return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in done:
                        active_futures.remove(future)
                        path, size, mtime = futures.pop(future, (None, 0, 0.0))
                        try:
                            hash_val = future.result()
                            if hash_val and path:
                                hash_results[path] = hash_val
                                if self.session_id:
                                    session_hash_batch.append((path, size, mtime, "PHASH", hash_val))
                        except Exception:
                            pass

                        processed += 1
                        if processed % 10 == 0:
                            percent = int((processed / total) * 50) + 10
                            self._emit_progress(percent, strings.tr("status_hashing_image").format(processed, total))

                        submit_task()

            if self.session_id and session_hash_batch:
                self.cache_manager.save_scan_hashes_batch(self.session_id, session_hash_batch)

            self._set_stage("grouping")
            self._emit_progress(60, strings.tr("status_grouping"), force=True)

            def grouping_progress(current, total_count):
                percent = 60 + int((current / total_count) * 40)
                self._emit_progress(percent, strings.tr("status_grouping_images").format(current, total_count))

            similar_groups = self.image_hasher.group_similar_images(
                hash_results,
                threshold=self.similarity_threshold,
                progress_callback=grouping_progress,
                check_cancel=lambda: self._stop_event.is_set(),
            )

            if self._stop_event.is_set():
                if self.session_id:
                    self.cache_manager.update_scan_session(
                        self.session_id,
                        status="paused",
                        stage=self._stage or "similar_image",
                    )
                if emit_result:
                    self.scan_cancelled.emit()
                return {}

            final_duplicates = {}
            for idx, group in enumerate(similar_groups):
                if len(group) >= 2:
                    try:
                        size = os.path.getsize(group[0])
                    except Exception:
                        size = 0
                    key = (f"similar_{idx}", int(size))
                    final_duplicates[key] = list(group)

            if emit_result:
                self._emit_progress(100, f"{strings.tr('status_done')}! ({time.time() - start_time:.2f}s)", force=True)
                self.latest_file_meta = dict(self._file_meta or {})
                if self.session_id:
                    self.cache_manager.update_scan_session(
                        self.session_id,
                        status="completed",
                        stage="completed",
                        progress=100,
                        progress_message=strings.tr("status_done"),
                    )
                self._set_stage("completed")
                self.scan_finished.emit(final_duplicates)

            return final_duplicates

        except Exception as e:
            import traceback

            traceback.print_exc()
            if self.session_id:
                self.cache_manager.update_scan_session(
                    self.session_id,
                    status="failed",
                    stage="error",
                    progress=0,
                    progress_message=f"Error: {e}",
                )
            if emit_result:
                self._emit_progress(0, strings.tr("err_scan_failed").format(e), force=True)
                self.scan_failed.emit(str(e))
            return {}

    def _detect_duplicate_folders(self):
        """Detect duplicate directories from collected file metadata."""
        if not self._file_meta:
            return {}

        # Build ancestor directory manifests.
        root_norms = [self._normalize_path(r) for r in (self.folders or []) if r]
        dir_members = defaultdict(list)  # dir_path -> [(rel_path, size, mtime, abs_path)]

        for abs_path, (size, mtime) in self._file_meta.items():
            if self._stop_event.is_set():
                return {}
            try:
                file_norm = self._normalize_path(abs_path)
                parent = os.path.dirname(abs_path)
                visited = set()
                while parent and parent not in visited:
                    visited.add(parent)
                    parent_norm = self._normalize_path(parent)
                    if not any(file_norm.startswith(r + os.sep) or file_norm == r for r in root_norms):
                        break
                    try:
                        rel = os.path.relpath(abs_path, parent)
                    except Exception:
                        break
                    dir_members[parent].append((rel.replace("\\", "/"), int(size), float(mtime), abs_path))

                    # Stop when parent is one of scan roots.
                    if any(parent_norm == r for r in root_norms):
                        break
                    next_parent = os.path.dirname(parent)
                    if next_parent == parent:
                        break
                    parent = next_parent
            except Exception:
                continue

        quick_groups = defaultdict(list)
        quick_rows = []
        for dir_path, members in dir_members.items():
            if len(members) < 2:
                continue
            file_count = len(members)
            bytes_total = sum(m[1] for m in members)
            quick_input = "\n".join(f"{rel}\0{size}" for rel, size, _m, _p in sorted(members))
            sig_quick = hashlib.blake2b(quick_input.encode("utf-8"), digest_size=20).hexdigest()
            quick_groups[sig_quick].append((dir_path, members, bytes_total, file_count))
            quick_rows.append((dir_path, sig_quick, None, bytes_total, file_count))

        final_groups = {}
        full_rows = []
        for sig_quick, dirs in quick_groups.items():
            if len(dirs) < 2:
                continue
            by_full = defaultdict(list)
            for dir_path, members, bytes_total, file_count in dirs:
                parts = []
                for rel, size, mtime, abs_path in sorted(members):
                    if self._stop_event.is_set():
                        return {}
                    full_hash, _is_new = self.get_file_hash(abs_path, size=size, mtime=mtime, partial=False)
                    if not full_hash:
                        full_hash = f"size:{size}"
                    parts.append(f"{rel}\0{full_hash}")
                sig_full = hashlib.blake2b("\n".join(parts).encode("utf-8"), digest_size=20).hexdigest()
                by_full[sig_full].append((dir_path, bytes_total, file_count))
                full_rows.append((dir_path, sig_quick, sig_full, bytes_total, file_count))

            for sig_full, rows in by_full.items():
                if len(rows) < 2:
                    continue
                paths = sorted(r[0] for r in rows)
                bytes_total = int(rows[0][1])
                file_count = int(rows[0][2])
                final_groups[("FOLDER_DUP", sig_full, bytes_total, file_count)] = paths

        if self.session_id and (quick_rows or full_rows):
            try:
                by_dir = {}
                for d, sq, sf, bt, fc in quick_rows + full_rows:
                    prev = by_dir.get(d)
                    if prev is None:
                        by_dir[d] = (d, sq, sf, bt, fc)
                    else:
                        by_dir[d] = (d, sq or prev[1], sf or prev[2], bt, fc)
                self.cache_manager.save_scan_folder_sigs_batch(self.session_id, list(by_dir.values()))
            except Exception:
                pass

        return final_groups


    def _process_final_group(self, file_hash, size, paths, final_duplicates):
        """Process a group of files with same hash (and size) for final verification."""
        if not self.byte_compare:
            # No byte compare
            if self.check_name:
                 name_map = defaultdict(list)
                 for p in paths:
                     name_key = (file_hash, size, os.path.basename(p))
                     name_map[name_key].append(p)
                 for nk, nv in name_map.items():
                     if len(nv) > 1: final_duplicates[nk] = nv
            else:
                final_duplicates[(file_hash, size)] = paths
        else:
            # Byte-by-byte compare
            self._byte_compare_group(file_hash, size, paths, final_duplicates)

    def _byte_compare_group(self, file_hash, size, paths, final_duplicates):
        """Perform byte-by-byte comparison on a group."""
        pending = paths[:]
        byte_groups = []
        
        while pending:
            if self._stop_event.is_set(): break
            basis = pending.pop(0)
            current_byte_group = [basis]
            non_matches = []
            
            for candidate in pending:
                if self.compare_files_byte_by_byte(basis, candidate):
                    current_byte_group.append(candidate)
                else:
                    non_matches.append(candidate)
            
            if len(current_byte_group) > 1:
                byte_groups.append(current_byte_group)
            
            pending = non_matches

        for idx, grp in enumerate(byte_groups):
            if self.check_name:
                 name_map = defaultdict(list)
                 for p in grp:
                     name_key = (file_hash, size, os.path.basename(p), f"byte_{idx}")
                     name_map[name_key].append(p)
                 for nk, nv in name_map.items():
                     if len(nv) > 1: final_duplicates[nk] = nv
            else:
                final_duplicates[(file_hash, size, f"byte_{idx}")] = grp
