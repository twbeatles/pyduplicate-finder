from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from src.utils.i18n import strings


def _build_metric_card(window, title_key: str, value_attr: str, hint_key: str) -> QWidget:
    card = QFrame()
    card.setObjectName("folder_card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)

    title = QLabel(strings.tr(title_key))
    title.setObjectName("card_desc")
    layout.addWidget(title)

    value = QLabel("0")
    value.setObjectName("page_title")
    setattr(window, value_attr, value)
    layout.addWidget(value)

    hint = QLabel(strings.tr(hint_key))
    hint.setWordWrap(True)
    hint.setObjectName("card_desc")
    layout.addWidget(hint)
    return card


def build_insights_page(window) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setSpacing(16)
    layout.setContentsMargins(16, 12, 16, 12)

    header = QHBoxLayout()
    header.setSpacing(8)
    window.lbl_insights_title = QLabel(strings.tr("nav_insights"))
    window.lbl_insights_title.setObjectName("page_title")
    header.addWidget(window.lbl_insights_title)

    header.addStretch()

    window.btn_insights_refresh = QPushButton(strings.tr("btn_refresh"))
    window.btn_insights_refresh.setMinimumHeight(38)
    window.btn_insights_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
    window.btn_insights_refresh.clicked.connect(window.refresh_insights_page)
    header.addWidget(window.btn_insights_refresh)
    layout.addLayout(header)

    window.lbl_insights_hint = QLabel(strings.tr("msg_insights_page_hint"))
    window.lbl_insights_hint.setObjectName("card_desc")
    window.lbl_insights_hint.setWordWrap(True)
    layout.addWidget(window.lbl_insights_hint)

    cards = QHBoxLayout()
    cards.setSpacing(12)
    cards.addWidget(_build_metric_card(window, "insight_scans_title", "lbl_insight_scans_value", "insight_scans_hint"))
    cards.addWidget(_build_metric_card(window, "insight_savings_title", "lbl_insight_savings_value", "insight_savings_hint"))
    cards.addWidget(_build_metric_card(window, "insight_fail_rate_title", "lbl_insight_fail_rate_value", "insight_fail_rate_hint"))
    cards.addWidget(_build_metric_card(window, "insight_quarantine_title", "lbl_insight_quarantine_value", "insight_quarantine_hint"))
    layout.addLayout(cards)

    sessions_card = QFrame()
    sessions_card.setObjectName("folder_card")
    sessions_layout = QVBoxLayout(sessions_card)
    sessions_layout.setContentsMargins(18, 16, 18, 16)
    sessions_layout.setSpacing(10)

    window.lbl_insights_sessions_title = QLabel(strings.tr("insight_sessions_title"))
    window.lbl_insights_sessions_title.setObjectName("card_title")
    sessions_layout.addWidget(window.lbl_insights_sessions_title)

    window.tbl_insight_sessions = QTableWidget()
    window.tbl_insight_sessions.setColumnCount(6)
    window.tbl_insight_sessions.setHorizontalHeaderLabels(
        [
            strings.tr("col_id"),
            strings.tr("col_created"),
            strings.tr("col_status"),
            strings.tr("col_groups"),
            strings.tr("col_watch_events"),
            strings.tr("col_message"),
        ]
    )
    session_header = window.tbl_insight_sessions.horizontalHeader()
    session_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    session_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    session_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    session_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    session_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    session_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
    window.tbl_insight_sessions.setColumnWidth(0, 80)
    window.tbl_insight_sessions.setColumnWidth(1, 170)
    window.tbl_insight_sessions.setColumnWidth(2, 110)
    window.tbl_insight_sessions.setColumnWidth(3, 90)
    window.tbl_insight_sessions.setColumnWidth(4, 100)
    window.tbl_insight_sessions.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    window.tbl_insight_sessions.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    window.tbl_insight_sessions.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    window.tbl_insight_sessions.setMinimumHeight(180)
    sessions_layout.addWidget(window.tbl_insight_sessions)

    layout.addWidget(sessions_card)

    jobs_card = QFrame()
    jobs_card.setObjectName("folder_card")
    jobs_layout = QVBoxLayout(jobs_card)
    jobs_layout.setContentsMargins(18, 16, 18, 16)
    jobs_layout.setSpacing(10)

    window.lbl_insights_jobs_title = QLabel(strings.tr("insight_jobs_title"))
    window.lbl_insights_jobs_title.setObjectName("card_title")
    jobs_layout.addWidget(window.lbl_insights_jobs_title)

    window.tbl_insight_jobs = QTableWidget()
    window.tbl_insight_jobs.setColumnCount(9)
    window.tbl_insight_jobs.setHorizontalHeaderLabels(
        [
            strings.tr("col_created"),
            strings.tr("col_job_name"),
            strings.tr("col_status"),
            strings.tr("col_groups"),
            strings.tr("col_files"),
            strings.tr("col_missing_folders"),
            strings.tr("col_export_failed"),
            strings.tr("col_watch_events"),
            strings.tr("col_message"),
        ]
    )
    job_header = window.tbl_insight_jobs.horizontalHeader()
    job_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    job_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    job_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    job_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    job_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    job_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
    job_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
    job_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
    job_header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
    window.tbl_insight_jobs.setColumnWidth(0, 170)
    window.tbl_insight_jobs.setColumnWidth(1, 150)
    window.tbl_insight_jobs.setColumnWidth(2, 110)
    window.tbl_insight_jobs.setColumnWidth(3, 90)
    window.tbl_insight_jobs.setColumnWidth(4, 90)
    window.tbl_insight_jobs.setColumnWidth(5, 110)
    window.tbl_insight_jobs.setColumnWidth(6, 110)
    window.tbl_insight_jobs.setColumnWidth(7, 100)
    window.tbl_insight_jobs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    window.tbl_insight_jobs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    window.tbl_insight_jobs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    window.tbl_insight_jobs.setMinimumHeight(180)
    jobs_layout.addWidget(window.tbl_insight_jobs)

    layout.addWidget(jobs_card)
    layout.addStretch()
    return page
