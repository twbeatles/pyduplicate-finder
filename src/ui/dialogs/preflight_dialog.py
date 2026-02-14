from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt

from src.utils.i18n import strings


class PreflightDialog(QDialog):
    def __init__(self, report, parent=None):
        super().__init__(parent)
        self.report = report
        self._accepted = False

        self.setWindowTitle(strings.tr("dlg_preflight_title"))
        self.setMinimumSize(720, 520)

        # Inherit parent theme if possible.
        if parent and hasattr(parent, "settings"):
            try:
                from src.ui.theme import ModernTheme

                theme = parent.settings.value("app/theme", "light")
                self.setStyleSheet(ModernTheme.get_stylesheet(theme))
            except Exception:
                pass

        self._init_ui()
        self._populate()

    @property
    def can_proceed(self) -> bool:
        try:
            return not bool(getattr(self.report, "has_blockers", False))
        except Exception:
            return True

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setObjectName("empty_state")
        layout.addWidget(self.lbl_summary)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            [
                strings.tr("col_severity"),
                strings.tr("col_path"),
                strings.tr("col_code"),
                strings.tr("col_message"),
            ]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(2, 140)
        layout.addWidget(self.table, 1)

        btns = QHBoxLayout()
        btns.addStretch()

        self.btn_cancel = QPushButton(strings.tr("btn_cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton(strings.tr("btn_proceed"))
        self.btn_ok.setObjectName("btn_primary")
        self.btn_ok.clicked.connect(self._accept)
        btns.addWidget(self.btn_ok)

        layout.addLayout(btns)

    def _severity_label(self, sev: str) -> str:
        s = str(sev or "").lower()
        if s == "block":
            return strings.tr("sev_block")
        if s == "warn":
            return strings.tr("sev_warn")
        return strings.tr("sev_info")

    def _populate(self):
        rep = self.report
        counts = {}
        try:
            counts = rep.summary_counts()
        except Exception:
            counts = {}

        eligible = 0
        try:
            eligible = int(getattr(rep, "meta", {}).get("eligible_count", 0)) or len(getattr(rep, "eligible_paths", []) or [])
        except Exception:
            eligible = 0

        self.lbl_summary.setText(
            strings.tr("msg_preflight_summary").format(
                eligible=eligible,
                blocks=counts.get("block", 0),
                warns=counts.get("warn", 0),
                infos=counts.get("info", 0),
            )
        )

        issues = list(getattr(rep, "issues", []) or [])
        self.table.setRowCount(len(issues))

        for r, it in enumerate(issues):
            sev = self._severity_label(getattr(it, "severity", "info"))
            path = getattr(it, "path", "") or ""
            code = getattr(it, "code", "") or ""
            msg = getattr(it, "message", "") or ""

            i0 = QTableWidgetItem(sev)
            i0.setFlags(i0.flags() & ~Qt.ItemIsEditable)
            if str(getattr(it, "severity", "")).lower() == "block":
                i0.setForeground(Qt.red)
            elif str(getattr(it, "severity", "")).lower() == "warn":
                i0.setForeground(Qt.darkYellow)
            self.table.setItem(r, 0, i0)

            i1 = QTableWidgetItem(path)
            i1.setFlags(i1.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 1, i1)

            i2 = QTableWidgetItem(code)
            i2.setFlags(i2.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 2, i2)

            i3 = QTableWidgetItem(msg)
            i3.setFlags(i3.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 3, i3)

        self.btn_ok.setEnabled(self.can_proceed)

    def _accept(self):
        self._accepted = True
        self.accept()
