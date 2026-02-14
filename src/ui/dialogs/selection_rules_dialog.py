"""
Selection rules dialog:
Ordered rules that mark paths as KEEP or DELETE using fnmatch-style globs.
"""

import json
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLineEdit,
    QComboBox,
    QMessageBox,
)
from PySide6.QtCore import Qt

from src.utils.i18n import strings


class SelectionRulesDialog(QDialog):
    COMMON_PRESETS = [
        # (pattern, action)
        ("*/temp/*", "delete"),
        ("*\\temp\\*", "delete"),
        ("*/cache/*", "delete"),
        ("*\\cache\\*", "delete"),
        ("*/downloads/*", "delete"),
        ("*\\downloads\\*", "delete"),
        ("*/appdata/local/temp/*", "delete"),
        ("*\\appdata\\local\\temp\\*", "delete"),
        ("*.tmp", "delete"),
        ("* - copy*", "delete"),
        ("* - 복사본*", "delete"),
    ]

    def __init__(self, rules: list, parent=None):
        super().__init__(parent)
        self.rules = list(rules or [])

        self.setWindowTitle(strings.tr("dlg_rules_title"))
        self.setMinimumSize(680, 520)

        if parent and hasattr(parent, "settings"):
            try:
                from src.ui.theme import ModernTheme

                theme = parent.settings.value("app/theme", "light")
                self.setStyleSheet(ModernTheme.get_stylesheet(theme))
            except Exception:
                pass

        self._init_ui()
        self._refresh()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        desc = QLabel(strings.tr("msg_rules_desc"))
        desc.setWordWrap(True)
        desc.setObjectName("empty_state")
        layout.addWidget(desc)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([strings.tr("col_pattern"), strings.tr("col_action")])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 140)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        layout.addWidget(self.table, 1)

        # Add row controls
        add_row = QHBoxLayout()
        self.txt_pattern = QLineEdit()
        self.txt_pattern.setPlaceholderText(strings.tr("ph_rule_pattern"))
        add_row.addWidget(self.txt_pattern, 1)

        self.combo_action = QComboBox()
        self.combo_action.addItem(strings.tr("rule_keep"), "keep")
        self.combo_action.addItem(strings.tr("rule_delete"), "delete")
        add_row.addWidget(self.combo_action)

        self.btn_add = QPushButton(strings.tr("btn_add"))
        self.btn_add.clicked.connect(self._add_rule)
        add_row.addWidget(self.btn_add)

        layout.addLayout(add_row)

        # Presets + reorder + remove
        row2 = QHBoxLayout()
        self.combo_presets = QComboBox()
        self.combo_presets.addItem(strings.tr("opt_select"), None)
        for pat, act in self.COMMON_PRESETS:
            self.combo_presets.addItem(f"{pat} ({act})", (pat, act))
        row2.addWidget(self.combo_presets, 1)

        self.btn_add_preset = QPushButton(strings.tr("btn_add_preset"))
        self.btn_add_preset.clicked.connect(self._add_preset)
        row2.addWidget(self.btn_add_preset)

        self.btn_up = QPushButton(strings.tr("btn_up"))
        self.btn_up.clicked.connect(lambda: self._move(-1))
        row2.addWidget(self.btn_up)

        self.btn_down = QPushButton(strings.tr("btn_down"))
        self.btn_down.clicked.connect(lambda: self._move(1))
        row2.addWidget(self.btn_down)

        self.btn_remove = QPushButton(strings.tr("btn_remove"))
        self.btn_remove.clicked.connect(self._remove_selected)
        row2.addWidget(self.btn_remove)

        layout.addLayout(row2)

        # Test match
        test_row = QHBoxLayout()
        self.txt_test = QLineEdit()
        self.txt_test.setPlaceholderText(strings.tr("ph_rule_test_path"))
        test_row.addWidget(self.txt_test, 1)
        self.btn_test = QPushButton(strings.tr("btn_test_rule"))
        self.btn_test.clicked.connect(self._test_rules)
        test_row.addWidget(self.btn_test)
        layout.addLayout(test_row)

        # Footer
        btns = QHBoxLayout()
        btns.addStretch()
        self.btn_cancel = QPushButton(strings.tr("btn_cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        self.btn_ok = QPushButton(strings.tr("btn_ok"))
        self.btn_ok.clicked.connect(self.accept)
        btns.addWidget(self.btn_ok)
        layout.addLayout(btns)

    def _refresh(self):
        self.table.setRowCount(len(self.rules))
        for r, rule in enumerate(self.rules):
            pat = str(rule.get("pattern") or "")
            act = str(rule.get("action") or "keep")
            i0 = QTableWidgetItem(pat)
            i0.setFlags(i0.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 0, i0)
            i1 = QTableWidgetItem(strings.tr("rule_keep") if act == "keep" else strings.tr("rule_delete"))
            i1.setData(Qt.UserRole, act)
            i1.setFlags(i1.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 1, i1)

    def _add_rule(self):
        pat = self.txt_pattern.text().strip()
        act = self.combo_action.currentData()
        if not pat:
            return
        self.rules.append({"pattern": pat, "action": act})
        self.txt_pattern.clear()
        self._refresh()

    def _add_preset(self):
        data = self.combo_presets.currentData()
        if not data:
            return
        pat, act = data
        self.rules.append({"pattern": pat, "action": act})
        self._refresh()

    def _current_row(self) -> int:
        return int(self.table.currentRow())

    def _move(self, delta: int):
        row = self._current_row()
        if row < 0:
            return
        new_row = row + int(delta)
        if new_row < 0 or new_row >= len(self.rules):
            return
        self.rules[row], self.rules[new_row] = self.rules[new_row], self.rules[row]
        self._refresh()
        self.table.selectRow(new_row)

    def _remove_selected(self):
        row = self._current_row()
        if row < 0 or row >= len(self.rules):
            return
        del self.rules[row]
        self._refresh()

    def _test_rules(self):
        path = self.txt_test.text().strip()
        if not path:
            return
        try:
            from src.core.selection_rules import parse_rules

            rules = parse_rules(self.rules)
            match = None
            for r in rules:
                if r.matches(path):
                    match = r
                    break
            if match:
                QMessageBox.information(
                    self,
                    strings.tr("app_title"),
                    strings.tr("msg_rule_test_match").format(action=match.action, pattern=match.pattern),
                )
            else:
                QMessageBox.information(self, strings.tr("app_title"), strings.tr("msg_rule_test_no_match"))
        except Exception as e:
            QMessageBox.warning(self, strings.tr("app_title"), str(e))

    def get_rules(self) -> list:
        return list(self.rules)

