from src.core.empty_folder_finder import cleanup_empty_parent_folders


def test_cleanup_empty_parent_folders_deletes_only_newly_empty_dirs(tmp_path):
    root = tmp_path / "root"
    leaf = root / "a" / "b"
    leaf.mkdir(parents=True)
    other = root / "keep"
    other.mkdir(parents=True)
    keeper = other / "keep.txt"
    keeper.write_text("x", encoding="utf-8")
    target = leaf / "file.txt"
    target.write_text("data", encoding="utf-8")
    target.unlink()

    deleted, failed = cleanup_empty_parent_folders([str(target)], stop_roots=[str(root)])

    assert failed == []
    assert str(leaf) in deleted
    assert str(root / "a") in deleted
    assert root.exists()
    assert other.exists()
    assert keeper.exists()


def test_cleanup_empty_parent_folders_keeps_stop_root(tmp_path):
    root = tmp_path / "root"
    nested = root / "only"
    nested.mkdir(parents=True)
    target = nested / "file.txt"
    target.write_text("data", encoding="utf-8")
    target.unlink()

    deleted, failed = cleanup_empty_parent_folders([str(target)], stop_roots=[str(root)])

    assert failed == []
    assert str(nested) in deleted
    assert str(root) not in deleted
    assert root.exists()
