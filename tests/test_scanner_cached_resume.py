from __future__ import annotations

import os

from src.core.scanner import ScanWorker


class _DocHasher:
    def is_supported(self, path: str) -> bool:
        return str(path).endswith(".txt")


def test_cached_file_scan_preserves_document_candidates_and_collection_roles(tmp_path):
    root = tmp_path / "primary"
    root.mkdir()
    doc = root / "a.txt"
    doc.write_text("hello", encoding="utf-8")
    st = os.stat(str(doc))

    worker = ScanWorker(
        [str(root)],
        session_id=None,
        use_cached_files=True,
        folder_roles={str(root): "primary"},
        use_similar_document=False,
    )
    worker.use_similar_document = True
    setattr(worker, "document_hasher", _DocHasher())
    worker._file_meta = {}
    worker._image_files = []
    worker._document_files = []
    worker._current_scan_dirs = {}
    worker._base_scan_dirs = {}
    worker._path_collection_roles = {}
    worker._path_exemption_status = {}

    size_map = worker._scan_files_from_cache([(str(doc), int(st.st_size), float(st.st_mtime))])

    assert str(doc) in size_map[int(st.st_size)]
    assert worker._document_files == [str(doc)]
    assert worker._path_collection_roles[str(doc)] == "primary"
