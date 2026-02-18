from __future__ import annotations

from typing import Callable, Optional

from src.core.scan_engine import ScanConfig, build_scan_worker_kwargs
from src.core.scanner import ScanWorker


class ScanController:
    def build_worker(
        self,
        *,
        config: ScanConfig,
        session_id: Optional[int],
        use_cached_files: bool,
    ) -> ScanWorker:
        kwargs = build_scan_worker_kwargs(config, session_id=session_id, use_cached_files=use_cached_files)
        return ScanWorker(config.folders, **kwargs)

    def wire_signals(
        self,
        worker: ScanWorker,
        *,
        on_progress: Callable,
        on_stage: Callable,
        on_finished: Callable,
        on_cancelled: Callable,
        on_failed: Callable,
    ) -> None:
        worker.progress_updated.connect(on_progress)
        worker.stage_updated.connect(on_stage)
        worker.scan_finished.connect(on_finished)
        worker.scan_cancelled.connect(on_cancelled)
        worker.scan_failed.connect(on_failed)
