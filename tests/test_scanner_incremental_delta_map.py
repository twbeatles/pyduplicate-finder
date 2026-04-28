import os

from src.core.scanner import ScanWorker
from src.core.scan_types import (
    EXEMPTION_ACTION_IGNORE,
    EXEMPTION_KIND_EXACT_PATH,
    ExemptionRule,
)


class _DummyCache:
    def __init__(self, rows, *, dirs=None):
        self._rows = list(rows)
        self._dirs = dict(dirs or {})

    def load_scan_dirs(self, _session_id):
        return dict(self._dirs)

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
    setattr(worker, "cache_manager", _DummyCache(base_rows))

    _ = worker._scan_files_incremental(123)
    delta = dict(worker.latest_baseline_delta_map or {})

    assert delta[str(keep_path)] == "revalidated"
    assert delta[str(changed_path)] == "changed"
    assert delta[str(new_path)] == "new"


def test_incremental_scan_finds_new_file_even_when_dir_mtime_matches_baseline(tmp_path):
    root = tmp_path / "scan"
    sub = root / "sub"
    sub.mkdir(parents=True)
    keep_path = sub / "keep.txt"
    keep_path.write_text("keep", encoding="utf-8")

    # Build baseline snapshot first.
    keep_stat = os.stat(str(keep_path))
    sub_stat = os.stat(str(sub))
    base_rows = [(str(keep_path), int(keep_stat.st_size), float(keep_stat.st_mtime))]

    # Create a new file, then force directory mtime back to baseline
    # to simulate coarse filesystem timestamp behavior.
    new_path = sub / "new.txt"
    new_path.write_text("new", encoding="utf-8")
    os.utime(str(sub), (float(sub_stat.st_atime), float(sub_stat.st_mtime)))

    worker = ScanWorker(
        [str(root)],
        incremental_rescan=True,
        base_session_id=123,
        session_id=None,
    )
    norm_sub = worker._normalize_path(str(sub))
    setattr(
        worker,
        "cache_manager",
        _DummyCache(base_rows, dirs={norm_sub: float(sub_stat.st_mtime)}),
    )

    _ = worker._scan_files_incremental(123)
    delta = dict(worker.latest_baseline_delta_map or {})
    assert delta[str(new_path)] == "new"


def test_incremental_baseline_known_paths_respect_ignore_rules(tmp_path):
    root = tmp_path / "scan"
    root.mkdir()
    ignored = root / "ignored.txt"
    kept = root / "kept.txt"
    ignored.write_text("ignored", encoding="utf-8")
    kept.write_text("kept", encoding="utf-8")

    ignored_stat = os.stat(str(ignored))
    kept_stat = os.stat(str(kept))
    base_rows = [
        (str(ignored), int(ignored_stat.st_size), float(ignored_stat.st_mtime)),
        (str(kept), int(kept_stat.st_size), float(kept_stat.st_mtime)),
    ]

    worker = ScanWorker(
        [str(root)],
        incremental_rescan=True,
        base_session_id=123,
        session_id=None,
        apply_exemptions=True,
    )
    worker._exemption_rules = [
        ExemptionRule(kind=EXEMPTION_KIND_EXACT_PATH, value=str(ignored), action=EXEMPTION_ACTION_IGNORE)
    ]
    setattr(worker, "cache_manager", _DummyCache(base_rows))

    size_map = worker._scan_files_incremental(123)
    all_paths = {path for paths in size_map.values() for path in paths}
    delta = dict(worker.latest_baseline_delta_map or {})

    assert str(ignored) not in all_paths
    assert str(ignored) not in delta
    assert delta[str(kept)] == "revalidated"
