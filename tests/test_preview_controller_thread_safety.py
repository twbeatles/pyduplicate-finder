import threading
import time

from src.ui.controllers.preview_controller import PreviewController


def test_preview_controller_cache_thread_safety_under_load(monkeypatch):
    loaded = {"count": 0}
    loaded_lock = threading.Lock()

    def fake_loader(_cls, path: str):
        time.sleep(0.001)
        with loaded_lock:
            loaded["count"] += 1
        return {
            "path": path,
            "kind": "text",
            "size": 128,
            "mtime": 1.0,
            "text": "x" * 128,
            "image": None,
            "message": None,
        }

    monkeypatch.setattr(PreviewController, "_load_preview_payload", classmethod(fake_loader))

    total = 160
    c = PreviewController(max_items=24, max_bytes=4096)
    try:
        for i in range(total):
            c.request_preview(f"/virtual/path/{i}.txt", i)

        deadline = time.time() + 5.0
        while time.time() < deadline:
            with loaded_lock:
                if loaded["count"] >= total:
                    break
            time.sleep(0.01)

        with loaded_lock:
            assert loaded["count"] == total

        with c._cache_lock:
            assert c._cache_bytes >= 0
            assert len(c._cache) <= c._max_items
            assert c._cache_bytes <= c._max_bytes
    finally:
        c.close()
