from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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
        self._init_ui()
        self._populate()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        layout.addWidget(self.lbl_summary)

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

        rows = sorted(self._delta_map.items(), key=lambda item: (item[1], item[0].lower()))
        self.tbl_deltas.setRowCount(len(rows))
        for row_idx, (path, delta) in enumerate(rows):
            self.tbl_deltas.setItem(row_idx, 0, QTableWidgetItem(str(delta)))
            path_item = QTableWidgetItem(str(path))
            path_item.setToolTip(str(path))
            self.tbl_deltas.setItem(row_idx, 1, path_item)

        self.tbl_deltas.resizeColumnToContents(0)
