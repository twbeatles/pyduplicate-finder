from __future__ import annotations

from typing import Any

from .common import DEBUG_SCAN, errno, logger
from .contracts import ScanWorkerHost


class ScanMetricsMixin(ScanWorkerHost):
    def _reset_metrics(self):
        with self._metrics_lock:
            self._metrics = {
                "files_scanned": 0,
                "files_hashed": 0,
                "files_skipped_error": 0,
                "files_skipped_locked": 0,
                "errors_total": 0,
            }
            self._error_samples = []
        self.latest_scan_metrics = {}
        self.latest_scan_status = "completed"
        self.latest_scan_warnings = []

    def _is_lock_like_error(self, exc: Exception) -> bool:
        if isinstance(exc, PermissionError):
            return True
        winerror = getattr(exc, "winerror", None)
        if winerror in (32, 33):
            return True
        err_no = getattr(exc, "errno", None)
        return err_no in {errno.EACCES, errno.EPERM, errno.EBUSY, errno.ETXTBSY}

    def _record_scan_error(self, path: str, exc: Exception, *, stage: str = "", operation: str = "") -> None:
        bucket = "files_skipped_locked" if self._is_lock_like_error(exc) else "files_skipped_error"
        message = str(exc or "")
        with self._metrics_lock:
            self._metrics[bucket] = int(self._metrics.get(bucket, 0) or 0) + 1
            self._metrics["errors_total"] = int(self._metrics.get("errors_total", 0) or 0) + 1
            if len(self._error_samples) < self._error_sample_limit:
                self._error_samples.append(
                    {
                        "path": str(path or ""),
                        "stage": str(stage or ""),
                        "operation": str(operation or ""),
                        "error": message,
                    }
                )
        if DEBUG_SCAN:
            logger.warning(
                "[scan] %s/%s path=%s error=%s",
                stage or "unknown",
                operation or "unknown",
                path,
                message,
            )

    def _inc_metric(self, key: str, value: int = 1) -> None:
        if not key:
            return
        with self._metrics_lock:
            self._metrics[key] = int(self._metrics.get(key, 0) or 0) + int(value or 0)

    def _snapshot_metrics(self):
        with self._metrics_lock:
            out: dict[str, Any] = dict(self._metrics or {})
            if self._error_samples:
                out["error_samples"] = list(self._error_samples)
        return out

    def _finalize_scan_status(self) -> str:
        metrics = self._snapshot_metrics()
        warnings = []
        status = "completed"
        if self.strict_mode and int(metrics.get("errors_total", 0) or 0) > int(self.strict_max_errors or 0):
            status = "partial"
            warnings.append("strict_mode_threshold_exceeded")
        self.latest_scan_metrics = metrics
        self.latest_scan_status = status
        self.latest_scan_warnings = warnings
        return status

    def _handle_cancel(self, stage_hint=None) -> bool:
        if not self._stop_event.is_set():
            return False
        if self.session_id:
            try:
                self.cache_manager.update_scan_session(
                    self.session_id,
                    status="paused",
                    stage=stage_hint or self._stage or "collecting",
                )
            except Exception:
                pass
        self.scan_cancelled.emit()
        return True
