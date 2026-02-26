import os

from src.core.scanner import ScanWorker


class _DummyCache:
    def __init__(self, rows):
        self._rows = list(rows)

    def load_scan_dirs(self, _session_id):
        return {}

    def iter_scan_files(self, _session_id):
        for row in self._rows:
            yield row

    def save_scan_files_batch(self, _session_id, _entries):
        return None


def test_incremental_scan_builds_file_level_baseline_delta_map(tmp_path):
    root = tmp_path / "scan"
    root.mkdir()
    keep_path = root / "keep.txt"
    changed_path = root / "changed.txt"
    new_path = root / "new.txt"

    keep_path.write_text("keep", encoding="utf-8")
    changed_path.write_text("changed_content", encoding="utf-8")
    new_path.write_text("new", encoding="utf-8")

    keep_stat = os.stat(str(keep_path))
    base_rows = [
        (str(keep_path), int(keep_stat.st_size), float(keep_stat.st_mtime)),  # revalidated
        (str(changed_path), 0, 0.0),  # changed
    ]

    worker = ScanWorker(
        [str(root)],
        incremental_rescan=True,
        base_session_id=123,
        session_id=None,
    )
    worker.cache_manager = _DummyCache(base_rows)

    _ = worker._scan_files_incremental(123)
    delta = dict(worker.latest_baseline_delta_map or {})

    assert delta[str(keep_path)] == "revalidated"
    assert delta[str(changed_path)] == "changed"
    assert delta[str(new_path)] == "new"
