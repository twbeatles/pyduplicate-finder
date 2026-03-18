from __future__ import annotations

from .common import QMutexLocker, time


class ScanStateMixin:
    def stop(self):
        self._stop_event.set()

    def _set_stage(self, stage: str, *, status=None, progress=None, progress_message=None):
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
        if self._stop_event.is_set():
            return

        current_time = time.time()
        with QMutexLocker(self._progress_mutex):
            should_emit_ui = force or (current_time - self._last_progress_update_time >= self._progress_update_interval)
            if should_emit_ui:
                self.progress_updated.emit(value, message)
                self._last_progress_update_time = current_time
            if self.session_id:
                should_persist = force or (
                    current_time - self._last_session_progress_time >= self._session_progress_update_interval
                )
                if should_persist:
                    self.cache_manager.update_scan_session(
                        self.session_id,
                        progress=value,
                        progress_message=message,
                    )
                    self._last_session_progress_time = current_time
