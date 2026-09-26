
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.design_system.components.density_switch import DensitySwitch
from src.ui.design_system.components.page_header import create_page_header
from src.ui.design_system.components.section_card import create_card
from src.ui.design_system.tokens import SPACING_LG, SPACING_MD
from src.utils.i18n import strings


def _stored_str(window, key: str, default: str) -> str:
    try:
        settings = getattr(window, "settings", None)
        if settings is None:
            return default
        value = settings.value(key, default)
        return default if value is None else str(value)
    except Exception:
        return default


def _stored_follow_system(window) -> bool:
    try:
        from src.ui.design_system.system_theme import normalize_bool
        settings = getattr(window, "settings", None)
        if settings is None:
            return True
        return normalize_bool(settings.value("app/follow_system_theme", True), True)
    except Exception:
        return True


def build_settings_page(window) -> QWidget:
    page = QWidget()
    settings_layout = QVBoxLayout(page)
    settings_layout.setSpacing(SPACING_LG)
    settings_layout.setContentsMargins(16, 12, 16, 12)

    header_wrap, _header_row, window.lbl_settings_title = create_page_header(
        strings.tr("nav_settings"), page
    )
    window.lbl_settings_title.setObjectName("page_title")
    settings_layout.addWidget(header_wrap)

    window.lbl_settings_hint = QLabel(strings.tr("msg_settings_page_hint"))
    window.lbl_settings_hint.setObjectName("card_desc")
    window.lbl_settings_hint.setWordWrap(True)
    settings_layout.addWidget(window.lbl_settings_hint)

    # Theme card
    theme_card, theme_card_layout = create_card(page)
    window.lbl_theme_title = QLabel(strings.tr("action_theme"))
    window.lbl_theme_title.setObjectName("card_title")
    theme_card_layout.addWidget(window.lbl_theme_title)

    window.btn_theme_settings = QPushButton(strings.tr("action_theme"))
    window.btn_theme_settings.setCheckable(True)
    window.btn_theme_settings.setMinimumHeight(44)
    window.btn_theme_settings.setCursor(Qt.CursorShape.PointingHandCursor)
    window.btn_theme_settings.clicked.connect(window.toggle_theme)
    theme_card_layout.addWidget(window.btn_theme_settings)
    settings_layout.addWidget(theme_card)

    # Appearance card (density + follow-system, srtgo theme pattern)
    appearance_card, appearance_layout = create_card(page)
    window.lbl_appearance_title = QLabel(strings.tr("settings_appearance_title"))
    window.lbl_appearance_title.setObjectName("card_title")
    appearance_layout.addWidget(window.lbl_appearance_title)

    density_row = QHBoxLayout()
    density_row.setSpacing(SPACING_MD)
    window.lbl_density = QLabel(strings.tr("settings_density_label"))
    window.lbl_density.setObjectName("filter_label")
    density_row.addWidget(window.lbl_density)
    window.density_switch = DensitySwitch(
        current=_stored_str(window, "app/density", "comfortable")
    )
    if hasattr(window, "apply_density"):
        window.density_switch.density_changed.connect(window.apply_density)
    density_row.addWidget(window.density_switch, 1)
    appearance_layout.addLayout(density_row)

    window.lbl_density_tip = QLabel(strings.tr("tip_density"))
    window.lbl_density_tip.setObjectName("card_desc")
    window.lbl_density_tip.setWordWrap(True)
    appearance_layout.addWidget(window.lbl_density_tip)

    window.chk_follow_system_theme = QCheckBox(strings.tr("settings_follow_system"))
    window.chk_follow_system_theme.setChecked(_stored_follow_system(window))
    if hasattr(window, "set_follow_system_theme"):
        window.chk_follow_system_theme.toggled.connect(window.set_follow_system_theme)
    appearance_layout.addWidget(window.chk_follow_system_theme)
    settings_layout.addWidget(appearance_card)

    # Shortcuts card
    shortcut_card, shortcut_card_layout = create_card(page)
    window.lbl_shortcut_title = QLabel(strings.tr("action_shortcut_settings"))
    window.lbl_shortcut_title.setObjectName("card_title")
    shortcut_card_layout.addWidget(window.lbl_shortcut_title)

    window.btn_shortcuts_settings = QPushButton(strings.tr("action_shortcut_settings"))
    window.btn_shortcuts_settings.setMinimumHeight(44)
    window.btn_shortcuts_settings.setCursor(Qt.CursorShape.PointingHandCursor)
    window.btn_shortcuts_settings.clicked.connect(window.open_shortcut_settings)
    shortcut_card_layout.addWidget(window.btn_shortcuts_settings)
    settings_layout.addWidget(shortcut_card)

    # Presets card
    preset_card, preset_card_layout = create_card(page)
    window.lbl_preset_title = QLabel(strings.tr("action_preset"))
    window.lbl_preset_title.setObjectName("card_title")
    preset_card_layout.addWidget(window.lbl_preset_title)

    window.btn_preset_settings = QPushButton(strings.tr("btn_manage_presets"))
    window.btn_preset_settings.setMinimumHeight(44)
    window.btn_preset_settings.setCursor(Qt.CursorShape.PointingHandCursor)
    window.btn_preset_settings.clicked.connect(window.open_preset_dialog)
    preset_card_layout.addWidget(window.btn_preset_settings)
    settings_layout.addWidget(preset_card)

    # Cache DB card
    cache_card, cache_layout = create_card(page)
    window.lbl_cache_title = QLabel(strings.tr("settings_cache_title"))
    window.lbl_cache_title.setObjectName("card_title")
    cache_layout.addWidget(window.lbl_cache_title)

    window.lbl_cache_desc = QLabel(strings.tr("settings_cache_desc"))
    window.lbl_cache_desc.setObjectName("card_desc")
    window.lbl_cache_desc.setWordWrap(True)
    cache_layout.addWidget(window.lbl_cache_desc)

    window.txt_cache_db_path = QLineEdit()
    try:
        window.txt_cache_db_path.setText(str(getattr(window.cache_manager, "db_path", "") or ""))
    except Exception:
        window.txt_cache_db_path.setText("")
    window.txt_cache_db_path.setReadOnly(True)
    cache_layout.addWidget(window.txt_cache_db_path)

    row = QHBoxLayout()
    row.setSpacing(SPACING_MD)
    window.btn_cache_open = QPushButton(strings.tr("ctx_open_folder"))
    window.btn_cache_open.clicked.connect(window.open_cache_db_folder)
    row.addWidget(window.btn_cache_open)
    window.btn_cache_copy = QPushButton(strings.tr("ctx_copy_path"))
    window.btn_cache_copy.clicked.connect(window.copy_cache_db_path)
    row.addWidget(window.btn_cache_copy)
    row.addStretch()
    cache_layout.addLayout(row)

    row_cache_policy = QHBoxLayout()
    row_cache_policy.setSpacing(SPACING_MD)
    window.lbl_cache_session_keep_latest = QLabel(strings.tr("settings_cache_session_keep_latest"))
    row_cache_policy.addWidget(window.lbl_cache_session_keep_latest)
    window.spin_cache_session_keep_latest = QSpinBox()
    window.spin_cache_session_keep_latest.setRange(1, 500)
    window.spin_cache_session_keep_latest.setValue(20)
    row_cache_policy.addWidget(window.spin_cache_session_keep_latest)

    window.lbl_cache_hash_cleanup_days = QLabel(strings.tr("settings_cache_hash_cleanup_days"))
    row_cache_policy.addWidget(window.lbl_cache_hash_cleanup_days)
    window.spin_cache_hash_cleanup_days = QSpinBox()
    window.spin_cache_hash_cleanup_days.setRange(1, 3650)
    window.spin_cache_hash_cleanup_days.setSuffix(strings.tr("term_days_suffix"))
    window.spin_cache_hash_cleanup_days.setValue(30)
    row_cache_policy.addWidget(window.spin_cache_hash_cleanup_days)
    row_cache_policy.addStretch()
    cache_layout.addLayout(row_cache_policy)

    window.btn_cache_apply = QPushButton(strings.tr("btn_apply"))
    window.btn_cache_apply.clicked.connect(window.apply_cache_settings)
    cache_layout.addWidget(window.btn_cache_apply)

    settings_layout.addWidget(cache_card)

    # Quarantine settings card
    quarantine_settings, quarantine_settings_layout = create_card(page)
    window.lbl_quarantine_settings_title = QLabel(strings.tr("settings_quarantine_title"))
    window.lbl_quarantine_settings_title.setObjectName("card_title")
    quarantine_settings_layout.addWidget(window.lbl_quarantine_settings_title)

    window.chk_quarantine_enabled = QCheckBox(strings.tr("settings_quarantine_enabled"))
    quarantine_settings_layout.addWidget(window.chk_quarantine_enabled)

    row_q = QHBoxLayout()
    row_q.setSpacing(SPACING_LG)
    window.lbl_quarantine_days = QLabel(strings.tr("settings_quarantine_days"))
    row_q.addWidget(window.lbl_quarantine_days)
    window.spin_quarantine_days = QSpinBox()
    window.spin_quarantine_days.setRange(1, 3650)
    window.spin_quarantine_days.setSuffix(strings.tr("term_days_suffix"))
    row_q.addWidget(window.spin_quarantine_days)

    window.lbl_quarantine_gb = QLabel(strings.tr("settings_quarantine_gb"))
    row_q.addWidget(window.lbl_quarantine_gb)
    window.spin_quarantine_gb = QSpinBox()
    window.spin_quarantine_gb.setRange(1, 10240)
    window.spin_quarantine_gb.setSuffix(" GB")
    row_q.addWidget(window.spin_quarantine_gb)
    row_q.addStretch()
    quarantine_settings_layout.addLayout(row_q)

    row_q2 = QHBoxLayout()
    row_q2.setSpacing(SPACING_MD)
    window.txt_quarantine_path = QLineEdit()
    window.txt_quarantine_path.setPlaceholderText(strings.tr("ph_quarantine_path"))
    row_q2.addWidget(window.txt_quarantine_path, 1)
    window.btn_quarantine_pick = QPushButton(strings.tr("btn_choose_folder"))
    window.btn_quarantine_pick.clicked.connect(window.choose_quarantine_folder)
    row_q2.addWidget(window.btn_quarantine_pick)
    quarantine_settings_layout.addLayout(row_q2)

    window.btn_quarantine_apply = QPushButton(strings.tr("btn_apply"))
    window.btn_quarantine_apply.clicked.connect(window.apply_quarantine_settings)
    quarantine_settings_layout.addWidget(window.btn_quarantine_apply)

    settings_layout.addWidget(quarantine_settings)

    # Hardlink settings card
    hardlink_settings, hardlink_settings_layout = create_card(page)
    window.lbl_hardlink_title = QLabel(strings.tr("settings_hardlink_title"))
    window.lbl_hardlink_title.setObjectName("card_title")
    hardlink_settings_layout.addWidget(window.lbl_hardlink_title)

    window.chk_enable_hardlink = QCheckBox(strings.tr("settings_hardlink_enabled"))
    window.chk_enable_hardlink.toggled.connect(window._sync_advanced_visibility)
    hardlink_settings_layout.addWidget(window.chk_enable_hardlink)

    settings_layout.addWidget(hardlink_settings)

    # Schedule settings card
    schedule_settings, schedule_layout = create_card(page)
    window.lbl_schedule_title = QLabel(strings.tr("settings_schedule_title"))
    window.lbl_schedule_title.setObjectName("card_title")
    schedule_layout.addWidget(window.lbl_schedule_title)

    window.chk_schedule_enabled = QCheckBox(strings.tr("settings_schedule_enabled"))
    schedule_layout.addWidget(window.chk_schedule_enabled)

    row_s1 = QHBoxLayout()
    row_s1.setSpacing(SPACING_MD)
    window.lbl_schedule_frequency = QLabel(strings.tr("settings_schedule_frequency"))
    row_s1.addWidget(window.lbl_schedule_frequency)
    window.cmb_schedule_frequency = QComboBox()
    window.cmb_schedule_frequency.addItem(strings.tr("term_daily"), "daily")
    window.cmb_schedule_frequency.addItem(strings.tr("term_weekly"), "weekly")
    row_s1.addWidget(window.cmb_schedule_frequency)

    window.lbl_schedule_weekday = QLabel(strings.tr("settings_schedule_weekday"))
    row_s1.addWidget(window.lbl_schedule_weekday)
    window.cmb_schedule_weekday = QComboBox()
    window.cmb_schedule_weekday.addItem(strings.tr("term_weekday_mon"), 0)
    window.cmb_schedule_weekday.addItem(strings.tr("term_weekday_tue"), 1)
    window.cmb_schedule_weekday.addItem(strings.tr("term_weekday_wed"), 2)
    window.cmb_schedule_weekday.addItem(strings.tr("term_weekday_thu"), 3)
    window.cmb_schedule_weekday.addItem(strings.tr("term_weekday_fri"), 4)
    window.cmb_schedule_weekday.addItem(strings.tr("term_weekday_sat"), 5)
    window.cmb_schedule_weekday.addItem(strings.tr("term_weekday_sun"), 6)
    row_s1.addWidget(window.cmb_schedule_weekday)
    row_s1.addStretch()
    schedule_layout.addLayout(row_s1)

    row_s2 = QHBoxLayout()
    row_s2.setSpacing(SPACING_MD)
    window.lbl_schedule_time = QLabel(strings.tr("settings_schedule_time"))
    row_s2.addWidget(window.lbl_schedule_time)
    window.txt_schedule_time = QLineEdit()
    window.txt_schedule_time.setPlaceholderText("03:00")
    window.txt_schedule_time.setMaximumWidth(120)
    row_s2.addWidget(window.txt_schedule_time)

    window.chk_schedule_export_json = QCheckBox(strings.tr("settings_schedule_export_json"))
    row_s2.addWidget(window.chk_schedule_export_json)
    window.chk_schedule_export_csv = QCheckBox(strings.tr("settings_schedule_export_csv"))
    row_s2.addWidget(window.chk_schedule_export_csv)
    row_s2.addStretch()
    schedule_layout.addLayout(row_s2)

    row_s3 = QHBoxLayout()
    row_s3.setSpacing(SPACING_MD)
    window.lbl_schedule_output = QLabel(strings.tr("settings_schedule_output"))
    row_s3.addWidget(window.lbl_schedule_output)
    window.txt_schedule_output = QLineEdit()
    window.txt_schedule_output.setPlaceholderText(strings.tr("settings_schedule_output"))
    row_s3.addWidget(window.txt_schedule_output, 1)
    window.btn_schedule_pick = QPushButton(strings.tr("btn_choose_folder"))
    window.btn_schedule_pick.clicked.connect(window.choose_schedule_output_folder)
    row_s3.addWidget(window.btn_schedule_pick)
    schedule_layout.addLayout(row_s3)

    row_s4 = QHBoxLayout()
    row_s4.setSpacing(SPACING_MD)
    window.lbl_schedule_job_name = QLabel(strings.tr("settings_schedule_job_name"))
    row_s4.addWidget(window.lbl_schedule_job_name)
    window.txt_schedule_job_name = QLineEdit()
    window.txt_schedule_job_name.setPlaceholderText(strings.tr("ph_schedule_job_name"))
    row_s4.addWidget(window.txt_schedule_job_name, 1)

    window.btn_schedule_new = QPushButton(strings.tr("btn_schedule_new"))
    window.btn_schedule_new.clicked.connect(window.prepare_new_schedule_job)
    row_s4.addWidget(window.btn_schedule_new)
    window.btn_schedule_run_now = QPushButton(strings.tr("btn_schedule_run_now"))
    window.btn_schedule_run_now.clicked.connect(window.run_selected_schedule_job_now)
    row_s4.addWidget(window.btn_schedule_run_now)
    schedule_layout.addLayout(row_s4)

    window.tbl_schedule_jobs = QTableWidget()
    window.tbl_schedule_jobs.setColumnCount(5)
    window.tbl_schedule_jobs.setHorizontalHeaderLabels(
        [
            strings.tr("col_job_name"),
            strings.tr("col_status"),
            strings.tr("settings_schedule_frequency"),
            strings.tr("settings_schedule_time"),
            strings.tr("col_next_run"),
        ]
    )
    shdr = window.tbl_schedule_jobs.horizontalHeader()
    shdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    shdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    shdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    shdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    shdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    window.tbl_schedule_jobs.setColumnWidth(1, 110)
    window.tbl_schedule_jobs.setColumnWidth(2, 110)
    window.tbl_schedule_jobs.setColumnWidth(3, 90)
    window.tbl_schedule_jobs.setColumnWidth(4, 170)
    window.tbl_schedule_jobs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    window.tbl_schedule_jobs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    window.tbl_schedule_jobs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    window.tbl_schedule_jobs.itemSelectionChanged.connect(window.on_schedule_job_selection_changed)
    window.tbl_schedule_jobs.setMinimumHeight(150)
    schedule_layout.addWidget(window.tbl_schedule_jobs)

    row_s5 = QHBoxLayout()
    row_s5.setSpacing(SPACING_MD)
    window.btn_schedule_refresh = QPushButton(strings.tr("btn_refresh"))
    window.btn_schedule_refresh.clicked.connect(window.refresh_schedule_jobs_view)
    row_s5.addWidget(window.btn_schedule_refresh)
    window.btn_schedule_delete = QPushButton(strings.tr("btn_delete"))
    window.btn_schedule_delete.clicked.connect(window.delete_selected_schedule_job)
    row_s5.addWidget(window.btn_schedule_delete)
    row_s5.addStretch()
    schedule_layout.addLayout(row_s5)

    window.lbl_schedule_runs = QLabel(strings.tr("settings_schedule_runs"))
    window.lbl_schedule_runs.setObjectName("card_desc")
    schedule_layout.addWidget(window.lbl_schedule_runs)

    window.tbl_schedule_runs = QTableWidget()
    window.tbl_schedule_runs.setColumnCount(8)
    window.tbl_schedule_runs.setHorizontalHeaderLabels(
        [
            strings.tr("col_created"),
            strings.tr("col_status"),
            strings.tr("col_groups"),
            strings.tr("col_files"),
            strings.tr("col_missing_folders"),
            strings.tr("col_export_failed"),
            strings.tr("col_watch_events"),
            strings.tr("col_message"),
        ]
    )
    rhdr = window.tbl_schedule_runs.horizontalHeader()
    rhdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    rhdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    rhdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    rhdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    rhdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    rhdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
    rhdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
    rhdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
    window.tbl_schedule_runs.setColumnWidth(0, 170)
    window.tbl_schedule_runs.setColumnWidth(1, 110)
    window.tbl_schedule_runs.setColumnWidth(2, 80)
    window.tbl_schedule_runs.setColumnWidth(3, 80)
    window.tbl_schedule_runs.setColumnWidth(4, 110)
    window.tbl_schedule_runs.setColumnWidth(5, 110)
    window.tbl_schedule_runs.setColumnWidth(6, 100)
    window.tbl_schedule_runs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    window.tbl_schedule_runs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    window.tbl_schedule_runs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    window.tbl_schedule_runs.setMinimumHeight(140)
    schedule_layout.addWidget(window.tbl_schedule_runs)

    window.btn_schedule_apply = QPushButton(strings.tr("btn_apply"))
    window.btn_schedule_apply.clicked.connect(window.apply_schedule_settings)
    schedule_layout.addWidget(window.btn_schedule_apply)
    settings_layout.addWidget(schedule_settings)

    settings_layout.addStretch()
    return page
