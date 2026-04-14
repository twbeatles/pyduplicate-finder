import time

import pytest
from PySide6.QtWidgets import QApplication

import os

from src.ui.controllers.watch_controller import FolderWatchService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_watch_service_debounces_multiple_events(qapp):
    service = FolderWatchService(debounce_ms=50, poll_interval_ms=1000)
    seen = []
    service.activity_detected.connect(lambda paths: seen.append(list(paths)))
    try:
        service.file_event.emit("C:/tmp/a.txt")
        service.file_event.emit("C:/tmp/b.txt")
        deadline = time.time() + 1.0
        while time.time() < deadline and not seen:
            qapp.processEvents()
            time.sleep(0.02)
    finally:
        service.stop()

    assert len(seen) == 1
    assert sorted(seen[0]) == sorted(
        [
            os.path.abspath("C:/tmp/a.txt"),
            os.path.abspath("C:/tmp/b.txt"),
        ]
    )
