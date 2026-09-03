from __future__ import annotations

import concurrent.futures
import logging

from .common import BUFFER_SIZE, defaultdict, hashlib, os, strings
from .contracts import ScanWorkerHost

logger = logging.getLogger(__name__)

try:
    from src.core.native.bridge import (
        RustCancellationToken,
        compare_files_byte_by_byte as native_compare_files,
        get_backend_name,
        hash_files_batch,
        is_rust_available,
    )
except ImportError:
    is_rust_available = lambda: False  # noqa: E731
    get_backend_name = lambda pref="auto": "python"  # noqa: E731
    hash_files_batch = None
    native_compare_files = None
    RustCancellationToken = None


class ScanHashingMixin(ScanWorkerHost):
    def _use_rust_hashing(self) -> bool:
        backend = getattr(self, "scan_backend", "auto")
        # If get_file_hash is dynamically patched/overridden on instance, respect it
        fn = getattr(self, "get_file_hash", None)
        if fn is not None:
            underlying = getattr(fn, "__func__", fn)
            if underlying is not ScanHashingMixin.get_file_hash:
                return False
        try:
            return bool(is_rust_available() and get_backend_name(backend) == "rust")
        except Exception:
            return False

    def get_file_hash(self, filepath, size=None, mtime=None, block_size=BUFFER_SIZE, partial=False):
        if size is None or mtime is None:
            try:
                stat = os.stat(filepath)
                size = stat.st_size
                mtime = stat.st_mtime
            except OSError:
                return None, False

        cached = self.cache_manager.get_cached_hash(filepath, size, mtime)
        if cached:
            if partial and cached[0]:
                return cached[0], False
            if not partial and cached[1]:
                return cached[1], False

        hasher = hashlib.blake2b(digest_size=32)
        try:
            with open(filepath, "rb") as f:
                if partial:
                    buf = f.read(4096)
                    hasher.update(buf)
                    if size > 8192:
                        f.seek(-4096, os.SEEK_END)
                        buf = f.read(4096)
                        hasher.update(buf)
                else:
                    while True:
                        if self._stop_event.is_set():
                            return None, False
                        buf = f.read(block_size)
                        if not buf:
                            break
                        hasher.update(buf)

            return hasher.hexdigest(), True
        except OSError as e:
            self._record_scan_error(filepath, e, stage="hashing", operation="read_hash")
            return None, False

    def compare_files_byte_by_byte(self, file1, file2):
        if self._use_rust_hashing() and native_compare_files is not None:
            if getattr(self, "_rust_cancel_token", None) is None and RustCancellationToken is not None:
                self._rust_cancel_token = RustCancellationToken()
            try:
                return bool(native_compare_files(file1, file2, cancel_token=getattr(self, "_rust_cancel_token", None)))
            except Exception:
                pass

        buf_size = BUFFER_SIZE
        try:
            with open(file1, "rb") as f1, open(file2, "rb") as f2:
                while True:
                    if self._stop_event.is_set():
                        return False
                    b1 = f1.read(buf_size)
                    b2 = f2.read(buf_size)
                    if b1 != b2:
                        return False
                    if not b1:
                        return True
        except OSError:
            return False

    def _calculate_hashes_parallel(self, candidates, is_quick_scan=True, seed_session_id=None):
        if self._use_rust_hashing():
            try:
                return self._calculate_hashes_rust(
                    candidates,
                    is_quick_scan=is_quick_scan,
                    seed_session_id=seed_session_id,
                )
            except Exception as e:
                logger.warning("Rust hashing error (%s); falling back to Python hashing", e)

        return self._calculate_hashes_python(
            candidates,
            is_quick_scan=is_quick_scan,
            seed_session_id=seed_session_id,
        )

    def _calculate_hashes_rust(self, candidates, is_quick_scan=True, seed_session_id=None):
        quick_scan_threshold = 10 * 1024 * 1024
        hash_chunk_size = 800
        batch_size = 100
        session_batch_size = 200

        hash_map = defaultdict(list)
        total = len(candidates or [])
        processed = 0
        if total <= 0:
            return hash_map

        if getattr(self, "_rust_cancel_token", None) is None and RustCancellationToken is not None:
            self._rust_cancel_token = RustCancellationToken()

        progress_step = max(10, min(500, total // 200 if total >= 200 else 10))
        db_batch = []
        session_hash_batch = {}

        def emit_hash_progress(force=False):
            if force or (processed % progress_step == 0) or processed == total:
                percent = int((processed / total) * 40) + (0 if is_quick_scan else 50)
                self._emit_progress(percent, strings.tr("status_hashing_progress").format(processed, total))

        for chunk_start in range(0, total, hash_chunk_size):
            if self._stop_event.is_set():
                if self._rust_cancel_token:
                    self._rust_cancel_token.cancel()
                break

            chunk = candidates[chunk_start:chunk_start + hash_chunk_size]
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

            # Partition chunk into cache hits and cache misses
            miss_items = []
            miss_types = {}  # filepath -> (partial, type_str)

            for filepath, size, mtime in chunk:
                if self._stop_event.is_set():
                    break

                partial = bool(is_quick_scan and int(size) >= quick_scan_threshold)
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
                        if type_str == "FULL":
                            self._full_hash_values[filepath] = digest
                        self._inc_metric("files_hashed", 1)
                        if self.session_id:
                            session_hash_batch[(filepath, type_str)] = (filepath, size, mtime, type_str, digest)
                    processed += 1
                    emit_hash_progress()
                else:
                    miss_items.append((filepath, int(size), float(mtime)))
                    miss_types[filepath] = (partial, type_str)

            if self._stop_event.is_set():
                break

            if miss_items and hash_files_batch is not None:
                # Group misses by partial flag so we can pass uniform partial mode to Rust batch
                partial_misses = [item for item in miss_items if miss_types[item[0]][0]]
                full_misses = [item for item in miss_items if not miss_types[item[0]][0]]

                batches_to_run = []
                if partial_misses:
                    batches_to_run.append((partial_misses, True))
                if full_misses:
                    batches_to_run.append((full_misses, False))

                for batch_items, partial_flag in batches_to_run:
                    if self._stop_event.is_set():
                        break

                    results = hash_files_batch(
                        batch_items,
                        partial=partial_flag,
                        max_workers=self.max_workers,
                        cancel_token=self._rust_cancel_token,
                    )

                    for r in results:
                        filepath = r.path
                        size = r.size
                        mtime = r.mtime
                        type_str = "PARTIAL" if partial_flag else "FULL"

                        if r.status == "ok" and r.digest:
                            digest = r.digest
                            hash_map[(size, digest, type_str)].append(filepath)
                            if type_str == "FULL":
                                self._full_hash_values[filepath] = digest
                            self._inc_metric("files_hashed", 1)
                            if self.session_id:
                                session_hash_batch[(filepath, type_str)] = (filepath, size, mtime, type_str, digest)
                            db_batch.append(
                                (
                                    filepath,
                                    size,
                                    mtime,
                                    digest if partial_flag else None,
                                    digest if not partial_flag else None,
                                )
                            )
                        elif r.status == "error":
                            err_msg = r.error or "Rust hash error"
                            if "Access is denied" in err_msg or "Permission denied" in err_msg:
                                exc = PermissionError(err_msg)
                            else:
                                exc = OSError(err_msg)
                            self._record_scan_error(path=filepath, exc=exc, stage="hashing", operation="rust_hash")

                        processed += 1
                        emit_hash_progress()

                        if len(db_batch) >= batch_size:
                            self.cache_manager.update_cache_batch(db_batch)
                            db_batch.clear()
                        if self.session_id and len(session_hash_batch) >= session_batch_size:
                            self.cache_manager.save_scan_hashes_batch(self.session_id, list(session_hash_batch.values()))
                            session_hash_batch.clear()

        if db_batch:
            self.cache_manager.update_cache_batch(db_batch)
        if self.session_id and session_hash_batch:
            self.cache_manager.save_scan_hashes_batch(self.session_id, list(session_hash_batch.values()))
        emit_hash_progress(force=True)
        return hash_map

    def _calculate_hashes_python(self, candidates, is_quick_scan=True, seed_session_id=None):
        quick_scan_threshold = 10 * 1024 * 1024
        hash_chunk_size = 800
        batch_size = 100
        session_batch_size = 200
        max_pending_tasks = self.max_workers * 4

        hash_map = defaultdict(list)
        total = len(candidates or [])
        processed = 0
        if total <= 0:
            return hash_map

        progress_step = max(10, min(500, total // 200 if total >= 200 else 10))
        db_batch = []
        session_hash_batch = {}

        def emit_hash_progress(force=False):
            if force or (processed % progress_step == 0) or processed == total:
                percent = int((processed / total) * 40) + (0 if is_quick_scan else 50)
                self._emit_progress(percent, strings.tr("status_hashing_progress").format(processed, total))

        def task_wrapper(fp, s, m, p):
            return fp, s, m, p, self.get_file_hash(fp, s, m, block_size=BUFFER_SIZE, partial=p)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for chunk_start in range(0, total, hash_chunk_size):
                if self._stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                chunk = candidates[chunk_start:chunk_start + hash_chunk_size]
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

                    partial = bool(is_quick_scan and int(size) >= quick_scan_threshold)
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
                            if type_str == "FULL":
                                self._full_hash_values[filepath] = digest
                            self._inc_metric("files_hashed", 1)
                            if self.session_id:
                                session_hash_batch[(filepath, type_str)] = (filepath, size, mtime, type_str, digest)
                        processed += 1
                        emit_hash_progress()
                        return True

                    future = executor.submit(task_wrapper, filepath, size, mtime, partial)
                    active_futures.add(future)
                    return True

                for _ in range(min(max_pending_tasks, len(chunk))):
                    if not submit_task():
                        break

                while active_futures:
                    if self._stop_event.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                    done, _ = concurrent.futures.wait(active_futures, return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in done:
                        active_futures.remove(future)
                        path_hint = ""
                        try:
                            filepath, size, mtime, partial, result_tuple = future.result()
                            path_hint = filepath
                            digest, is_newly_calculated = result_tuple
                            if digest:
                                type_str = "PARTIAL" if partial else "FULL"
                                hash_map[(size, digest, type_str)].append(filepath)
                                if type_str == "FULL":
                                    self._full_hash_values[filepath] = digest
                                self._inc_metric("files_hashed", 1)
                                if self.session_id:
                                    session_hash_batch[(filepath, type_str)] = (filepath, size, mtime, type_str, digest)
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
                        except Exception as e:
                            self._record_scan_error(path=path_hint, exc=e, stage="hashing", operation="future_result")

                        if len(db_batch) >= batch_size:
                            self.cache_manager.update_cache_batch(db_batch)
                            db_batch.clear()
                        if self.session_id and len(session_hash_batch) >= session_batch_size:
                            self.cache_manager.save_scan_hashes_batch(self.session_id, list(session_hash_batch.values()))
                            session_hash_batch.clear()

                        processed += 1
                        emit_hash_progress()
                        submit_task()

        if db_batch:
            self.cache_manager.update_cache_batch(db_batch)
        if self.session_id and session_hash_batch:
            self.cache_manager.save_scan_hashes_batch(self.session_id, list(session_hash_batch.values()))
        emit_hash_progress(force=True)
        return hash_map
