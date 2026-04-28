from __future__ import annotations

import concurrent.futures

from .common import os, strings, time
from .contracts import ScanWorkerHost


class ScanSimilarDocumentsMixin(ScanWorkerHost):
    def _run_similar_document_scan(self, document_files=None, emit_result=True):
        try:
            start_time = time.time()
            self._set_stage(
                "similar_document",
                status="running",
                progress=0,
                progress_message=strings.tr("status_collecting_files"),
            )
            if not hasattr(self, "document_hasher"):
                if emit_result:
                    self.scan_finished.emit({})
                return {}

            if document_files is None:
                self._emit_progress(0, strings.tr("status_collecting_files"), force=True)
                document_files = []
                for folder in self.folders:
                    if self.protect_system and self.is_protected(folder):
                        continue
                    for entry in self._scandir_recursive(folder):
                        if self._stop_event.is_set():
                            if emit_result:
                                self.scan_cancelled.emit()
                            return {}
                        if self.document_hasher.is_supported(entry.path):
                            document_files.append(entry.path)

            document_files = [p for p in (document_files or []) if p]
            if len(document_files) < 2:
                if emit_result:
                    self.scan_finished.emit({})
                return {}

            hash_results = {}
            total = len(document_files)
            processed = 0
            signature_batch = []
            progress_step = max(10, min(500, total // 100 if total else 10))

            def emit_progress(force=False):
                if force or processed % progress_step == 0 or processed == total:
                    percent = 15 + int((processed / total) * 45)
                    self._emit_progress(percent, strings.tr("status_hashing_document").format(processed, total))

            def task_wrapper(path, size, mtime):
                return path, size, mtime, self.document_hasher.calculate_simhash(path)

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {}
                for path in document_files:
                    try:
                        stat = os.stat(path, follow_symlinks=self.follow_symlinks)
                        size = int(stat.st_size)
                        mtime = float(stat.st_mtime)
                    except OSError as e:
                        self._record_scan_error(path, e, stage="similar_document", operation="stat")
                        continue
                    cached = self.cache_manager.get_cached_signature(path, size, mtime, "DOC_SIMHASH")
                    if cached:
                        hash_results[path] = cached
                        processed += 1
                        emit_progress()
                        continue
                    future = executor.submit(task_wrapper, path, size, mtime)
                    futures[future] = path

                for future in concurrent.futures.as_completed(futures):
                    if self._stop_event.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        if emit_result:
                            self.scan_cancelled.emit()
                        return {}
                    path_hint = futures.get(future, "")
                    try:
                        path, size, mtime, simhash = future.result()
                        if simhash:
                            hash_results[path] = simhash
                            signature_batch.append((path, size, mtime, "DOC_SIMHASH", simhash))
                    except Exception as e:
                        self._record_scan_error(path_hint, e, stage="similar_document", operation="simhash_future")
                    processed += 1
                    emit_progress()

            if signature_batch:
                self.cache_manager.update_signature_batch(signature_batch)

            self._set_stage("grouping")
            self._emit_progress(65, strings.tr("status_grouping"), force=True)

            def grouping_progress(current, total_count):
                percent = 65 + int((current / total_count) * 35)
                self._emit_progress(percent, strings.tr("status_grouping_documents").format(current, total_count))

            similar_groups = self.document_hasher.group_similar_documents(
                hash_results,
                threshold=self.document_similarity_threshold,
                progress_callback=grouping_progress,
                check_cancel=lambda: self._stop_event.is_set(),
            )
            if self._stop_event.is_set():
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
                    final_duplicates[(f"doc_similar_{idx}", int(size))] = list(group)

            if emit_result:
                final_status = self._finalize_scan_status()
                done_msg = strings.tr("status_done_partial") if final_status == "partial" else strings.tr("status_done")
                self._emit_progress(100, f"{done_msg}! ({time.time() - start_time:.2f}s)", force=True)
                self.scan_finished.emit(final_duplicates)
            return final_duplicates
        except Exception as e:
            if emit_result:
                self.latest_scan_metrics = self._snapshot_metrics()
                self.latest_scan_status = "failed"
                self.latest_scan_warnings = []
                self.scan_failed.emit(str(e))
            return {}
