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
try:
    from src.core.image_hash import ImageHasher, is_available as image_hash_available
    IMAGE_HASH_AVAILABLE = image_hash_available()
except ImportError:
    IMAGE_HASH_AVAILABLE = False

BUFFER_SIZE = 1024 * 1024  # 1MB buffer for faster I/O

class ScanWorker(QThread):
    progress_updated = Signal(int, str)
    stage_updated = Signal(str)  # stage code for UI
    scan_finished = Signal(object)  # dict of results, or None if cancelled
    scan_cancelled = Signal()  # Issue #3: Separate signal for cancellation
    scan_failed = Signal(str)  # error message

    def __init__(self, folders, check_name=False, min_size_kb=0, extensions=None,
                 protect_system=True, byte_compare=False, max_workers=None,
                 exclude_patterns=None, name_only=False,
                 use_similar_image=False, similarity_threshold=0.9,
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
        self.use_similar_image = use_similar_image and IMAGE_HASH_AVAILABLE  # 유사 이미지 탐지
        self.similarity_threshold = similarity_threshold
        self._stop_event = threading.Event() # Thread-safe cancellation signal
        self._init_protected_paths()
        self.cache_manager = CacheManager()
        self.max_workers = max_workers or (os.cpu_count() or 4)
        self.session_id = session_id
        self.use_cached_files = use_cached_files
        
        # Physical file tracking (Dev, Inode)
        self.seen_inodes = set()

        # Progress throttling
        self._last_progress_update_time = 0
        self._progress_update_interval = 0.1  # 100ms
        self._progress_mutex = QMutex()
        self._stage = None
        
        # 유사 이미지 탐지기
        if self.use_similar_image:
            self.image_hasher = ImageHasher()

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

    def _should_exclude(self, path):
        """제외 패턴과 일치하는지 확인"""
        if not self.exclude_patterns:
            return False

        def normalize_match(value):
            normalized = os.path.normpath(value).replace("\\", "/")
            if os.name == "nt":
                return normalized.lower()
            return normalized

        name = os.path.basename(path)
        name_match = name.lower() if os.name == "nt" else name
        path_match = normalize_match(path)

        for pattern in self.exclude_patterns:
            if not pattern:
                continue
            pattern_match = pattern.lower() if os.name == "nt" else pattern
            # 파일명과 전체 경로 모두 매칭 시도
            if fnmatch.fnmatchcase(name_match, pattern_match):
                return True
            if fnmatch.fnmatchcase(path_match, normalize_match(pattern)):
                return True
        return False

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

    def _scandir_recursive(self, path):
        """Recursive os.scandir generator"""
        # print(f"DEBUG: Entering _scandir_recursive({path})")
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if self._stop_event.is_set(): break

                    if self._should_exclude(entry.path):
                        continue

                    if entry.is_dir(follow_symlinks=False):
                        if self.protect_system and self.is_protected(entry.path):
                            continue
                        yield from self._scandir_recursive(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        # print(f"DEBUG: Yielding file {entry.name}")
                        if self.extensions:
                            # entry.name is filename
                            _, ext = os.path.splitext(entry.name)
                            if ext.lower().replace('.', '') not in self.extensions:
                                continue
                        yield entry
        except OSError as e:
            if DEBUG_SCAN:
                logger.warning("[scan] Scandir error: %s", e)
            return

    def _scan_files(self):
        """Step 1: File collection and size filtering using cached os.scandir entries."""
        size_map = defaultdict(list)
        self._emit_progress(0, strings.tr("status_collecting_files"), force=True)

        if self.session_id and self.use_cached_files:
            if self.cache_manager.has_scan_files(self.session_id):
                return self._scan_files_from_cache(self.cache_manager.iter_scan_files(self.session_id))
        
        file_count = 0
        db_batch = []
        DB_BATCH_SIZE = 1000
        for folder in self.folders:
            # print(f"DEBUG: Scandir on {folder}")
            for entry in self._scandir_recursive(folder):
                if self._stop_event.is_set(): break
                
                try:
                    # stat() result is cached in entry object on Windows usually
                    stat = entry.stat(follow_symlinks=False)
                    
                    # Fix for Windows: entry.stat() might return st_ino=0
                    if stat.st_ino == 0:
                        stat = os.stat(entry.path)
                    
                    # Physical file check
                    if stat.st_ino:
                        inode_key = (stat.st_dev, stat.st_ino)
                        if inode_key in self.seen_inodes:
                            continue
                        self.seen_inodes.add(inode_key)

                    size = stat.st_size
                    if size >= self.min_size and size > 0:
                        size_map[size].append(entry.path) # We only store path to save memory
                        if self.session_id:
                            db_batch.append((entry.path, size, stat.st_mtime))
                            if len(db_batch) >= DB_BATCH_SIZE:
                                self.cache_manager.save_scan_files_batch(self.session_id, db_batch)
                                db_batch.clear()
                        
                    file_count += 1
                    if file_count % 1000 == 0:
                         self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")

                except OSError:
                    continue
        if self.session_id and db_batch:
            self.cache_manager.save_scan_files_batch(self.session_id, db_batch)
        # print(f"DEBUG: Size map keys: {len(size_map)}, Total files: {file_count}")
                    
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
            if self._should_exclude(path):
                continue
            if self.extensions:
                _, ext = os.path.splitext(path)
                if ext.lower().replace('.', '') not in self.extensions:
                    continue
            try:
                stat = os.stat(path)
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

            file_count += 1
            if file_count % 1000 == 0:
                self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")

        if self.session_id and update_entries:
            self.cache_manager.save_scan_files_batch(self.session_id, update_entries)
        if self.session_id and missing_paths:
            self.cache_manager.remove_scan_files(self.session_id, missing_paths)

        return size_map

    def _calculate_hashes_parallel(self, candidates, is_quick_scan=True):
        """Helper to calculate hashes in parallel with batch DB updates and Bounded Processing."""
        QUICK_SCAN_THRESHOLD = 10 * 1024 * 1024 
        hash_map = defaultdict(list)
        
        total = len(candidates)
        processed = 0
        
        # Batching for DB updates
        db_batch = []
        BATCH_SIZE = 100
        session_hash_batch = []
        SESSION_BATCH_SIZE = 200

        session_hashes = {}
        if self.session_id:
            if is_quick_scan:
                session_hashes = self.cache_manager.load_scan_hashes_for_paths(self.session_id, candidates)
            else:
                session_hashes = self.cache_manager.load_scan_hashes_for_paths(self.session_id, candidates, hash_type="FULL")
        
        # Bound the number of active futures to prevent OOM
        MAX_PENDING_TASKS = self.max_workers * 4

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_info = {}
            candidate_iter = iter(candidates)
            active_futures = set()
            
            # Helper to process done futures
            def process_done_futures(done_subset):
                nonlocal processed, db_batch, future_to_info, session_hash_batch
                for future in done_subset:
                    active_futures.remove(future)
                    # future_to_info might not have the future if we didn't store it or already removed it
                    if future in future_to_info:
                        del future_to_info[future]
                    
                    try:
                        filepath, size, mtime, partial, result_tuple = future.result()
                        digest, is_newly_calculated = result_tuple
                        
                        if digest:
                            type_str = "PARTIAL" if partial else "FULL"
                            key = (size, digest, type_str)
                            hash_map[key].append(filepath)
                            
                            if self.session_id:
                                session_hash_batch.append((filepath, size, mtime, type_str, digest))

                            if is_newly_calculated:
                                entry_partial = digest if partial else None
                                entry_full = digest if not partial else None
                                db_batch.append((filepath, size, mtime, entry_partial, entry_full))
                    except Exception as e:
                        # Log error if needed
                        pass
                    
                    # Process Batch
                    if len(db_batch) >= BATCH_SIZE:
                        self.cache_manager.update_cache_batch(db_batch)
                        db_batch.clear()
                    if self.session_id and len(session_hash_batch) >= SESSION_BATCH_SIZE:
                        self.cache_manager.save_scan_hashes_batch(self.session_id, session_hash_batch)
                        session_hash_batch.clear()

                    processed += 1
                    if processed % 10 == 0:
                        percent = int((processed / total) * 40) + (0 if is_quick_scan else 50)
                        msg = f"{strings.tr('status_hashing_progress').format(processed, total)}"
                        self._emit_progress(percent, msg)

            while True:
                # 1. Fill queue up to limit
                while len(active_futures) < MAX_PENDING_TASKS:
                    if self._stop_event.is_set(): break
                    try:
                        filepath = next(candidate_iter)
                        
                        try:
                            # We might need stat again
                            stat = os.stat(filepath)
                            size = stat.st_size
                            mtime = stat.st_mtime
                            partial = is_quick_scan and (size >= QUICK_SCAN_THRESHOLD)
                            type_str = "PARTIAL" if partial else "FULL"

                            if self.session_id:
                                cached = session_hashes.get((filepath, type_str))
                                if cached and cached[1] == size and cached[2] == mtime:
                                    digest = cached[0]
                                    key = (size, digest, type_str)
                                    hash_map[key].append(filepath)
                                    processed += 1
                                    if processed % 10 == 0:
                                        percent = int((processed / total) * 40) + (0 if is_quick_scan else 50)
                                        msg = f"{strings.tr('status_hashing_progress').format(processed, total)}"
                                        self._emit_progress(percent, msg)
                                    continue
                            
                            # Wrapper to return context with result
                            def task_wrapper(fp, s, m, p):
                                return fp, s, m, p, self.get_file_hash(fp, s, m, block_size=BUFFER_SIZE, partial=p)

                            future = executor.submit(task_wrapper, filepath, size, mtime, partial)
                            future_to_info[future] = filepath 
                            active_futures.add(future)
                        except OSError:
                            processed += 1 # Count skipped files as processed
                            continue
                            
                    except StopIteration:
                        break
                
                # Check stop or done
                if self._stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                
                if not active_futures:
                    break
                
                # 2. Wait for at least one task to complete
                done, _ = concurrent.futures.wait(active_futures, return_when=concurrent.futures.FIRST_COMPLETED)
                process_done_futures(done)

        # Flush remaining batch
        if db_batch:
            self.cache_manager.update_cache_batch(db_batch)
        if self.session_id and session_hash_batch:
            self.cache_manager.save_scan_hashes_batch(self.session_id, session_hash_batch)

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
            
            # 유사 이미지 모드
            if self.use_similar_image:
                self._run_similar_image_scan()
                return
            
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

                self._emit_progress(100, strings.tr("status_done"), force=True)
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
                return

            # 2. Size Filter (Candidates)
            candidates = []
            for size, paths in size_map.items():
                if len(paths) > 1:
                    candidates.extend(paths)

            total_candidates = len(candidates)
            if total_candidates == 0:
                self.scan_finished.emit({})
                return

            self._set_stage("analyzing")
            self._emit_progress(0, f"{strings.tr('status_analyzing')}: {total_candidates}", force=True)

            # 3. Quick Scan (Parallel)
            # (Size, Hash, Type) -> [paths]
            self._set_stage("hashing")
            temp_hash_map = self._calculate_hashes_parallel(candidates, is_quick_scan=True)
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
            final_duplicates = {}
            
            # Identify groups needing full hash
            groups_needing_full_hash = []
            for key, paths in temp_hash_map.items():
                if len(paths) < 2: continue
                size, _, hash_type = key
                if hash_type == "PARTIAL":
                     groups_needing_full_hash.extend(paths)
                else:
                    # Already FULL, verify matches
                    self._process_final_group(key[1], size, paths, final_duplicates)

            # Run Full Hash for required files
            if groups_needing_full_hash:
                # Re-hash fully
                full_hash_results = self._calculate_hashes_parallel(groups_needing_full_hash, is_quick_scan=False)
                
                for key, paths in full_hash_results.items():
                    if len(paths) < 2: continue
                    self._process_final_group(key[1], key[0], paths, final_duplicates)

            self._emit_progress(100, f"{strings.tr('status_done')}! ({time.time() - start_time:.2f}s)", force=True)
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
    
    def _run_similar_image_scan(self):
        """유사 이미지 탐지 스캔"""
        try:
            start_time = time.time()
            self._set_stage(
                "similar_image",
                status="running",
                progress=0,
                progress_message=strings.tr("status_collecting_files"),
            )
            
            # Issue #7: Reuse ImageHasher.SUPPORTED_EXTENSIONS instead of hardcoding
            # Convert from {'.jpg', '.jpeg', ...} to {'jpg', 'jpeg', ...}
            image_extensions = {ext.lstrip('.') for ext in self.image_hasher.SUPPORTED_EXTENSIONS}
            
            # 1. 이미지 파일 수집
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
                        return
                    
                    _, ext = os.path.splitext(entry.name)
                    if ext.lower().replace('.', '') in image_extensions:
                        image_files.append(entry.path)
            
            if len(image_files) < 2:
                if self.session_id:
                    self.cache_manager.update_scan_session(
                        self.session_id,
                        status="completed",
                        stage="completed",
                        progress=100,
                        progress_message=strings.tr("status_done")
                    )
                self._set_stage("completed")
                self.scan_finished.emit({})
                return
            
            self._emit_progress(10, strings.tr("status_found_images").format(len(image_files)), force=True)
            
            # 2. pHash 계산 (병렬 처리)
            hash_results = {}
            total = len(image_files)
            processed = 0
            
            # Bounded parallel execution
            MAX_PENDING = self.max_workers * 4
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {}
                file_iter = iter(image_files)
                active_futures = set()
                
                def submit_task():
                    try:
                        path = next(file_iter)
                        future = executor.submit(self.image_hasher.calculate_phash, path)
                        futures[future] = path
                        active_futures.add(future)
                        return True
                    except StopIteration:
                        return False
                
                # Initial batch
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
                        self.scan_cancelled.emit()
                        return
                    
                    done, _ = concurrent.futures.wait(active_futures, return_when=concurrent.futures.FIRST_COMPLETED)
                    
                    for future in done:
                        active_futures.remove(future)
                        path = futures.pop(future, None)
                        
                        try:
                            hash_val = future.result()
                            if hash_val:
                                hash_results[path] = hash_val
                        except:
                            pass
                        
                        processed += 1
                        if processed % 10 == 0:
                            percent = int((processed / total) * 50) + 10
                            self._emit_progress(percent, strings.tr("status_hashing_image").format(processed, total))
                        
                        # Submit next task
                        submit_task()
            
            # 3. 유사 이미지 그룹핑
            self._set_stage("grouping")
            self._emit_progress(60, strings.tr("status_grouping"), force=True)
            
            def grouping_progress(current, total):
                percent = 60 + int((current / total) * 40)
                self._emit_progress(percent, strings.tr("status_grouping_images").format(current, total))

            similar_groups = self.image_hasher.group_similar_images(
                hash_results, 
                threshold=self.similarity_threshold,
                progress_callback=grouping_progress,
                check_cancel=lambda: self._stop_event.is_set()
            )
            
            # 취소 확인
            if self._stop_event.is_set():
                if self.session_id:
                    self.cache_manager.update_scan_session(
                        self.session_id,
                        status="paused",
                        stage=self._stage or "similar_image",
                    )
                self.scan_cancelled.emit()
                return
            
            # 4. 결과 변환
            final_duplicates = {}
            for idx, group in enumerate(similar_groups):
                if len(group) >= 2:
                    # 첫 번째 파일의 크기를 키로 사용
                    try:
                        size = os.path.getsize(group[0])
                    except:
                        size = 0
                    key = (f"similar_{idx}", size)
                    final_duplicates[key] = list(group)
            
            self._emit_progress(100, f"{strings.tr('status_done')}! ({time.time() - start_time:.2f}s)", force=True)
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
            # 스레드 종료 시 CacheManager 커넥션 정리 (모든 스레드)
            self.cache_manager.close_all()


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
