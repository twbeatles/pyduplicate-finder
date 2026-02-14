import csv
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt

from src.utils.i18n import strings


class OperationLogDialog(QDialog):
    def __init__(self, cache_manager, op_row: dict, parent=None):
        super().__init__(parent)
        self.cache_manager = cache_manager
        self.op_row = op_row or {}
        self.items = []

        self.setWindowTitle(strings.tr("dlg_operation_details"))
        self.setMinimumSize(860, 560)

        if parent and hasattr(parent, "settings"):
            try:
                from src.ui.theme import ModernTheme

                theme = parent.settings.value("app/theme", "light")
                self.setStyleSheet(ModernTheme.get_stylesheet(theme))
            except Exception:
                pass

        self._init_ui()
        self._load()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("card_title")
        layout.addWidget(self.lbl_title)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                strings.tr("col_path"),
                strings.tr("col_action"),
                strings.tr("col_result"),
                strings.tr("col_detail"),
                strings.tr("col_size"),
                strings.tr("col_quarantine_path"),
            ]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(4, 110)
        layout.addWidget(self.table, 1)

        btns = QHBoxLayout()

        self.btn_export_csv = QPushButton(strings.tr("btn_export_csv2"))
        self.btn_export_csv.clicked.connect(self._export_csv)
        btns.addWidget(self.btn_export_csv)

        self.btn_export_json = QPushButton(strings.tr("btn_export_json"))
        self.btn_export_json.clicked.connect(self._export_json)
        btns.addWidget(self.btn_export_json)

        self.btn_undo_hardlink = QPushButton(strings.tr("btn_undo_hardlink"))
        self.btn_undo_hardlink.setVisible(False)
        btns.addWidget(self.btn_undo_hardlink)

        btns.addStretch()

        self.btn_close = QPushButton(strings.tr("btn_close"))
        self.btn_close.clicked.connect(self.reject)
        btns.addWidget(self.btn_close)

        layout.addLayout(btns)

    def _load(self):
        op_id = int(self.op_row.get("id") or 0)
        created_at = self.op_row.get("created_at") or 0
        dt = datetime.fromtimestamp(float(created_at)).strftime("%Y-%m-%d %H:%M") if created_at else "—"
        title = strings.tr("msg_operation_title").format(
            id=op_id,
            op_type=str(self.op_row.get("op_type") or ""),
            status=str(self.op_row.get("status") or ""),
            time=dt,
        )
        self.lbl_title.setText(title)

        self.items = self.cache_manager.get_operation_items(op_id)

        self.table.setRowCount(len(self.items))
        for r, it in enumerate(self.items):
            path = it.get("path") or ""
            action = it.get("action") or ""
            result = it.get("result") or ""
            detail = it.get("detail") or ""
            size = it.get("size") or 0
            qpath = it.get("quarantine_path") or ""

            i0 = QTableWidgetItem(path)
            i0.setFlags(i0.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 0, i0)

            i1 = QTableWidgetItem(action)
            i1.setFlags(i1.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 1, i1)

            i2 = QTableWidgetItem(result)
            i2.setFlags(i2.flags() & ~Qt.ItemIsEditable)
            if result == "fail":
                i2.setForeground(Qt.red)
            self.table.setItem(r, 2, i2)

            i3 = QTableWidgetItem(detail)
            i3.setFlags(i3.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 3, i3)

            i4 = QTableWidgetItem(str(size))
            i4.setFlags(i4.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 4, i4)

            i5 = QTableWidgetItem(qpath)
            i5.setFlags(i5.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 5, i5)

        # Hardlink undo supported when op is hardlink and we have detail=canonical recorded.
        if str(self.op_row.get("op_type") or "") == "hardlink_consolidate":
            self.btn_undo_hardlink.setVisible(True)

    def _export_csv(self):
        op_id = int(self.op_row.get("id") or 0)
        path, _ = QFileDialog.getSaveFileName(self, strings.tr("btn_export_csv2"), f"operation_{op_id}.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["path", "action", "result", "detail", "size", "mtime", "quarantine_path", "created_at"])
                for it in self.items:
                    w.writerow(
                        [
                            it.get("path") or "",
                            it.get("action") or "",
                            it.get("result") or "",
                            it.get("detail") or "",
                            it.get("size") or 0,
                            it.get("mtime") or "",
                            it.get("quarantine_path") or "",
                            it.get("created_at") or "",
                        ]
                    )
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_export_done").format(path))
        except Exception as e:
            QMessageBox.warning(self, strings.tr("app_title"), str(e))

    def _export_json(self):
        op_id = int(self.op_row.get("id") or 0)
        path, _ = QFileDialog.getSaveFileName(self, strings.tr("btn_export_json"), f"operation_{op_id}.json", "JSON Files (*.json)")
        if not path:
            return
        try:
            data = {"operation": self.op_row, "items": self.items}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_export_done").format(path))
        except Exception as e:
            QMessageBox.warning(self, strings.tr("app_title"), str(e))

