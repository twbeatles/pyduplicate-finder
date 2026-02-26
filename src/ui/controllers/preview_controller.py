from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage


class PreviewController(QObject):
    """
    Async preview loader with a small LRU cache.

    Emits payload dicts:
    {
      "request_id": int,
      "path": str,
      "kind": "image"|"text"|"folder"|"info",
      "size": int|None,
      "mtime": float|None,
      "text": str|None,
      "image": QImage|None,
      "message": str|None,
    }
    """

    preview_ready = Signal(object)

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".ico", ".webp"}
    TEXT_EXTS = {
        ".txt",
        ".py",
        ".c",
        ".cpp",
        ".h",
        ".java",
        ".md",
        ".json",
        ".xml",
        ".html",
        ".css",
        ".js",
        ".log",
        ".bat",
        ".sh",
        ".ini",
        ".yaml",
        ".yml",
        ".csv",
    }

    def __init__(self, parent=None, *, max_items: int = 48, max_bytes: int = 64 * 1024 * 1024):
        super().__init__(parent)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preview")
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._cache_bytes = 0
        self._cache_lock = threading.RLock()
        self._max_items = int(max_items)
        self._max_bytes = int(max_bytes)

    def close(self) -> None:
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    def request_preview(self, path: str, request_id: int) -> None:
        p = str(path or "")
        if not p:
            self.preview_ready.emit({"request_id": request_id, "path": p, "kind": "info", "message": "empty_path"})
            return

        cached = self._cache_get(p)
        if cached is not None:
            payload = dict(cached)
            payload["request_id"] = int(request_id)
            self.preview_ready.emit(payload)
            return

        fut = self._executor.submit(self._load_preview_payload, p)

        def _done(f):
            try:
                payload = f.result()
            except Exception as e:
                payload = {"path": p, "kind": "info", "message": f"preview_error:{e}", "size": None, "mtime": None}
            self._cache_put(p, payload)
            out = dict(payload)
            out["request_id"] = int(request_id)
            # Contract: UI binds this signal with Qt.QueuedConnection and updates widgets on the main thread.
            self.preview_ready.emit(out)

        fut.add_done_callback(_done)

    def _cache_get(self, path: str):
        with self._cache_lock:
            item = self._cache.get(path)
            if item is None:
                return None
            self._cache.move_to_end(path)
            return item

    def _cache_put(self, path: str, payload: dict[str, Any]) -> None:
        with self._cache_lock:
            existing = self._cache.pop(path, None)
            if existing is not None:
                self._cache_bytes -= self._estimate_payload_size(existing)
            self._cache[path] = payload
            self._cache_bytes += self._estimate_payload_size(payload)
            self._cache.move_to_end(path)

            while len(self._cache) > self._max_items or self._cache_bytes > self._max_bytes:
                k, v = self._cache.popitem(last=False)
                _ = k
                self._cache_bytes -= self._estimate_payload_size(v)
            if self._cache_bytes < 0:
                self._cache_bytes = 0

    @staticmethod
    def _estimate_payload_size(payload: dict[str, Any]) -> int:
        kind = payload.get("kind")
        if kind == "text":
            text = str(payload.get("text") or "")
            return len(text.encode("utf-8", errors="ignore"))
        if kind == "image":
            img = payload.get("image")
            if isinstance(img, QImage):
                try:
                    return int(img.width() * img.height() * 4)
                except Exception:
                    return 0
        return 512

    @classmethod
    def _load_preview_payload(cls, path: str) -> dict[str, Any]:
        size = None
        mtime = None
        try:
            st = os.stat(path)
            size = int(st.st_size)
            mtime = float(st.st_mtime)
        except Exception:
            return {"path": path, "kind": "info", "message": "missing", "size": None, "mtime": None}

        if os.path.isdir(path):
            return {"path": path, "kind": "folder", "size": size, "mtime": mtime, "text": None, "image": None}

        _, ext = os.path.splitext(path)
        ext = ext.lower()

        if ext in cls.IMAGE_EXTS:
            img = QImage(path)
            if not img.isNull():
                return {
                    "path": path,
                    "kind": "image",
                    "size": size,
                    "mtime": mtime,
                    "text": None,
                    "image": img,
                    "message": None,
                }
            return {"path": path, "kind": "info", "message": "image_unavailable", "size": size, "mtime": mtime}

        if ext in cls.TEXT_EXTS:
            max_chars = 200_000
            read_all_json = bool(ext == ".json" and size is not None and size <= 1_000_000)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read() if read_all_json else f.read(max_chars)
                if ext == ".json" and read_all_json:
                    try:
                        content = json.dumps(json.loads(content), indent=4, ensure_ascii=False)
                    except Exception:
                        pass
                return {
                    "path": path,
                    "kind": "text",
                    "size": size,
                    "mtime": mtime,
                    "text": content,
                    "image": None,
                    "message": None,
                }
            except Exception:
                return {"path": path, "kind": "info", "message": "text_unavailable", "size": size, "mtime": mtime}

        return {"path": path, "kind": "info", "message": "preview_unavailable", "size": size, "mtime": mtime}
