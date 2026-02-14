from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QHeaderView,
    QAbstractItemView,
)
from PySide6.QtCore import Qt

from src.utils.i18n import strings


def build_tools_page(window) -> QWidget:
    page = QWidget()
    tools_layout = QVBoxLayout(page)
    tools_layout.setSpacing(16)
    tools_layout.setContentsMargins(16, 12, 16, 12)

    window.lbl_tools_title = QLabel(strings.tr("nav_tools"))
    window.lbl_tools_title.setObjectName("page_title")
    tools_layout.addWidget(window.lbl_tools_title)

    window.lbl_tools_hint = QLabel(strings.tr("msg_tools_page_hint"))
    window.lbl_tools_hint.setObjectName("card_desc")
    window.lbl_tools_hint.setWordWrap(True)
    tools_layout.addWidget(window.lbl_tools_hint)

    window.lbl_tools_target = QLabel("")
    window.lbl_tools_target.setObjectName("filter_count")
    tools_layout.addWidget(window.lbl_tools_target)

    window.btn_tools_go_scan = QPushButton(strings.tr("btn_go_scan"))
    window.btn_tools_go_scan.setMinimumHeight(40)
    window.btn_tools_go_scan.setCursor(Qt.PointingHandCursor)
    window.btn_tools_go_scan.clicked.connect(lambda: window._navigate_to("scan"))
    window.btn_tools_go_scan.setVisible(False)
    tools_layout.addWidget(window.btn_tools_go_scan)

    # Empty Folder Finder card
    empty_card = QWidget()
    empty_card.setObjectName("folder_card")
    empty_card_layout = QVBoxLayout(empty_card)
    empty_card_layout.setContentsMargins(20, 16, 20, 16)
    empty_card_layout.setSpacing(12)

    window.lbl_empty_title = QLabel(strings.tr("action_empty_finder"))
    window.lbl_empty_title.setObjectName("card_title")
    empty_card_layout.addWidget(window.lbl_empty_title)

    window.lbl_empty_desc = QLabel(strings.tr("msg_empty_finder_desc"))
    window.lbl_empty_desc.setWordWrap(True)
    window.lbl_empty_desc.setObjectName("card_desc")
    empty_card_layout.addWidget(window.lbl_empty_desc)

    window.btn_empty_tools = QPushButton(strings.tr("btn_scan_empty"))
    window.btn_empty_tools.setMinimumHeight(44)
    window.btn_empty_tools.setCursor(Qt.PointingHandCursor)
    window.btn_empty_tools.clicked.connect(window.open_empty_finder)
    empty_card_layout.addWidget(window.btn_empty_tools)

    tools_layout.addWidget(empty_card)

    # Quarantine card
    quarantine_card = QWidget()
    quarantine_card.setObjectName("folder_card")
    quarantine_layout = QVBoxLayout(quarantine_card)
    quarantine_layout.setContentsMargins(20, 16, 20, 16)
    quarantine_layout.setSpacing(12)

    window.lbl_quarantine_title = QLabel(strings.tr("tool_quarantine_title"))
    window.lbl_quarantine_title.setObjectName("card_title")
    quarantine_layout.addWidget(window.lbl_quarantine_title)

    window.lbl_quarantine_desc = QLabel(strings.tr("tool_quarantine_desc"))
    window.lbl_quarantine_desc.setWordWrap(True)
    window.lbl_quarantine_desc.setObjectName("card_desc")
    quarantine_layout.addWidget(window.lbl_quarantine_desc)

    q_top = QHBoxLayout()
    q_top.setSpacing(8)
    window.txt_quarantine_search = QLineEdit()
    window.txt_quarantine_search.setPlaceholderText(strings.tr("ph_quarantine_search"))
    window.txt_quarantine_search.textChanged.connect(lambda _t: window.refresh_quarantine_list())
    q_top.addWidget(window.txt_quarantine_search, 1)
    window.btn_quarantine_refresh = QPushButton(strings.tr("btn_refresh"))
    window.btn_quarantine_refresh.clicked.connect(window.refresh_quarantine_list)
    q_top.addWidget(window.btn_quarantine_refresh)
    quarantine_layout.addLayout(q_top)

    window.tbl_quarantine = QTableWidget()
    window.tbl_quarantine.setColumnCount(4)
    window.tbl_quarantine.setHorizontalHeaderLabels(
        [
            strings.tr("col_path"),
            strings.tr("col_size"),
            strings.tr("col_created"),
            strings.tr("col_status"),
        ]
    )
    qhdr = window.tbl_quarantine.horizontalHeader()
    qhdr.setSectionResizeMode(0, QHeaderView.Stretch)
    qhdr.setSectionResizeMode(1, QHeaderView.Fixed)
    qhdr.setSectionResizeMode(2, QHeaderView.Fixed)
    qhdr.setSectionResizeMode(3, QHeaderView.Fixed)
    window.tbl_quarantine.setColumnWidth(1, 110)
    window.tbl_quarantine.setColumnWidth(2, 160)
    window.tbl_quarantine.setColumnWidth(3, 110)
    window.tbl_quarantine.setSelectionBehavior(QAbstractItemView.SelectRows)
    window.tbl_quarantine.setSelectionMode(QAbstractItemView.ExtendedSelection)
    window.tbl_quarantine.setEditTriggers(QAbstractItemView.NoEditTriggers)
    window.tbl_quarantine.setMinimumHeight(180)
    window.tbl_quarantine.setMaximumHeight(260)
    quarantine_layout.addWidget(window.tbl_quarantine, 1)

    q_btns = QHBoxLayout()
    q_btns.setSpacing(8)
    window.btn_quarantine_restore = QPushButton(strings.tr("btn_restore_selected"))
    window.btn_quarantine_restore.clicked.connect(window.restore_selected_quarantine)
    q_btns.addWidget(window.btn_quarantine_restore)

    window.btn_quarantine_purge = QPushButton(strings.tr("btn_purge_selected"))
    window.btn_quarantine_purge.clicked.connect(window.purge_selected_quarantine)
    q_btns.addWidget(window.btn_quarantine_purge)

    q_btns.addStretch()

    window.btn_quarantine_purge_all = QPushButton(strings.tr("btn_purge_all"))
    window.btn_quarantine_purge_all.setObjectName("btn_danger")
    window.btn_quarantine_purge_all.clicked.connect(window.purge_all_quarantine)
    q_btns.addWidget(window.btn_quarantine_purge_all)

    quarantine_layout.addLayout(q_btns)
    tools_layout.addWidget(quarantine_card)

    # Rules card
    rules_card = QWidget()
    rules_card.setObjectName("folder_card")
    rules_layout = QVBoxLayout(rules_card)
    rules_layout.setContentsMargins(20, 16, 20, 16)
    rules_layout.setSpacing(12)

    window.lbl_rules_title = QLabel(strings.tr("tool_rules_title"))
    window.lbl_rules_title.setObjectName("card_title")
    rules_layout.addWidget(window.lbl_rules_title)

    window.lbl_rules_desc = QLabel(strings.tr("tool_rules_desc"))
    window.lbl_rules_desc.setWordWrap(True)
    window.lbl_rules_desc.setObjectName("card_desc")
    rules_layout.addWidget(window.lbl_rules_desc)

    r_btns = QHBoxLayout()
    r_btns.setSpacing(8)
    window.btn_rules_edit = QPushButton(strings.tr("btn_edit_rules"))
    window.btn_rules_edit.clicked.connect(window.open_selection_rules_dialog)
    r_btns.addWidget(window.btn_rules_edit)

    window.btn_rules_apply = QPushButton(strings.tr("btn_apply_rules"))
    window.btn_rules_apply.clicked.connect(window.select_duplicates_by_rules)
    r_btns.addWidget(window.btn_rules_apply)

    r_btns.addStretch()
    rules_layout.addLayout(r_btns)
    tools_layout.addWidget(rules_card)

    # Operations card
    ops_card = QWidget()
    ops_card.setObjectName("folder_card")
    ops_layout = QVBoxLayout(ops_card)
    ops_layout.setContentsMargins(20, 16, 20, 16)
    ops_layout.setSpacing(12)

    window.lbl_ops_title = QLabel(strings.tr("tool_ops_title"))
    window.lbl_ops_title.setObjectName("card_title")
    ops_layout.addWidget(window.lbl_ops_title)

    ops_top = QHBoxLayout()
    ops_top.setSpacing(8)
    window.btn_ops_refresh = QPushButton(strings.tr("btn_refresh"))
    window.btn_ops_refresh.clicked.connect(window.refresh_operations_list)
    ops_top.addWidget(window.btn_ops_refresh)
    ops_top.addStretch()
    window.btn_ops_view = QPushButton(strings.tr("btn_view_details"))
    window.btn_ops_view.clicked.connect(window.view_selected_operation)
    ops_top.addWidget(window.btn_ops_view)
    ops_layout.addLayout(ops_top)

    window.tbl_ops = QTableWidget()
    window.tbl_ops.setColumnCount(5)
    window.tbl_ops.setHorizontalHeaderLabels(
        [
            strings.tr("col_id"),
            strings.tr("col_created"),
            strings.tr("col_type"),
            strings.tr("col_status"),
            strings.tr("col_message"),
        ]
    )
    ohdr = window.tbl_ops.horizontalHeader()
    ohdr.setSectionResizeMode(0, QHeaderView.Fixed)
    ohdr.setSectionResizeMode(1, QHeaderView.Fixed)
    ohdr.setSectionResizeMode(2, QHeaderView.Fixed)
    ohdr.setSectionResizeMode(3, QHeaderView.Fixed)
    ohdr.setSectionResizeMode(4, QHeaderView.Stretch)
    window.tbl_ops.setColumnWidth(0, 70)
    window.tbl_ops.setColumnWidth(1, 160)
    window.tbl_ops.setColumnWidth(2, 170)
    window.tbl_ops.setColumnWidth(3, 110)
    window.tbl_ops.setSelectionBehavior(QAbstractItemView.SelectRows)
    window.tbl_ops.setSelectionMode(QAbstractItemView.SingleSelection)
    window.tbl_ops.setEditTriggers(QAbstractItemView.NoEditTriggers)
    window.tbl_ops.setMinimumHeight(160)
    window.tbl_ops.setMaximumHeight(240)
    ops_layout.addWidget(window.tbl_ops, 1)

    window.btn_hardlink_checked = QPushButton(strings.tr("btn_hardlink_checked"))
    window.btn_hardlink_checked.setVisible(False)
    window.btn_hardlink_checked.clicked.connect(window.hardlink_consolidate_checked)
    ops_layout.addWidget(window.btn_hardlink_checked)

    tools_layout.addWidget(ops_card)
    tools_layout.addStretch()

    return page

