import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.ui.components.results_tree import ResultsTreeWidget
import src.ui.components.results_tree as tree_module
from src.utils.i18n import strings


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _drain_populate(widget: ResultsTreeWidget):
    guard = 0
    while widget._populate_timer.isActive() and guard < 1000:
        widget._process_batch()
        guard += 1


def test_populate_uses_injected_meta_without_fs_calls(qapp, monkeypatch):
    paths = [r"C:\tmp\alpha.txt", r"C:\tmp\beta.txt"]
    results = {("hash_a", 10): paths}
    file_meta = {
        paths[0]: (10, 1700000000.0),
        paths[1]: (10, 1700000001.0),
    }
    existence_map = {paths[0]: True, paths[1]: False}

    def fail_exists(_path):
        raise AssertionError("os.path.exists should not be called during populate")

    monkeypatch.setattr(tree_module.os.path, "exists", fail_exists)

    widget = ResultsTreeWidget()
    widget.populate(results, selected_paths=[paths[0]], file_meta=file_meta, existence_map=existence_map)
    _drain_populate(widget)

    root = widget.invisibleRootItem()
    assert root.childCount() == 1
    group = root.child(0)
    assert group.childCount() == 2
    assert paths[0] in set(widget.get_checked_files())
    assert f"[{strings.tr('badge_missing')}]" in group.child(1).text(0)


def test_checked_cache_and_filter_counts(qapp):
    paths = ["/x/alpha.log", "/x/beta.log"]
    results = {("hash_b", 20): paths}
    file_meta = {paths[0]: (20, 1700000010.0), paths[1]: (20, 1700000020.0)}

    widget = ResultsTreeWidget()
    widget.populate(results, selected_paths=[], file_meta=file_meta, existence_map={paths[0]: True, paths[1]: True})
    _drain_populate(widget)

    group = widget.invisibleRootItem().child(0)
    first = group.child(0)
    first.setCheckState(0, Qt.CheckState.Checked)
    assert set(widget.get_checked_files()) == {paths[0]}

    visible, total = widget.apply_filter("alpha")
    assert total == 2
    assert visible == 1

    widget.set_group_checked(group, False)
    assert widget.get_checked_files() == []


def test_files_checked_delta_and_filter_short_circuit(qapp):
    paths = ["/x/a.log", "/x/b.log", "/x/c.log"]
    results = {("hash_c", 30): paths}
    file_meta = {p: (30, 1700000100.0 + i) for i, p in enumerate(paths)}

    widget = ResultsTreeWidget()
    widget.populate(results, selected_paths=[], file_meta=file_meta, existence_map={p: True for p in paths})
    _drain_populate(widget)

    deltas = []
    widget.files_checked_delta.connect(lambda added, removed, count: deltas.append((list(added), list(removed), int(count))))

    group = widget.invisibleRootItem().child(0)
    first = group.child(0)
    second = group.child(1)
    first.setCheckState(0, Qt.CheckState.Checked)
    second.setCheckState(0, Qt.CheckState.Checked)
    second.setCheckState(0, Qt.CheckState.Unchecked)

    assert deltas[0] == ([paths[0]], [], 1)
    assert deltas[1] == ([paths[1]], [], 2)
    assert deltas[2] == ([], [paths[1]], 1)

    v1 = widget.apply_filter("a.log")
    v2 = widget.apply_filter("a.log")
    assert v1 == v2
