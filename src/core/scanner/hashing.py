from __future__ import annotations

import concurrent.futures

from .common import BUFFER_SIZE, defaultdict, hashlib, os, strings
from .contracts import ScanWorkerHost


class ScanHashingMixin(ScanWorkerHost):
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
