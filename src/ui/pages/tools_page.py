from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
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
    window.btn_tools_go_scan.setCursor(Qt.CursorShape.PointingHandCursor)
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
    window.btn_empty_tools.setCursor(Qt.CursorShape.PointingHandCursor)
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
    window.cmb_quarantine_status = QComboBox()
    window.cmb_quarantine_status.addItem(strings.tr("opt_status_quarantined"), "quarantined")
    window.cmb_quarantine_status.addItem(strings.tr("opt_status_all"), "")
    window.cmb_quarantine_status.addItem(strings.tr("opt_status_restored"), "restored")
    window.cmb_quarantine_status.addItem(strings.tr("opt_status_purged"), "purged")
    window.cmb_quarantine_status.currentIndexChanged.connect(lambda _i: window.refresh_quarantine_list(reset_page=True))
    q_top.addWidget(window.cmb_quarantine_status)
    window.txt_quarantine_min_size = QLineEdit()
    window.txt_quarantine_min_size.setPlaceholderText(strings.tr("ph_min_size_bytes"))
    window.txt_quarantine_min_size.textChanged.connect(lambda _t: window.refresh_quarantine_list(reset_page=True))
    q_top.addWidget(window.txt_quarantine_min_size)
    window.txt_quarantine_max_size = QLineEdit()
    window.txt_quarantine_max_size.setPlaceholderText(strings.tr("ph_max_size_bytes"))
    window.txt_quarantine_max_size.textChanged.connect(lambda _t: window.refresh_quarantine_list(reset_page=True))
    q_top.addWidget(window.txt_quarantine_max_size)
    window.txt_quarantine_date_from = QLineEdit()
    window.txt_quarantine_date_from.setPlaceholderText(strings.tr("ph_date_from"))
    window.txt_quarantine_date_from.textChanged.connect(lambda _t: window.refresh_quarantine_list(reset_page=True))
    q_top.addWidget(window.txt_quarantine_date_from)
    window.txt_quarantine_date_to = QLineEdit()
    window.txt_quarantine_date_to.setPlaceholderText(strings.tr("ph_date_to"))
    window.txt_quarantine_date_to.textChanged.connect(lambda _t: window.refresh_quarantine_list(reset_page=True))
    q_top.addWidget(window.txt_quarantine_date_to)
    window.btn_quarantine_refresh = QPushButton(strings.tr("btn_refresh"))
    window.btn_quarantine_refresh.clicked.connect(lambda: window.refresh_quarantine_list(reset_page=True))
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
    qhdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    qhdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    qhdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    qhdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    window.tbl_quarantine.setColumnWidth(1, 110)
    window.tbl_quarantine.setColumnWidth(2, 160)
    window.tbl_quarantine.setColumnWidth(3, 110)
    window.tbl_quarantine.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    window.tbl_quarantine.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    window.tbl_quarantine.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
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

    window.btn_quarantine_prev = QPushButton(strings.tr("btn_prev"))
    window.btn_quarantine_prev.clicked.connect(lambda: window.change_quarantine_page(-1))
    q_btns.addWidget(window.btn_quarantine_prev)
    window.lbl_quarantine_page = QLabel("")
    window.lbl_quarantine_page.setObjectName("filter_count")
    q_btns.addWidget(window.lbl_quarantine_page)
    window.btn_quarantine_next = QPushButton(strings.tr("btn_next"))
    window.btn_quarantine_next.clicked.connect(lambda: window.change_quarantine_page(1))
    q_btns.addWidget(window.btn_quarantine_next)

    window.btn_quarantine_purge_all = QPushButton(strings.tr("btn_purge_all"))
    window.btn_quarantine_purge_all.setObjectName("btn_danger")
    window.btn_quarantine_purge_all.clicked.connect(window.purge_all_quarantine)
    q_btns.addWidget(window.btn_quarantine_purge_all)

    quarantine_layout.addLayout(q_btns)
    tools_layout.addWidget(quarantine_card)

    # Safelist / Ignore card
    exemption_card = QWidget()
    exemption_card.setObjectName("folder_card")
    exemption_layout = QVBoxLayout(exemption_card)
    exemption_layout.setContentsMargins(20, 16, 20, 16)
    exemption_layout.setSpacing(12)

    window.lbl_exemption_title = QLabel(strings.tr("tool_exemptions_title"))
    window.lbl_exemption_title.setObjectName("card_title")
    exemption_layout.addWidget(window.lbl_exemption_title)

    window.lbl_exemption_desc = QLabel(strings.tr("tool_exemptions_desc"))
    window.lbl_exemption_desc.setWordWrap(True)
    window.lbl_exemption_desc.setObjectName("card_desc")
    exemption_layout.addWidget(window.lbl_exemption_desc)

    ex_form = QHBoxLayout()
    ex_form.setSpacing(8)
    window.cmb_exemption_kind = QComboBox()
    window.cmb_exemption_kind.addItem(strings.tr("ex_kind_exact_path"), "exact_path")
    window.cmb_exemption_kind.addItem(strings.tr("ex_kind_path_glob"), "path_glob")
    window.cmb_exemption_kind.addItem(strings.tr("ex_kind_content_hash"), "content_hash")
    ex_form.addWidget(window.cmb_exemption_kind)

    window.cmb_exemption_action = QComboBox()
    window.cmb_exemption_action.addItem(strings.tr("ex_action_safelist"), "safelist")
    window.cmb_exemption_action.addItem(strings.tr("ex_action_ignore"), "ignore")
    ex_form.addWidget(window.cmb_exemption_action)

    window.txt_exemption_value = QLineEdit()
    window.txt_exemption_value.setPlaceholderText(strings.tr("ph_exemption_value"))
    ex_form.addWidget(window.txt_exemption_value, 2)

    window.txt_exemption_note = QLineEdit()
    window.txt_exemption_note.setPlaceholderText(strings.tr("ph_exemption_note"))
    ex_form.addWidget(window.txt_exemption_note, 1)

    window.btn_exemption_save = QPushButton(strings.tr("btn_save"))
    window.btn_exemption_save.clicked.connect(window.save_exemption_from_form)
    ex_form.addWidget(window.btn_exemption_save)

    window.btn_exemption_delete = QPushButton(strings.tr("btn_delete"))
    window.btn_exemption_delete.clicked.connect(window.delete_selected_exemption)
    ex_form.addWidget(window.btn_exemption_delete)
    exemption_layout.addLayout(ex_form)

    ex_top = QHBoxLayout()
    ex_top.setSpacing(8)
    window.txt_exemption_search = QLineEdit()
    window.txt_exemption_search.setPlaceholderText(strings.tr("ph_exemption_search"))
    window.txt_exemption_search.textChanged.connect(lambda _t: window.refresh_exemption_list())
    ex_top.addWidget(window.txt_exemption_search, 1)
    window.btn_exemption_refresh = QPushButton(strings.tr("btn_refresh"))
    window.btn_exemption_refresh.clicked.connect(window.refresh_exemption_list)
    ex_top.addWidget(window.btn_exemption_refresh)
    exemption_layout.addLayout(ex_top)

    window.tbl_exemptions = QTableWidget()
    window.tbl_exemptions.setColumnCount(6)
    window.tbl_exemptions.setHorizontalHeaderLabels(
        [
            strings.tr("col_id"),
            strings.tr("col_kind"),
            strings.tr("col_value"),
            strings.tr("col_action"),
            strings.tr("col_note"),
            strings.tr("col_created"),
        ]
    )
    ehdr = window.tbl_exemptions.horizontalHeader()
    ehdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    ehdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    ehdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    ehdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    ehdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
    ehdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
    window.tbl_exemptions.setColumnWidth(0, 60)
    window.tbl_exemptions.setColumnWidth(1, 130)
    window.tbl_exemptions.setColumnWidth(3, 100)
    window.tbl_exemptions.setColumnWidth(5, 150)
    window.tbl_exemptions.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    window.tbl_exemptions.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    window.tbl_exemptions.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    window.tbl_exemptions.itemSelectionChanged.connect(window.on_exemption_selection_changed)
    window.tbl_exemptions.setMinimumHeight(150)
    window.tbl_exemptions.setMaximumHeight(240)
    exemption_layout.addWidget(window.tbl_exemptions, 1)

    tools_layout.addWidget(exemption_card)

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
    ohdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    ohdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    ohdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    ohdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    ohdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
    window.tbl_ops.setColumnWidth(0, 70)
    window.tbl_ops.setColumnWidth(1, 160)
    window.tbl_ops.setColumnWidth(2, 170)
    window.tbl_ops.setColumnWidth(3, 110)
    window.tbl_ops.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    window.tbl_ops.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    window.tbl_ops.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
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
