from __future__ import annotations

import os
from collections.abc import Iterable

from PySide6.QtCore import QObject, QTimer, Signal

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # pragma: no cover - optional dependency
    FileSystemEventHandler = object
    Observer = None


class _QtWatchdogHandler(FileSystemEventHandler):  # pragma: no cover - thin wrapper
    def __init__(self, service: "FolderWatchService") -> None:
        super().__init__()
        self._service = service

    def on_any_event(self, event) -> None:
        path = getattr(event, "src_path", "") or getattr(event, "dest_path", "") or ""
        if path:
            self._service.file_event.emit(str(path))


class FolderWatchService(QObject):
    file_event = Signal(str)
    activity_detected = Signal(list)
    state_changed = Signal(str)

    def __init__(self, parent=None, *, debounce_ms: int = 1500, poll_interval_ms: int = 2500) -> None:
        super().__init__(parent)
        self._paths: list[str] = []
        self._pending_paths: set[str] = set()
        self._observer = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(max(500, int(poll_interval_ms)))
        self._poll_timer.timeout.connect(self._poll_snapshot)
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(max(250, int(debounce_ms)))
        self._debounce_timer.timeout.connect(self._flush_pending)
        self._snapshot: dict[str, tuple[int, float]] = {}
        self.file_event.connect(self._queue_path)

    @property
    def is_running(self) -> bool:
        return bool(self._paths) and (
            (self._observer is not None and getattr(self._observer, "is_alive", lambda: False)())
            or self._poll_timer.isActive()
        )

    def start(self, paths: Iterable[str]) -> None:
        self.stop()
        normalized = []
        seen = set()
        for raw in list(paths or []):
            if not raw:
                continue
            path = os.path.abspath(str(raw))
            key = os.path.normcase(os.path.normpath(path))
            if key in seen or not os.path.isdir(path):
                continue
            seen.add(key)
            normalized.append(path)
        self._paths = normalized
        self._snapshot = self._build_snapshot()
        if not self._paths:
            self.state_changed.emit("stopped")
            return

        if Observer is not None:
            try:
                observer = Observer()
                handler = _QtWatchdogHandler(self)
                for path in self._paths:
                    observer.schedule(handler, path, recursive=True)
                observer.start()
                self._observer = observer
                self.state_changed.emit("watchdog")
                return
            except Exception:
                self._observer = None

        self._poll_timer.start()
        self.state_changed.emit("polling")

    def stop(self) -> None:
        self._debounce_timer.stop()
        self._poll_timer.stop()
        self._pending_paths.clear()
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=1.0)
            except Exception:
                pass
            self._observer = None
        self._paths = []
        self._snapshot = {}
        self.state_changed.emit("stopped")

    def _queue_path(self, path: str) -> None:
        if not path:
            return
        self._pending_paths.add(os.path.abspath(str(path)))
        self._debounce_timer.start()

    def _flush_pending(self) -> None:
        if not self._pending_paths:
            return
        pending = sorted(self._pending_paths)
        self._pending_paths.clear()
        self.activity_detected.emit(pending)

    def _build_snapshot(self) -> dict[str, tuple[int, float]]:
        snapshot: dict[str, tuple[int, float]] = {}
        for root in self._paths:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    try:
                        stat = os.stat(full)
                    except Exception:
                        continue
                    snapshot[full] = (int(stat.st_size), float(stat.st_mtime))
        return snapshot

    def _poll_snapshot(self) -> None:
        current = self._build_snapshot()
        changed: set[str] = set()
        for path, meta in current.items():
            if self._snapshot.get(path) != meta:
                changed.add(path)
        for path in self._snapshot:
            if path not in current:
                changed.add(path)
        self._snapshot = current
        if changed:
            for path in changed:
                self._pending_paths.add(path)
            self._debounce_timer.start()
