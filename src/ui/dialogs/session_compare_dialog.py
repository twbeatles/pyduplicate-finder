from __future__ import annotations

import csv
from collections import Counter
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.utils.i18n import strings


class SessionCompareDialog(QDialog):
    def __init__(
        self,
        *,
        baseline_session_id: int = 0,
        current_session_id: int = 0,
        delta_map: dict[str, str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(strings.tr("dlg_session_compare_title"))
        self.resize(840, 520)
        self._delta_map = {
            str(path): str(delta or "")
            for path, delta in dict(delta_map or {}).items()
            if str(delta or "") in {"new", "changed", "revalidated"}
        }
        self._baseline_session_id = int(baseline_session_id or 0)
        self._current_session_id = int(current_session_id or 0)
        self._visible_rows: list[tuple[str, str]] = []
        self._init_ui()
        self._populate()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        layout.addWidget(self.lbl_summary)

        filter_row = QHBoxLayout()
        self.cmb_delta_filter = QComboBox()
        self.cmb_delta_filter.addItem(strings.tr("opt_delta_all"), "")
        self.cmb_delta_filter.addItem(strings.tr("opt_delta_new"), "new")
        self.cmb_delta_filter.addItem(strings.tr("opt_delta_changed"), "changed")
        self.cmb_delta_filter.addItem(strings.tr("opt_delta_revalidated"), "revalidated")
        self.cmb_delta_filter.currentIndexChanged.connect(lambda _i: self._populate())
        filter_row.addWidget(self.cmb_delta_filter)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self.tbl_deltas = QTableWidget()
        self.tbl_deltas.setColumnCount(2)
        self.tbl_deltas.setHorizontalHeaderLabels(
            [
                strings.tr("col_delta"),
                strings.tr("col_path"),
            ]
        )
        header = self.tbl_deltas.horizontalHeader()
        header.setStretchLastSection(True)
        self.tbl_deltas.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_deltas.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_deltas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.tbl_deltas, 1)

        button_row = QHBoxLayout()
        self.btn_select_results = QPushButton(strings.tr("btn_select_in_results"))
        self.btn_select_results.clicked.connect(self._select_in_results)
        button_row.addWidget(self.btn_select_results)
        self.btn_mark_keep = QPushButton(strings.tr("ctx_review_keep"))
        self.btn_mark_keep.clicked.connect(lambda: self._mark_review("reviewed_keep"))
        button_row.addWidget(self.btn_mark_keep)
        self.btn_mark_delete = QPushButton(strings.tr("ctx_review_delete_later"))
        self.btn_mark_delete.clicked.connect(lambda: self._mark_review("reviewed_delete_later"))
        button_row.addWidget(self.btn_mark_delete)
        self.btn_export = QPushButton(strings.tr("btn_export_csv2"))
        self.btn_export.clicked.connect(self._export_csv)
        button_row.addWidget(self.btn_export)
        button_row.addStretch()
        self.btn_close = QPushButton(strings.tr("btn_close"))
        self.btn_close.clicked.connect(self.accept)
        button_row.addWidget(self.btn_close)
        layout.addLayout(button_row)

    def _populate(self) -> None:
        counts = Counter(self._delta_map.values())
        self.lbl_summary.setText(
            strings.tr("msg_session_compare_summary").format(
                current=self._current_session_id or "-",
                baseline=self._baseline_session_id or "-",
                new=int(counts.get("new", 0)),
                changed=int(counts.get("changed", 0)),
                revalidated=int(counts.get("revalidated", 0)),
            )
        )

        selected_delta = str(self.cmb_delta_filter.currentData() or "") if hasattr(self, "cmb_delta_filter") else ""
        rows = sorted(
            (
                (path, delta)
                for path, delta in self._delta_map.items()
                if not selected_delta or delta == selected_delta
            ),
            key=lambda item: (item[1], item[0].lower()),
        )
        self._visible_rows = list(rows)
        self.tbl_deltas.setRowCount(len(rows))
        for row_idx, (path, delta) in enumerate(rows):
            self.tbl_deltas.setItem(row_idx, 0, QTableWidgetItem(str(delta)))
            path_item = QTableWidgetItem(str(path))
            path_item.setToolTip(str(path))
            self.tbl_deltas.setItem(row_idx, 1, path_item)

        self.tbl_deltas.resizeColumnToContents(0)

    def _action_paths(self) -> list[str]:
        selected_rows = sorted({idx.row() for idx in self.tbl_deltas.selectedIndexes()})
        if selected_rows:
            paths = []
            for row in selected_rows:
                item = self.tbl_deltas.item(row, 1)
                if item is not None:
                    paths.append(str(item.text()))
            return paths
        return [path for path, _delta in self._visible_rows]

    def _select_in_results(self) -> None:
        parent = cast(Any, self.parent())
        paths = self._action_paths()
        if paths and parent is not None and hasattr(parent, "select_paths_in_results"):
            parent.select_paths_in_results(paths)

    def _mark_review(self, state: str) -> None:
        parent = cast(Any, self.parent())
        paths = self._action_paths()
        if paths and parent is not None and hasattr(parent, "_set_review_state"):
            parent._set_review_state(paths, state)

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, strings.tr("btn_export_csv2"), "session_compare.csv", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["delta", "path"])
            for item_path, delta in self._visible_rows:
                writer.writerow([delta, item_path])
