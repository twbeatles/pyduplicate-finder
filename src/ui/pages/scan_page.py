from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QCheckBox,
    QGroupBox,
    QSpinBox,
    QLineEdit,
    QListWidget,
    QDoubleSpinBox,
    QFrame,
)
from PySide6.QtCore import Qt

from src.utils.i18n import strings


def _create_separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.VLine)
    sep.setFrameShadow(QFrame.Sunken)
    return sep


def build_scan_page(window) -> QWidget:
    """
    Build Scan page (settings + execution).

    This function intentionally assigns widgets onto the main window instance so
    the existing logic methods can keep referencing `self.<widget>` names.
    """
    page = QWidget()
    main_layout = QVBoxLayout(page)
    main_layout.setSpacing(12)
    main_layout.setContentsMargins(16, 12, 16, 12)

    # === Settings & Scan Actions (Card style) ===
    window.top_container = QWidget()
    window.top_container.setObjectName("folder_card")
    top_main_layout = QVBoxLayout(window.top_container)
    top_main_layout.setSpacing(12)
    top_main_layout.setContentsMargins(20, 16, 20, 16)

    # --- Row 1: Folder Selection Header ---
    folder_header = QHBoxLayout()
    folder_header.setSpacing(8)

    folder_label = QLabel(strings.tr("grp_search_loc"))
    folder_label.setObjectName("card_title")
    folder_header.addWidget(folder_label)

    window.lbl_folder_count = QLabel("")
    window.lbl_folder_count.setObjectName("results_meta")
    folder_header.addWidget(window.lbl_folder_count)

    window.btn_add_folder = QPushButton(strings.tr("btn_add_folder"))
    window.btn_add_folder.setMinimumHeight(32)
    window.btn_add_folder.setCursor(Qt.PointingHandCursor)
    window.btn_add_folder.clicked.connect(window.add_folder)

    window.btn_add_drive = QPushButton(strings.tr("btn_add_drive"))
    window.btn_add_drive.setMinimumHeight(32)
    window.btn_add_drive.setCursor(Qt.PointingHandCursor)
    window.btn_add_drive.clicked.connect(window.add_drive_dialog)

    window.btn_remove_folder = QPushButton(strings.tr("btn_remove_folder"))
    window.btn_remove_folder.setMinimumHeight(32)
    window.btn_remove_folder.setCursor(Qt.PointingHandCursor)
    window.btn_remove_folder.setToolTip(strings.tr("btn_remove_folder"))
    window.btn_remove_folder.clicked.connect(window.remove_selected_folder)

    window.btn_clear_folder = QPushButton(strings.tr("btn_clear"))
    window.btn_clear_folder.setMinimumHeight(32)
    window.btn_clear_folder.setCursor(Qt.PointingHandCursor)
    window.btn_clear_folder.clicked.connect(window.clear_folders)

    folder_header.addStretch()
    folder_header.addWidget(window.btn_add_folder)
    folder_header.addWidget(window.btn_add_drive)
    folder_header.addWidget(window.btn_remove_folder)
    folder_header.addWidget(window.btn_clear_folder)
    top_main_layout.addLayout(folder_header)

    # --- Row 2: Folder List ---
    window.list_folders = QListWidget()
    window.list_folders.setMinimumHeight(60)
    top_main_layout.addWidget(window.list_folders, 1)

    # --- Row 3: Collapsible Filter Options ---
    window.btn_filter_toggle = QPushButton(strings.tr("lbl_filter_options") + " ▼")
    window.btn_filter_toggle.setObjectName("filter_header")
    window.btn_filter_toggle.setCheckable(True)
    window.btn_filter_toggle.setChecked(True)
    window.btn_filter_toggle.setCursor(Qt.PointingHandCursor)
    window.btn_filter_toggle.clicked.connect(window._toggle_filter_panel)
    top_main_layout.addWidget(window.btn_filter_toggle)

    window.filter_container = QWidget()
    window.filter_container.setObjectName("filter_card")
    filter_main_layout = QVBoxLayout(window.filter_container)
    filter_main_layout.setSpacing(14)
    filter_main_layout.setContentsMargins(16, 14, 16, 14)

    # Basic filters header
    window.lbl_filter_basic = QLabel(strings.tr("hdr_filters_basic"))
    window.lbl_filter_basic.setObjectName("section_header")
    filter_main_layout.addWidget(window.lbl_filter_basic)

    row1_layout = QHBoxLayout()
    row1_layout.setSpacing(20)

    ext_layout = QHBoxLayout()
    ext_layout.setSpacing(8)
    window.lbl_ext = QLabel(strings.tr("lbl_ext"))
    window.lbl_ext.setObjectName("filter_label")
    ext_layout.addWidget(window.lbl_ext)
    window.txt_extensions = QLineEdit()
    window.txt_extensions.setPlaceholderText(strings.tr("ph_ext"))
    window.txt_extensions.setMinimumWidth(120)
    window.txt_extensions.setMaximumWidth(180)
    window.txt_extensions.setMinimumHeight(32)
    ext_layout.addWidget(window.txt_extensions)
    row1_layout.addLayout(ext_layout)

    size_layout = QHBoxLayout()
    size_layout.setSpacing(8)
    window.lbl_min_size = QLabel(strings.tr("lbl_min_size"))
    window.lbl_min_size.setObjectName("filter_label")
    size_layout.addWidget(window.lbl_min_size)
    window.spin_min_size = QSpinBox()
    window.spin_min_size.setRange(0, 10000000)
    window.spin_min_size.setValue(0)
    window.spin_min_size.setSuffix(" KB")
    window.spin_min_size.setMinimumWidth(100)
    window.spin_min_size.setMaximumWidth(140)
    window.spin_min_size.setMinimumHeight(32)
    size_layout.addWidget(window.spin_min_size)
    row1_layout.addLayout(size_layout)

    filter_main_layout.addLayout(row1_layout)

    # Comparison header
    window.lbl_filter_compare = QLabel(strings.tr("hdr_filters_compare"))
    window.lbl_filter_compare.setObjectName("section_header")
    filter_main_layout.addWidget(window.lbl_filter_compare)

    row2_layout = QHBoxLayout()
    row2_layout.setSpacing(20)
    window.chk_same_name = QCheckBox(strings.tr("chk_same_name"))
    window.chk_same_name.setToolTip(strings.tr("tip_same_name"))
    window.chk_name_only = QCheckBox(strings.tr("chk_name_only"))
    window.chk_name_only.setToolTip(strings.tr("tip_name_only"))
    window.chk_byte_compare = QCheckBox(strings.tr("chk_byte_compare"))
    row2_layout.addWidget(window.chk_same_name)
    row2_layout.addWidget(window.chk_name_only)
    row2_layout.addWidget(window.chk_byte_compare)
    row2_layout.addStretch()
    filter_main_layout.addLayout(row2_layout)

    # Advanced header
    window.lbl_filter_advanced = QLabel(strings.tr("hdr_filters_advanced"))
    window.lbl_filter_advanced.setObjectName("section_header")
    filter_main_layout.addWidget(window.lbl_filter_advanced)

    row3_layout = QHBoxLayout()
    row3_layout.setSpacing(20)

    window.chk_protect_system = QCheckBox(strings.tr("chk_protect_system"))
    window.chk_protect_system.setChecked(True)
    window.chk_use_trash = QCheckBox(strings.tr("chk_use_trash"))
    window.chk_use_trash.setToolTip(strings.tr("tip_use_trash"))
    row3_layout.addWidget(window.chk_protect_system)
    row3_layout.addWidget(window.chk_use_trash)
    row3_layout.addWidget(_create_separator())

    window.chk_similar_image = QCheckBox(strings.tr("chk_similar_image"))
    window.chk_similar_image.setToolTip(strings.tr("tip_similar_image"))
    row3_layout.addWidget(window.chk_similar_image)

    window.lbl_similarity = QLabel(strings.tr("lbl_similarity_threshold"))
    window.spin_similarity = QDoubleSpinBox()
    window.spin_similarity.setRange(0.1, 1.0)
    window.spin_similarity.setSingleStep(0.05)
    window.spin_similarity.setValue(0.9)
    window.spin_similarity.setDecimals(2)
    window.spin_similarity.setMinimumWidth(80)
    window.spin_similarity.setEnabled(False)
    row3_layout.addWidget(window.lbl_similarity)
    row3_layout.addWidget(window.spin_similarity)
    row3_layout.addWidget(_create_separator())

    window.btn_exclude_patterns = QPushButton(strings.tr("btn_exclude_patterns"))
    window.btn_exclude_patterns.setMinimumHeight(32)
    window.btn_exclude_patterns.setObjectName("btn_icon")
    window.btn_exclude_patterns.setCursor(Qt.PointingHandCursor)
    window.btn_exclude_patterns.clicked.connect(window.open_exclude_patterns_dialog)
    row3_layout.addWidget(window.btn_exclude_patterns)

    row3_layout.addStretch()
    filter_main_layout.addLayout(row3_layout)

    window.chk_name_only.toggled.connect(window._sync_filter_states)
    window.chk_similar_image.toggled.connect(window._sync_filter_states)

    top_main_layout.addWidget(window.filter_container)
    window._sync_filter_states()

    # --- Row 4: Action Buttons ---
    action_layout = QHBoxLayout()
    action_layout.setSpacing(12)

    window.btn_start_scan = QPushButton(strings.tr("btn_start_scan"))
    window.btn_start_scan.setMinimumHeight(40)
    window.btn_start_scan.setMinimumWidth(150)
    window.btn_start_scan.setCursor(Qt.PointingHandCursor)
    window.btn_start_scan.setObjectName("btn_primary")
    window.btn_start_scan.clicked.connect(window.start_scan)

    window.btn_stop_scan = QPushButton(strings.tr("scan_stop"))
    window.btn_stop_scan.setMinimumHeight(40)
    window.btn_stop_scan.setCursor(Qt.PointingHandCursor)
    window.btn_stop_scan.clicked.connect(window.stop_scan)
    window.btn_stop_scan.setEnabled(False)

    action_layout.addWidget(window.btn_start_scan)
    action_layout.addWidget(window.btn_stop_scan)

    window.lbl_scan_stage = QLabel(strings.tr("msg_scan_stage").format(stage=strings.tr("status_ready")))
    window.lbl_scan_stage.setObjectName("stage_badge")
    action_layout.addWidget(window.lbl_scan_stage)
    action_layout.addStretch()
    top_main_layout.addLayout(action_layout)

    # --- Row 5: Last results summary + CTA ---
    summary_row = QHBoxLayout()
    summary_row.setSpacing(8)
    window.lbl_scan_summary = QLabel("")
    window.lbl_scan_summary.setObjectName("results_meta")
    summary_row.addWidget(window.lbl_scan_summary, 1)

    window.btn_go_results = QPushButton(strings.tr("nav_results"))
    window.btn_go_results.setMinimumHeight(32)
    window.btn_go_results.setCursor(Qt.PointingHandCursor)
    window.btn_go_results.setObjectName("btn_secondary")
    window.btn_go_results.setEnabled(False)
    window.btn_go_results.clicked.connect(lambda: window._navigate_to("results"))
    summary_row.addWidget(window.btn_go_results)
    top_main_layout.addLayout(summary_row)

    main_layout.addWidget(window.top_container, 0)

    # Drag & Drop folder support lives on the main window; the list is here.
    try:
        window.list_folders.itemSelectionChanged.connect(window._on_folders_changed)
    except Exception:
        pass

    return page

