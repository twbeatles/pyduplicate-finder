from src.core.scanner import ScanWorker


def _scan_with_extensions(root: str, extensions):
    worker = ScanWorker([root], protect_system=False, extensions=extensions, max_workers=1)
    try:
        worker._scan_files()
        return set(worker._file_meta.keys()), set(worker.extensions or set())
    finally:
        worker.cache_manager.close_all()


def test_extension_inputs_txt_and_dot_txt_match(tmp_path):
    txt_a = tmp_path / "a.txt"
    txt_b = tmp_path / "b.TXT"
    log_c = tmp_path / "c.log"
    txt_a.write_text("a", encoding="utf-8")
    txt_b.write_text("b", encoding="utf-8")
    log_c.write_text("c", encoding="utf-8")

    files_plain, ext_plain = _scan_with_extensions(str(tmp_path), ["txt"])
    files_dot, ext_dot = _scan_with_extensions(str(tmp_path), [".txt"])

    assert ext_plain == {"txt"}
    assert ext_dot == {"txt"}
    assert files_plain == files_dot
    assert str(txt_a) in files_plain
    assert str(txt_b) in files_plain
    assert str(log_c) not in files_plain
