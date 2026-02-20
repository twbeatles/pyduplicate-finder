import os

from src.core.scanner import ScanWorker


def test_scan_files_from_cache_respects_follow_symlinks(monkeypatch, tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("abc", encoding="utf-8")

    real_stat = os.stat
    seen_follow_flags = []

    def stat_spy(path, *, follow_symlinks=True):
        seen_follow_flags.append(bool(follow_symlinks))
        return real_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr("src.core.scanner.os.stat", stat_spy)

    worker = ScanWorker([str(tmp_path)], follow_symlinks=True, protect_system=False)
    try:
        st = real_stat(str(file_path), follow_symlinks=True)
        worker._scan_files_from_cache([(str(file_path), int(st.st_size), float(st.st_mtime))])
    finally:
        worker.cache_manager.close_all()

    assert seen_follow_flags
    assert any(seen_follow_flags)
