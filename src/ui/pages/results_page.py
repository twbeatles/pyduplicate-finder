from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QSplitter,
    QTextEdit,
    QScrollArea,
    QToolButton,
    QMenu,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from src.utils.i18n import strings
from src.ui.components.results_tree import ResultsTreeWidget


def build_results_page(window) -> QWidget:
    """
    Build Results page (review + selection + delete/export).

    Assigns widgets to the main window instance for backward-compatible logic.
    """
    page = QWidget()
    results_layout = QVBoxLayout(page)
    results_layout.setSpacing(12)
    results_layout.setContentsMargins(16, 12, 16, 12)

    # === Results Splitter: Tree | Preview ===
    window.splitter = QSplitter(Qt.Horizontal)
    window.splitter.setHandleWidth(12)

    # [Left] Tree Widget Container
    window.tree_container = QWidget()
    window.tree_container.setObjectName("result_card")
    tree_layout = QVBoxLayout(window.tree_container)
    tree_layout.setContentsMargins(12, 12, 12, 12)
    tree_layout.setSpacing(8)

    # Results header
    results_header = QHBoxLayout()
    results_header.setSpacing(8)
    window.lbl_results_title = QLabel(strings.tr("nav_results"))
    window.lbl_results_title.setObjectName("results_title")
    window.lbl_results_meta = QLabel("")
    window.lbl_results_meta.setObjectName("results_meta")
    results_header.addWidget(window.lbl_results_title)
    results_header.addStretch()

    # Quick link back to Scan options.
    window.btn_show_options = QPushButton(strings.tr("btn_show_options"))
    window.btn_show_options.setMinimumHeight(28)
    window.btn_show_options.setCursor(Qt.PointingHandCursor)
    window.btn_show_options.setObjectName("btn_icon")
    window.btn_show_options.clicked.connect(lambda: window._navigate_to("scan"))
    results_header.addWidget(window.btn_show_options)
    results_header.addWidget(window.lbl_results_meta)
    tree_layout.addLayout(results_header)

    # Filter input
    filter_row = QHBoxLayout()
    window.txt_result_filter = QLineEdit()
    window.txt_result_filter.setPlaceholderText("🔍 " + strings.tr("ph_filter_results"))
    window.txt_result_filter.setClearButtonEnabled(True)
    window.txt_result_filter.textChanged.connect(window.filter_results_tree)
    filter_row.addWidget(window.txt_result_filter)
    filter_row.addStretch()
    window.lbl_filter_count = QLabel("")
    window.lbl_filter_count.setObjectName("filter_count")
    filter_row.addWidget(window.lbl_filter_count)
    tree_layout.addLayout(filter_row)

    # Tree widget + empty stack
    window.tree_widget = ResultsTreeWidget()
    window.tree_widget.itemDoubleClicked.connect(window.open_file)
    window.tree_widget.currentItemChanged.connect(window.update_preview)
    window.tree_widget.customContextMenuRequested.connect(window.show_context_menu)
    window.tree_widget.files_checked.connect(window.on_checked_files_changed)

    from PySide6.QtWidgets import QStackedWidget

    window.results_stack = QStackedWidget()
    window.results_stack.setObjectName("results_stack")

    empty_wrap = QWidget()
    empty_layout = QVBoxLayout(empty_wrap)
    empty_layout.setContentsMargins(24, 24, 24, 24)
    window.lbl_results_empty = QLabel("\n📂\n\n" + strings.tr("msg_no_results"))
    window.lbl_results_empty.setAlignment(Qt.AlignCenter)
    window.lbl_results_empty.setWordWrap(True)
    window.lbl_results_empty.setObjectName("empty_state")
    empty_layout.addStretch()
    empty_layout.addWidget(window.lbl_results_empty)

    # Empty-state CTAs
    empty_btn_row = QHBoxLayout()
    empty_btn_row.setSpacing(10)
    window.btn_results_empty_add_folder = QPushButton(strings.tr("btn_add_folder"))
    window.btn_results_empty_add_folder.setMinimumHeight(40)
    window.btn_results_empty_add_folder.setCursor(Qt.PointingHandCursor)
    window.btn_results_empty_add_folder.clicked.connect(lambda: window._navigate_to("scan"))
    empty_btn_row.addWidget(window.btn_results_empty_add_folder)

    window.btn_results_empty_start_scan = QPushButton(strings.tr("btn_start_scan"))
    window.btn_results_empty_start_scan.setMinimumHeight(40)
    window.btn_results_empty_start_scan.setCursor(Qt.PointingHandCursor)
    window.btn_results_empty_start_scan.setObjectName("btn_primary")
    window.btn_results_empty_start_scan.clicked.connect(lambda: window._navigate_to("scan"))
    empty_btn_row.addWidget(window.btn_results_empty_start_scan)
    empty_layout.addLayout(empty_btn_row)
    empty_layout.addStretch()

    window.results_stack.addWidget(empty_wrap)
    window.results_stack.addWidget(window.tree_widget)
    tree_layout.addWidget(window.results_stack, 1)

    window.splitter.addWidget(window.tree_container)

    # [Right] Preview panel
    window.preview_container = QWidget()
    window.preview_container.setObjectName("preview_card")
    preview_layout = QVBoxLayout(window.preview_container)
    preview_layout.setContentsMargins(0, 0, 0, 0)
    preview_layout.setSpacing(0)

    window.lbl_preview_header = QLabel(strings.tr("lbl_preview"))
    window.lbl_preview_header.setAlignment(Qt.AlignCenter)
    window.lbl_preview_header.setObjectName("preview_header")
    preview_layout.addWidget(window.lbl_preview_header)

    window.preview_info = QWidget()
    window.preview_info.setObjectName("preview_info")
    info_layout = QVBoxLayout(window.preview_info)
    info_layout.setContentsMargins(16, 12, 16, 12)
    info_layout.setSpacing(4)

    window.lbl_preview_name = QLabel("")
    window.lbl_preview_name.setObjectName("preview_name")
    window.lbl_preview_path = QLabel("")
    window.lbl_preview_path.setObjectName("preview_path")
    window.lbl_preview_path.setWordWrap(True)
    window.lbl_preview_meta = QLabel("")
    window.lbl_preview_meta.setObjectName("preview_meta")

    info_layout.addWidget(window.lbl_preview_name)
    info_layout.addWidget(window.lbl_preview_path)
    info_layout.addWidget(window.lbl_preview_meta)
    preview_layout.addWidget(window.preview_info)
    window.preview_info.hide()

    window.preview_scroll = QScrollArea()
    window.preview_scroll.setWidgetResizable(True)
    window.preview_scroll.setFrameShape(QScrollArea.NoFrame)

    scroll_content = QWidget()
    scroll_content.setObjectName("preview_content")
    scroll_layout = QVBoxLayout(scroll_content)
    scroll_layout.setContentsMargins(16, 16, 16, 16)
    scroll_layout.setSpacing(12)

    window.lbl_image_preview = QLabel()
    window.lbl_image_preview.setAlignment(Qt.AlignCenter)
    window.lbl_image_preview.hide()
    scroll_layout.addWidget(window.lbl_image_preview)

    window.txt_text_preview = QTextEdit()
    window.txt_text_preview.setReadOnly(True)
    window.txt_text_preview.hide()
    scroll_layout.addWidget(window.txt_text_preview)

    window.lbl_info_preview = QLabel(strings.tr("msg_select_file"))
    window.lbl_info_preview.setAlignment(Qt.AlignCenter)
    window.lbl_info_preview.setWordWrap(True)
    window.lbl_info_preview.setObjectName("preview_placeholder")
    scroll_layout.addWidget(window.lbl_info_preview)

    scroll_layout.addStretch()
    window.preview_scroll.setWidget(scroll_content)
    preview_layout.addWidget(window.preview_scroll, 1)

    window.splitter.addWidget(window.preview_container)
    window.splitter.setSizes([700, 400])
    window.splitter.setCollapsible(0, False)
    window.splitter.setCollapsible(1, True)

    results_layout.addWidget(window.splitter, 1)

    # === Action bar (bottom) ===
    window.action_bar = QWidget()
    window.action_bar.setObjectName("action_bar")
    bottom_layout = QHBoxLayout(window.action_bar)
    bottom_layout.setSpacing(12)
    bottom_layout.setContentsMargins(16, 8, 16, 8)

    window.btn_select_smart = QToolButton()
    window.btn_select_smart.setText(strings.tr("btn_smart_select"))
    window.btn_select_smart.setToolTip(strings.tr("tip_smart_select"))
    window.btn_select_smart.setMinimumHeight(44)
    window.btn_select_smart.setObjectName("btn_secondary")
    window.btn_select_smart.setCursor(Qt.PointingHandCursor)
    window.btn_select_smart.setPopupMode(QToolButton.MenuButtonPopup)
    window.btn_select_smart.clicked.connect(window.select_duplicates_smart)

    window.menu_smart_select = QMenu(window)
    window.action_smart = QAction(strings.tr("btn_smart_select"), window)
    window.action_smart.triggered.connect(window.select_duplicates_smart)
    window.menu_smart_select.addAction(window.action_smart)
    window.menu_smart_select.addSeparator()

    window.action_newest = QAction(strings.tr("action_select_newest"), window)
    window.action_newest.setToolTip(strings.tr("tip_select_newest"))
    window.action_newest.triggered.connect(window.select_duplicates_newest)
    window.menu_smart_select.addAction(window.action_newest)

    window.action_oldest = QAction(strings.tr("action_select_oldest"), window)
    window.action_oldest.setToolTip(strings.tr("tip_select_oldest"))
    window.action_oldest.triggered.connect(window.select_duplicates_oldest)
    window.menu_smart_select.addAction(window.action_oldest)
    window.menu_smart_select.addSeparator()

    window.action_pattern = QAction(strings.tr("action_select_pattern"), window)
    window.action_pattern.triggered.connect(window.select_duplicates_by_pattern)
    window.menu_smart_select.addAction(window.action_pattern)

    window.btn_select_smart.setMenu(window.menu_smart_select)

    window.btn_select_rules = QPushButton(strings.tr("btn_auto_select_rules"))
    window.btn_select_rules.setMinimumHeight(44)
    window.btn_select_rules.setCursor(Qt.PointingHandCursor)
    window.btn_select_rules.setObjectName("btn_secondary")
    window.btn_select_rules.clicked.connect(window.select_duplicates_by_rules)

    window.btn_export = QPushButton(strings.tr("btn_export"))
    window.btn_export.setMinimumHeight(44)
    window.btn_export.setCursor(Qt.PointingHandCursor)
    window.btn_export.clicked.connect(window.export_results)

    window.btn_delete = QPushButton(strings.tr("btn_delete_selected"))
    window.btn_delete.setObjectName("btn_danger")
    window.btn_delete.setMinimumHeight(44)
    window.btn_delete.setCursor(Qt.PointingHandCursor)
    window.btn_delete.clicked.connect(window.delete_selected_files)

    bottom_layout.addWidget(window.btn_select_smart)
    bottom_layout.addWidget(window.btn_select_rules)
    bottom_layout.addWidget(window.btn_export)

    window.lbl_action_meta = QLabel("")
    window.lbl_action_meta.setObjectName("filter_count")
    bottom_layout.addWidget(window.lbl_action_meta)

    bottom_layout.addStretch()
    bottom_layout.addWidget(window.btn_delete)
    results_layout.addWidget(window.action_bar, 0)

    # Default state
    window._set_results_view(False)
    window._update_results_summary(0)

    return page
