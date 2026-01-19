from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import hashlib
import os
import platform
import time
import fnmatch
from collections import defaultdict
import concurrent.futures
from src.core.cache_manager import CacheManager
from src.utils.i18n import strings

# 유사 이미지 탐지 (선택적)
try:
    from src.core.image_hash import ImageHasher, is_available as image_hash_available
    IMAGE_HASH_AVAILABLE = image_hash_available()
except ImportError:
    IMAGE_HASH_AVAILABLE = False

BUFFER_SIZE = 1024 * 1024  # 1MB buffer for faster I/O

class ScanWorker(QThread):
    progress_updated = Signal(int, str)
    scan_finished = Signal(object)

    def __init__(self, folders, check_name=False, min_size_kb=0, extensions=None, 
                 protect_system=True, byte_compare=False, max_workers=None,
                 exclude_patterns=None, name_only=False,
                 use_similar_image=False, similarity_threshold=0.9):
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
        self._is_running = True
        self._init_protected_paths()
        self.cache_manager = CacheManager()
        self.max_workers = max_workers or (os.cpu_count() or 4)
        
        # Physical file tracking (Dev, Inode)
        self.seen_inodes = set()

        # Progress throttling
        self._last_progress_update_time = 0
        self._progress_update_interval = 0.1  # 100ms
        self._progress_mutex = QMutex()
        
        # 유사 이미지 탐지기
        if self.use_similar_image:
            self.image_hasher = ImageHasher()

    def _init_protected_paths(self):
        self.protected_paths = []
        if self.protect_system:
            if platform.system() == "Windows":
                # Typical Windows system paths
                sys_drive = os.environ.get('SystemDrive', 'C:')
                self.protected_paths = [
                    os.path.join(sys_drive, '\\Windows'),
                    os.path.join(sys_drive, '\\Program Files'),
                    os.path.join(sys_drive, '\\Program Files (x86)'),
                    os.path.join(sys_drive, '\\ProgramData'),
                ]
            else:
                # Unix-like system paths
                self.protected_paths = [
                    '/bin', '/boot', '/dev', '/etc', '/lib', '/lib64', 
                    '/proc', '/root', '/run', '/sbin', '/sys', '/usr', '/var'
                ]
            # Normalize paths
            self.protected_paths = [os.path.normpath(p).lower() for p in self.protected_paths]

    def is_protected(self, path):
        if not self.protect_system: return False
        try:
            norm_path = os.path.normpath(path).lower()
            for p in self.protected_paths:
                if norm_path.startswith(p):
                    return True
        except:
            return False
        return False

    def _should_exclude(self, path):
        """제외 패턴과 일치하는지 확인"""
        if not self.exclude_patterns:
            return False
        
        name = os.path.basename(path)
        for pattern in self.exclude_patterns:
            # 파일명과 전체 경로 모두 매칭 시도
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path, pattern):
                return True
        return False

    def stop(self):
        self._is_running = False

    def _emit_progress(self, value, message, force=False):
        """Thread-safe and throttled progress emission."""
        if not self._is_running: return

        current_time = time.time()
        with QMutexLocker(self._progress_mutex):
            if force or (current_time - self._last_progress_update_time >= self._progress_update_interval):
                self.progress_updated.emit(value, message)
                self._last_progress_update_time = current_time

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
                        if not self._is_running: return None, False
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
                    if not self._is_running: return False
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
                    if not self._is_running: break
                    
                    if entry.is_dir(follow_symlinks=False):
                        if self.protect_system and self.is_protected(entry.path):
                            continue
                        yield from self._scandir_recursive(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        # 제외 패턴 확인
                        if self._should_exclude(entry.path):
                            continue
                        # print(f"DEBUG: Yielding file {entry.name}")
                        if self.extensions:
                            # entry.name is filename
                            _, ext = os.path.splitext(entry.name)
                            if ext.lower().replace('.', '') not in self.extensions:
                                continue
                        yield entry
        except OSError as e:
            print(f"DEBUG: Scandir Error: {e}")
            return

    def _scan_files(self):
        """Step 1: File collection and size filtering using cached os.scandir entries."""
        size_map = defaultdict(list)
        self._emit_progress(0, strings.tr("status_collecting_files"), force=True)
        
        file_count = 0
        for folder in self.folders:
            # print(f"DEBUG: Scandir on {folder}")
            for entry in self._scandir_recursive(folder):
                if not self._is_running: break
                
                try:
                    # stat() result is cached in entry object on Windows usually
                    stat = entry.stat(follow_symlinks=False)
                    
                    # Fix for Windows: entry.stat() might return st_ino=0
                    if stat.st_ino == 0:
                        stat = os.stat(entry.path)
                    
                    # Physical file check
                    inode_key = (stat.st_dev, stat.st_ino)
                    if inode_key in self.seen_inodes:
                        continue
                    self.seen_inodes.add(inode_key)

                    size = stat.st_size
                    if size >= self.min_size and size > 0:
                        size_map[size].append(entry.path) # We only store path to save memory
                        
                    file_count += 1
                    if file_count % 1000 == 0:
                         self._emit_progress(0, f"{strings.tr('status_collecting_files')}: {file_count}")

                except OSError:
                    continue
        # print(f"DEBUG: Size map keys: {len(size_map)}, Total files: {file_count}")
                    
        return size_map

    def _calculate_hashes_parallel(self, candidates, is_quick_scan=True):
        """Helper to calculate hashes in parallel with batch DB updates."""
        QUICK_SCAN_THRESHOLD = 10 * 1024 * 1024 
        hash_map = defaultdict(list)
        
        total = len(candidates)
        processed = 0
        
        # Batching for DB updates
        db_batch = []
        BATCH_SIZE = 100

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_info = {}
            for filepath in candidates:
                if not self._is_running: break
                
                try:
                    # We need size/mtime for cache lookup anyway
                    # Since we only passed paths, we might need to stat again if we didn't store it.
                    # Optimization: In _scan_files we could store (path, size, mtime) but that consumes more RAM.
                    # Getting stat here again is relatively cheap (OS filesystem cache).
                    stat = os.stat(filepath)
                    size = stat.st_size
                    mtime = stat.st_mtime
                    
                    partial = is_quick_scan and (size >= QUICK_SCAN_THRESHOLD)
                    
                    future = executor.submit(self.get_file_hash, filepath, size, mtime, block_size=BUFFER_SIZE, partial=partial)
                    future_to_info[future] = (filepath, size, mtime, partial)
                except OSError:
                    continue

            for future in concurrent.futures.as_completed(future_to_info):
                if not self._is_running: 
                    # Python 3.9+ cancel_futures 옵션으로 안전 종료
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                
                filepath, size, mtime, partial = future_to_info[future]
                try:
                    digest, is_newly_calculated = future.result()
                    if digest:
                        type_str = "PARTIAL" if partial else "FULL"
                        key = (size, digest, type_str)
                        hash_map[key].append(filepath)
                        
                        if is_newly_calculated:
                            # Queue for batch update
                            entry_partial = digest if partial else None
                            entry_full = digest if not partial else None
                            db_batch.append((filepath, size, mtime, entry_partial, entry_full))
                            
                except Exception as e:
                    pass
                
                # Process Batch
                if len(db_batch) >= BATCH_SIZE:
                    self.cache_manager.update_cache_batch(db_batch)
                    db_batch = []

                processed += 1
                percent = int((processed / total) * 40) + (0 if is_quick_scan else 50)
                if processed % 10 == 0: # Throttling update messages slightly
                     msg = f"{strings.tr('status_hashing_progress').format(processed, total)}"
                     self._emit_progress(percent, msg)

        # Flush remaining batch
        if db_batch:
            self.cache_manager.update_cache_batch(db_batch)

        return hash_map

    def run(self):
        try:
            start_time = time.time()
            self.seen_inodes.clear()
            
            # 유사 이미지 모드
            if self.use_similar_image:
                self._run_similar_image_scan()
                return
            
            # 1. File Collection
            size_map = self._scan_files()
            if not self._is_running:
                self.scan_finished.emit({})
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

            self._emit_progress(0, f"{strings.tr('status_analyzing')}: {total_candidates}", force=True)

            # 3. Quick Scan (Parallel)
            # (Size, Hash, Type) -> [paths]
            temp_hash_map = self._calculate_hashes_parallel(candidates, is_quick_scan=True)
            if not self._is_running:
                self.scan_finished.emit({})
                return

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
            self.scan_finished.emit(final_duplicates)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._emit_progress(0, f"Error: {e}")
            self.scan_finished.emit({})
        finally:
            # 스레드 종료 시 CacheManager 커넥션 정리
            self.cache_manager.close()
    
    def _run_similar_image_scan(self):
        """유사 이미지 탐지 스캔"""
        try:
            start_time = time.time()
            
            # 이미지 확장자
            image_extensions = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'tif'}
            
            # 1. 이미지 파일 수집
            self._emit_progress(0, strings.tr("status_collecting_files"), force=True)
            image_files = []
            
            for folder in self.folders:
                for entry in self._scandir_recursive(folder):
                    if not self._is_running:
                        self.scan_finished.emit({})
                        return
                    
                    _, ext = os.path.splitext(entry.name)
                    if ext.lower().replace('.', '') in image_extensions:
                        image_files.append(entry.path)
            
            if len(image_files) < 2:
                self.scan_finished.emit({})
                return
            
            self._emit_progress(10, strings.tr("status_found_images").format(len(image_files)), force=True)
            
            # 2. pHash 계산
            hash_results = {}
            total = len(image_files)
            
            for idx, path in enumerate(image_files):
                if not self._is_running:
                    self.scan_finished.emit({})
                    return
                
                hash_val = self.image_hasher.calculate_phash(path)
                if hash_val:
                    hash_results[path] = hash_val
                
                if (idx + 1) % 10 == 0:
                    percent = int((idx / total) * 50) + 10
                    self._emit_progress(percent, strings.tr("status_hashing_image").format(idx + 1, total))
            
            # 3. 유사 이미지 그룹핑
            self._emit_progress(60, strings.tr("status_grouping"), force=True)
            
            def grouping_progress(current, total):
                percent = 60 + int((current / total) * 40)
                self._emit_progress(percent, strings.tr("status_grouping_images").format(current, total))

            similar_groups = self.image_hasher.group_similar_images(
                hash_results, 
                threshold=self.similarity_threshold,
                progress_callback=grouping_progress,
                check_cancel=lambda: not self._is_running
            )
            
            # 취소 확인
            if not self._is_running:
                self.scan_finished.emit({})
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
            self.scan_finished.emit(final_duplicates)
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._emit_progress(0, f"Error: {e}")
            self.scan_finished.emit({})
        finally:
            # 스레드 종료 시 CacheManager 커넥션 정리
            self.cache_manager.close()


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
            if not self._is_running: break
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
