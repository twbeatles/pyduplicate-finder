from __future__ import annotations

import concurrent.futures

from .common import os, strings, time


class ScanSimilarImagesMixin:
    def _run_similar_image_scan(self, image_files=None, emit_result=True):
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
                image_extensions = {ext.lstrip(".") for ext in self.image_hasher.SUPPORTED_EXTENSIONS}
                self._emit_progress(0, strings.tr("status_collecting_files"), force=True)
                image_files = []
                for folder in self.folders:
                    if self.protect_system and self.is_protected(folder):
                        self._emit_progress(0, strings.tr("status_skip_protected_root").format(folder), force=True)
                        continue
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
                        if ext.lower().replace(".", "") in image_extensions:
                            image_files.append(entry.path)

            image_files = [p for p in (image_files or []) if p]
            if len(image_files) < 2:
                if emit_result:
                    final_status = self._finalize_scan_status()
                    done_msg = strings.tr("status_done_partial") if final_status == "partial" else strings.tr("status_done")
                    if self.session_id:
                        self.cache_manager.update_scan_session(
                            self.session_id,
                            status=final_status,
                            stage="completed",
                            progress=100,
                            progress_message=done_msg,
                        )
                    self._set_stage("completed")
                    self.scan_finished.emit({})
                return {}

            self._emit_progress(10, strings.tr("status_found_images").format(len(image_files)), force=True)

            hash_results = {}
            total = len(image_files)
            processed = 0
            max_pending = self.max_workers * 4

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
            session_hash_batch = {}

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
                    except OSError as e:
                        self._record_scan_error(path, e, stage="similar_image", operation="stat")
                        processed += 1
                        return True

                    cached = session_phashes.get((path, "PHASH"))
                    if not cached and seed_phashes:
                        cached = seed_phashes.get((path, "PHASH"))

                    if cached and cached[1] == size and cached[2] == mtime:
                        h = cached[0]
                        if h:
                            hash_results[path] = h
                            self._inc_metric("files_hashed", 1)
                            if self.session_id:
                                session_hash_batch[(path, "PHASH")] = (path, size, mtime, "PHASH", h)
                        processed += 1
                        if processed % 10 == 0:
                            percent = int((processed / total) * 50) + 10
                            self._emit_progress(percent, strings.tr("status_hashing_image").format(processed, total))
                        return True

                    future = executor.submit(self.image_hasher.calculate_phash, path)
                    futures[future] = (path, size, mtime)
                    active_futures.add(future)
                    return True

                for _ in range(min(max_pending, total)):
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
                                self._inc_metric("files_hashed", 1)
                                if self.session_id:
                                    session_hash_batch[(path, "PHASH")] = (path, size, mtime, "PHASH", hash_val)
                        except Exception as e:
                            self._record_scan_error(path, e, stage="similar_image", operation="phash_future")

                        processed += 1
                        if processed % 10 == 0:
                            percent = int((processed / total) * 50) + 10
                            self._emit_progress(percent, strings.tr("status_hashing_image").format(processed, total))

                        submit_task()

            if self.session_id and session_hash_batch:
                self.cache_manager.save_scan_hashes_batch(self.session_id, list(session_hash_batch.values()))

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
                final_status = self._finalize_scan_status()
                done_msg = strings.tr("status_done_partial") if final_status == "partial" else strings.tr("status_done")
                self._emit_progress(100, f"{done_msg}! ({time.time() - start_time:.2f}s)", force=True)
                self.latest_file_meta = dict(self._file_meta or {})
                if self.session_id:
                    self.cache_manager.update_scan_session(
                        self.session_id,
                        status=final_status,
                        stage="completed",
                        progress=100,
                        progress_message=done_msg,
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
                self.latest_scan_metrics = self._snapshot_metrics()
                self.latest_scan_status = "failed"
                self.latest_scan_warnings = []
                self.scan_failed.emit(str(e))
            return {}
