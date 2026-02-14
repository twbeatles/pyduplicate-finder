import os

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QSpinBox,
    QLineEdit,
)
from PySide6.QtCore import Qt

from src.utils.i18n import strings


def build_settings_page(window) -> QWidget:
    page = QWidget()
    settings_layout = QVBoxLayout(page)
    settings_layout.setSpacing(16)
    settings_layout.setContentsMargins(16, 12, 16, 12)

    window.lbl_settings_title = QLabel(strings.tr("nav_settings"))
    window.lbl_settings_title.setObjectName("page_title")
    settings_layout.addWidget(window.lbl_settings_title)

    window.lbl_settings_hint = QLabel(strings.tr("msg_settings_page_hint"))
    window.lbl_settings_hint.setObjectName("card_desc")
    window.lbl_settings_hint.setWordWrap(True)
    settings_layout.addWidget(window.lbl_settings_hint)

    # Theme card
    theme_card = QWidget()
    theme_card.setObjectName("folder_card")
    theme_card_layout = QVBoxLayout(theme_card)
    theme_card_layout.setContentsMargins(20, 16, 20, 16)
    theme_card_layout.setSpacing(12)

    window.lbl_theme_title = QLabel(strings.tr("action_theme"))
    window.lbl_theme_title.setObjectName("card_title")
    theme_card_layout.addWidget(window.lbl_theme_title)

    window.btn_theme_settings = QPushButton(strings.tr("action_theme"))
    window.btn_theme_settings.setCheckable(True)
    window.btn_theme_settings.setMinimumHeight(44)
    window.btn_theme_settings.setCursor(Qt.PointingHandCursor)
    window.btn_theme_settings.clicked.connect(window.toggle_theme)
    theme_card_layout.addWidget(window.btn_theme_settings)
    settings_layout.addWidget(theme_card)

    # Shortcuts card
    shortcut_card = QWidget()
    shortcut_card.setObjectName("folder_card")
    shortcut_card_layout = QVBoxLayout(shortcut_card)
    shortcut_card_layout.setContentsMargins(20, 16, 20, 16)
    shortcut_card_layout.setSpacing(12)

    window.lbl_shortcut_title = QLabel(strings.tr("action_shortcut_settings"))
    window.lbl_shortcut_title.setObjectName("card_title")
    shortcut_card_layout.addWidget(window.lbl_shortcut_title)

    window.btn_shortcuts_settings = QPushButton(strings.tr("action_shortcut_settings"))
    window.btn_shortcuts_settings.setMinimumHeight(44)
    window.btn_shortcuts_settings.setCursor(Qt.PointingHandCursor)
    window.btn_shortcuts_settings.clicked.connect(window.open_shortcut_settings)
    shortcut_card_layout.addWidget(window.btn_shortcuts_settings)
    settings_layout.addWidget(shortcut_card)

    # Presets card
    preset_card = QWidget()
    preset_card.setObjectName("folder_card")
    preset_card_layout = QVBoxLayout(preset_card)
    preset_card_layout.setContentsMargins(20, 16, 20, 16)
    preset_card_layout.setSpacing(12)

    window.lbl_preset_title = QLabel(strings.tr("action_preset"))
    window.lbl_preset_title.setObjectName("card_title")
    preset_card_layout.addWidget(window.lbl_preset_title)

    window.btn_preset_settings = QPushButton(strings.tr("btn_manage_presets"))
    window.btn_preset_settings.setMinimumHeight(44)
    window.btn_preset_settings.setCursor(Qt.PointingHandCursor)
    window.btn_preset_settings.clicked.connect(window.open_preset_dialog)
    preset_card_layout.addWidget(window.btn_preset_settings)
    settings_layout.addWidget(preset_card)

    # Cache DB card
    cache_card = QWidget()
    cache_card.setObjectName("folder_card")
    cache_layout = QVBoxLayout(cache_card)
    cache_layout.setContentsMargins(20, 16, 20, 16)
    cache_layout.setSpacing(12)

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
    row.setSpacing(8)
    window.btn_cache_open = QPushButton(strings.tr("ctx_open_folder"))
    window.btn_cache_open.clicked.connect(window.open_cache_db_folder)
    row.addWidget(window.btn_cache_open)
    window.btn_cache_copy = QPushButton(strings.tr("ctx_copy_path"))
    window.btn_cache_copy.clicked.connect(window.copy_cache_db_path)
    row.addWidget(window.btn_cache_copy)
    row.addStretch()
    cache_layout.addLayout(row)

    settings_layout.addWidget(cache_card)

    # Quarantine settings card
    quarantine_settings = QWidget()
    quarantine_settings.setObjectName("folder_card")
    quarantine_settings_layout = QVBoxLayout(quarantine_settings)
    quarantine_settings_layout.setContentsMargins(20, 16, 20, 16)
    quarantine_settings_layout.setSpacing(12)

    window.lbl_quarantine_settings_title = QLabel(strings.tr("settings_quarantine_title"))
    window.lbl_quarantine_settings_title.setObjectName("card_title")
    quarantine_settings_layout.addWidget(window.lbl_quarantine_settings_title)

    window.chk_quarantine_enabled = QCheckBox(strings.tr("settings_quarantine_enabled"))
    quarantine_settings_layout.addWidget(window.chk_quarantine_enabled)

    row_q = QHBoxLayout()
    row_q.setSpacing(12)
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
    row_q2.setSpacing(8)
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
    hardlink_settings = QWidget()
    hardlink_settings.setObjectName("folder_card")
    hardlink_settings_layout = QVBoxLayout(hardlink_settings)
    hardlink_settings_layout.setContentsMargins(20, 16, 20, 16)
    hardlink_settings_layout.setSpacing(12)

    window.lbl_hardlink_title = QLabel(strings.tr("settings_hardlink_title"))
    window.lbl_hardlink_title.setObjectName("card_title")
    hardlink_settings_layout.addWidget(window.lbl_hardlink_title)

    window.chk_enable_hardlink = QCheckBox(strings.tr("settings_hardlink_enabled"))
    window.chk_enable_hardlink.toggled.connect(window._sync_advanced_visibility)
    hardlink_settings_layout.addWidget(window.chk_enable_hardlink)

    settings_layout.addWidget(hardlink_settings)

    settings_layout.addStretch()
    return page
