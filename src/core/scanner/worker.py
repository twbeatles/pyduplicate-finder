from __future__ import annotations

from .common import (
    Any,
    CacheManager,
    DOCUMENT_HASH_AVAILABLE,
    IMAGE_HASH_AVAILABLE,
    QMutex,
    QThread,
    Signal,
    _DocumentHasher,
    _ImageHasher,
    defaultdict,
    os,
    strings,
    threading,
    time,
)
from .discovery import ScanDiscoveryMixin
from .filters import ScanFilterMixin
from .folder_duplicates import ScanFolderDuplicatesMixin
from .hashing import ScanHashingMixin
from .incremental import ScanIncrementalMixin
from .metrics import ScanMetricsMixin
from .similar_documents import ScanSimilarDocumentsMixin
from .similar_images import ScanSimilarImagesMixin
from .state import ScanStateMixin


class ScanWorker(
    ScanSimilarDocumentsMixin,
    ScanSimilarImagesMixin,
    ScanFolderDuplicatesMixin,
    ScanHashingMixin,
    ScanIncrementalMixin,
    ScanDiscoveryMixin,
    ScanStateMixin,
    ScanFilterMixin,
    ScanMetricsMixin,
    QThread,
):
    progress_updated = Signal(int, str)
    stage_updated = Signal(str)
    scan_finished = Signal(object)
    scan_cancelled = Signal()
    scan_failed = Signal(str)

    def __init__(
        self,
        folders,
        check_name=False,
        min_size_kb=0,
        extensions=None,
        protect_system=True,
        byte_compare=False,
        max_workers=None,
        exclude_patterns=None,
        include_patterns=None,
        skip_hidden=False,
        follow_symlinks=False,
        name_only=False,
        detect_duplicate_folders=False,
        use_similar_image=False,
        similarity_threshold=0.9,
        use_mixed_mode=False,
        incremental_rescan=False,
        base_session_id=None,
        session_id=None,
        use_cached_files=False,
        strict_mode=False,
        strict_max_errors=0,
        selection_policy="smart",
        compare_mode="none",
        folder_roles=None,
        use_similar_document=False,
        document_similarity_threshold=0.9,
        watch_mode=False,
        apply_exemptions=True,
        post_cleanup_empty_dirs=False,
    ):
        super().__init__()
        self.folders = folders
        self.check_name = check_name
        self.name_only = name_only
        self.min_size = min_size_kb * 1024
        self.extensions = self._normalize_extensions(extensions)
        self.protect_system = protect_system
        self.byte_compare = byte_compare
        self.exclude_patterns = exclude_patterns or []
        self.include_patterns = include_patterns or []
        self._exclude_matchers = self._prepare_patterns(self.exclude_patterns)
        self._include_matchers = self._prepare_patterns(self.include_patterns)
        self.skip_hidden = bool(skip_hidden)
        self.follow_symlinks = bool(follow_symlinks)
        self.detect_duplicate_folders = bool(detect_duplicate_folders)
        self.use_similar_image = use_similar_image and IMAGE_HASH_AVAILABLE
        self.use_mixed_mode = bool(use_mixed_mode)
        self.similarity_threshold = similarity_threshold
        self.incremental_rescan = bool(incremental_rescan)
        self.base_session_id = int(base_session_id) if base_session_id else None
        self.strict_mode = bool(strict_mode)
        self.strict_max_errors = max(0, int(strict_max_errors or 0))
        self.selection_policy = str(selection_policy or "smart")
        self.compare_mode = str(compare_mode or "none")
        self.folder_roles = {str(k): str(v) for k, v in dict(folder_roles or {}).items() if k}
        self.use_similar_document = bool(use_similar_document) and DOCUMENT_HASH_AVAILABLE
        self.document_similarity_threshold = float(document_similarity_threshold or 0.9)
        self.watch_mode = bool(watch_mode)
        self.apply_exemptions = bool(apply_exemptions)
        self.post_cleanup_empty_dirs = bool(post_cleanup_empty_dirs)
        self._stop_event = threading.Event()
        self._init_protected_paths()
        self.cache_manager = CacheManager()
        self.max_workers = max_workers or (os.cpu_count() or 4)
        self.session_id = session_id
        self.use_cached_files = use_cached_files

        self.seen_inodes = set()
        self._seen_dir_keys = set()

        self._last_progress_update_time = 0
        self._progress_update_interval = 0.1
        self._last_session_progress_time = 0
        self._session_progress_update_interval = 0.8
        self._progress_mutex = QMutex()
        self._stage = None

        self._file_meta = {}
        self._image_files = []
        self._document_files = []
        self._current_scan_dirs = {}
        self._base_scan_dirs = {}
        self.latest_file_meta = {}
        self.latest_baseline_delta_map = {}
        self.latest_scan_metrics: dict[str, Any] = {}
        self.latest_scan_status = "completed"
        self.latest_scan_warnings = []
        self.latest_collection_role_map: dict[str, str] = {}
        self.latest_exemption_status_map: dict[str, str] = {}
        self.latest_selection_reason_map: dict[str, str] = {}
        self.latest_result_review_state_map: dict[str, str] = {}
        self.incremental_stats = {}
        self._metrics_lock = threading.Lock()
        self._metrics: dict[str, int] = {
            "files_scanned": 0,
            "files_hashed": 0,
            "files_skipped_error": 0,
            "files_skipped_locked": 0,
            "errors_total": 0,
        }
        self._error_sample_limit = 25
        self._error_samples: list[dict[str, str]] = []

        if self.use_similar_image and _ImageHasher is not None:
            self.image_hasher = _ImageHasher()
        if self.use_similar_document and _DocumentHasher is not None:
            self.document_hasher = _DocumentHasher()

        self._exemption_rules = []
        try:
            from src.core.selection_rules import parse_exemption_rules

            self._exemption_rules = parse_exemption_rules(self.cache_manager.list_scan_exemptions())
        except Exception:
            self._exemption_rules = []
        self._full_hash_values: dict[str, str] = {}
        self._path_collection_roles: dict[str, str] = {}
        self._path_exemption_status: dict[str, str] = {}

    def _normalize_extensions(self, extensions):
        normalized = set()
        for ext in extensions or []:
            token = str(ext or "").strip().lower()
            if not token:
                continue
            token = token.lstrip(".")
            if token:
                normalized.add(token)
        return normalized or None

    def run(self):
        try:
            start_time = time.time()
            self._reset_metrics()
            self.seen_inodes.clear()
            self._set_stage(
                "collecting",
                status="running",
                progress=0,
                progress_message=strings.tr("status_collecting_files"),
            )

            if self.use_similar_image and not self.use_mixed_mode:
                self._run_similar_image_scan()
                return

            if self.incremental_rescan and self.base_session_id:
                self._set_stage("incremental_index")

            size_map = self._scan_files()
            if self._handle_cancel("collecting"):
                return
            self._set_stage("collected")

            final_duplicates = {}

            if self.name_only:
                name_groups = defaultdict(list)
                for paths in size_map.values():
                    if self._handle_cancel("collected"):
                        return
                    for path in paths:
                        name = os.path.basename(path)
                        if not name:
                            continue
                        key = name.lower() if os.name == "nt" else name
                        name_groups[key].append(path)

                for name_key, paths in name_groups.items():
                    if len(paths) > 1:
                        final_duplicates[("NAME_ONLY", name_key)] = paths
            else:
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

                    self._set_stage("hashing")
                    temp_hash_map = self._calculate_hashes_parallel(
                        candidates,
                        is_quick_scan=True,
                        seed_session_id=self.base_session_id if self.incremental_rescan else None,
                    )
                    if self._handle_cancel("hashing"):
                        return
                    self._set_stage("hashing")

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
                        if self._handle_cancel("hashing"):
                            return

                        for key, paths in full_hash_results.items():
                            if len(paths) < 2:
                                continue
                            self._process_final_group(key[1], key[0], paths, final_duplicates)

            if self.detect_duplicate_folders and self._file_meta:
                self._set_stage("folder_dup")
                folder_groups = self._detect_duplicate_folders()
                if self._handle_cancel("folder_dup"):
                    return
                if folder_groups:
                    final_duplicates.update(folder_groups)

            if self.use_similar_image and self.use_mixed_mode:
                similar_groups = self._run_similar_image_scan(image_files=list(self._image_files), emit_result=False)
                if self._handle_cancel("similar_image"):
                    return
                if similar_groups:
                    final_duplicates.update(similar_groups)

            if self.use_similar_document:
                similar_doc_groups = self._run_similar_document_scan(document_files=list(self._document_files), emit_result=False)
                if self._handle_cancel("similar_document"):
                    return
                if similar_doc_groups:
                    final_duplicates.update(similar_doc_groups)

            final_duplicates = self._apply_post_scan_filters(final_duplicates)

            final_status = self._finalize_scan_status()
            done_msg = strings.tr("status_done_partial") if final_status == "partial" else strings.tr("status_done")
            self._emit_progress(100, f"{done_msg}! ({time.time() - start_time:.2f}s)", force=True)
            self._trim_file_meta_for_results(final_duplicates)
            self.latest_file_meta = dict(self._file_meta or {})
            self.latest_collection_role_map = dict(self._path_collection_roles or {})
            self.latest_exemption_status_map = dict(self._path_exemption_status or {})
            try:
                review_rows = self.cache_manager.list_review_marks(int(self.session_id or 0), target_type="file")
                self.latest_result_review_state_map = {
                    str(row.get("target_key") or ""): str(row.get("state") or "")
                    for row in review_rows
                    if row.get("target_key")
                }
            except Exception:
                self.latest_result_review_state_map = {}
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
            self._emit_progress(0, strings.tr("err_scan_failed").format(e), force=True)
            self.latest_scan_metrics = self._snapshot_metrics()
            self.latest_scan_status = "failed"
            self.latest_scan_warnings = []
            self.scan_failed.emit(str(e))
        finally:
            self.cache_manager.close_all()
