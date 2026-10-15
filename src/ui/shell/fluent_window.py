"""Fluent 셸 (경로 A, 사용자 승인 2026-10-15).

KTrain ``ktrain/gui/main_window.py`` 와 같은 계열의 최상위 셸이다:
``MSFluentWindow`` (미지원 시 ``FluentWindow``) + ``addSubInterface``,
상단 4개 + 하단 고정 설정, 1100x800/최소 640x560 + 가용영역 clamp,
``InfoBar``/``MessageBox`` 알림, 스캔 중 탭 전환 가드·종료 확인.
철도 예매 전용 구조·용어는 이식하지 않는다.

``QMainWindow`` 이중 상속 금지 규칙을 지키기 위해, 본 셸은
``DuplicateFinderApp`` 을 상속하지 않고 동일한 mixin 조합 +
``MSFluentWindow`` 를 기반으로 하며, 검증된 ``_init_core`` 부팅을
그대로 재사용한다. 페이지 빌더·컨트롤러·설정 키는 레거지와 공유하므로
기능·데이터 계약이 그대로 유지된다.
"""

from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.ui.controllers.navigation_controller import NavigationController
from src.ui.design_system.tokens import BRAND_PRIMARY
from src.ui.main_window import DuplicateFinderApp
from src.ui.main_window_parts.results_flow import MainWindowResultsFlowMixin
from src.ui.main_window_parts.scan_flow import MainWindowScanFlowMixin
from src.ui.main_window_parts.schedule_flow import MainWindowScheduleFlowMixin
from src.ui.main_window_parts.settings_flow import MainWindowSettingsFlowMixin
from src.ui.main_window_parts.tools_flow import MainWindowToolsFlowMixin
from src.ui.main_window_parts.ui_shell import MainWindowUiShellMixin
from src.ui.pages.insights_page import build_insights_page
from src.ui.pages.results_page import build_results_page
from src.ui.pages.scan_page import build_scan_page
from src.ui.pages.settings_page import build_settings_page
from src.ui.pages.tools_page import build_tools_page
from src.ui.shell.view_state import (
    horizontal_split_sizes,
    needed_horizontal_width,
    orientation_for_width,
    preferred_window_size,
    vertical_split_sizes,
)
from src.utils.i18n import strings

try:
    from qfluentwidgets import (
        FluentIcon as FIF,
        InfoBar,
        InfoBarPosition,
        MessageBox,
        NavigationItemPosition,
        Theme,
        setTheme,
        setThemeColor,
    )
except ImportError as _fluent_import_error:  # pragma: no cover - import gate
    FIF = None  # type: ignore[assignment]
    InfoBar = None  # type: ignore[assignment]
    InfoBarPosition = None  # type: ignore[assignment]
    MessageBox = None  # type: ignore[assignment]
    NavigationItemPosition = None  # type: ignore[assignment]
    Theme = None  # type: ignore[assignment]
    setTheme = None  # type: ignore[assignment]
    setThemeColor = None  # type: ignore[assignment]
    _FLUENT_IMPORT_ERROR = _fluent_import_error
else:
    _FLUENT_IMPORT_ERROR = None

try:
    from qfluentwidgets import MSFluentWindow
except ImportError:
    try:
        from qfluentwidgets import FluentWindow as MSFluentWindow  # type: ignore[no-redef]
    except ImportError:
        MSFluentWindow = None  # type: ignore[assignment]

#: 셸 네비게이션 순서 + 아이콘 + 라벨 키 (레거시 Sidebar.NAV_ITEMS/BOTTOM_ITEMS 대응).
FLUENT_NAV = (
    ("scan", "SCAN_ICON", "nav_scan", False),
    ("results", "RESULTS_ICON", "nav_results", False),
    ("tools", "TOOLS_ICON", "nav_tools", False),
    ("insights", "INSIGHTS_ICON", "nav_insights", False),
    ("settings", "SETTINGS_ICON", "nav_settings", True),
)

_NAV_ICONS = {
    "SCAN_ICON": "SEARCH",
    "RESULTS_ICON": "FOLDER",
    "TOOLS_ICON": "SYNC",
    "INSIGHTS_ICON": "DOCUMENT",
    "SETTINGS_ICON": "SETTING",
}

#: 인터페이스 objectName (테스트·디버깅용 고정 식별자).
INTERFACE_NAMES = {
    "scan": "scanInterface",
    "results": "resultsInterface",
    "tools": "toolsInterface",
    "insights": "insightsInterface",
    "settings": "settingsInterface",
}


def _require_fluent() -> None:
    if MSFluentWindow is None or FIF is None:
        print(
            "Fluent 셸에 필요한 패키지가 설치되지 않았습니다.\n"
            "  누락: PySide6-Fluent-Widgets\n\n"
            "설치:\n"
            "  pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1)


class FluentDuplicateFinderApp(
    MainWindowUiShellMixin,
    MainWindowScanFlowMixin,
    MainWindowResultsFlowMixin,
    MainWindowSettingsFlowMixin,
    MainWindowScheduleFlowMixin,
    MainWindowToolsFlowMixin,
    MSFluentWindow,
):
    """MSFluentWindow 기반 최상위 셸 (동작 코드는 mixin·컨트롤러 공유)."""

    # Static helpers owned by DuplicateFinderApp (no QMainWindow dependency).
    @staticmethod
    def _create_settings():
        return DuplicateFinderApp._create_settings()

    @staticmethod
    def _to_int(value, default=0):
        return DuplicateFinderApp._to_int(value, default)

    @staticmethod
    def _to_float(value, default=0.0):
        return DuplicateFinderApp._to_float(value, default)

    @staticmethod
    def _json_loads(value, default):
        return DuplicateFinderApp._json_loads(value, default)

    def __init__(self) -> None:
        _require_fluent()
        super().__init__()
        mica = getattr(self, "setMicaEffectEnabled", None)
        if callable(mica):
            try:
                mica(False)
            except Exception:
                pass
        setThemeColor(BRAND_PRIMARY)
        self.setWindowTitle(strings.tr("app_title"))
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else None
        width, height = preferred_window_size(
            avail.width() if avail is not None else 1100,
            avail.height() if avail is not None else 800,
        )
        self.resize(width, height)
        self.setMinimumSize(min(640, width), min(560, height))
        # 검증된 레거지 부팅 재사용 (init_ui/create_toolbar/apply_theme는
        # 아래 Fluent 오버라이드가 다형적으로 호출된다).
        DuplicateFinderApp._init_core(self)
        self._guard_navigation_during_scan()

    # -- Fluent 셸 후크 -------------------------------------------------

    def init_ui(self: Any) -> None:
        builders = {
            "scan": build_scan_page,
            "results": build_results_page,
            "tools": build_tools_page,
            "insights": build_insights_page,
            "settings": build_settings_page,
        }
        self._fluent_interfaces = {}
        for key, _icon, label_key, bottom in FLUENT_NAV:
            page = builders[key](self)
            if key != "results":
                scroll = QScrollArea(self)
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.Shape.NoFrame)
                scroll.setWidget(page)
                interface = scroll
            else:
                interface = page
            interface.setObjectName(INTERFACE_NAMES[key])
            setattr(self, f"{key}_page", page)
            setattr(self, f"{key}_interface", interface)
            self._fluent_interfaces[key] = interface
            kwargs = {"position": NavigationItemPosition.BOTTOM} if bottom else {}
            self.addSubInterface(
                interface,
                getattr(FIF, _NAV_ICONS[_icon]),
                strings.tr(label_key),
                **kwargs,
            )

        # 레거시와 동일한 상시 상태 스트립 (스캔 진행·상태 계약 유지).
        # FluentWindow에는 setStatusBar가 없으므로 루트 레이아웃을
        # 수직 구조로 재구성해 하단에 붙인다.
        status_strip = QWidget(self)
        strip_layout = QHBoxLayout(status_strip)
        strip_layout.setContentsMargins(16, 8, 16, 8)
        strip_layout.setSpacing(8)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumWidth(200)
        self.progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.status_label = QLabel(strings.tr("status_ready"))
        self.status_label.setObjectName("status_label")
        strip_layout.addWidget(self.progress_bar)
        strip_layout.addWidget(self.status_label, 1)
        self._attach_status_strip(status_strip)

        if hasattr(self, "chk_schedule_enabled"):
            self.chk_schedule_enabled.toggled.connect(self._sync_schedule_ui)
        if hasattr(self, "cmb_schedule_frequency"):
            self.cmb_schedule_frequency.currentIndexChanged.connect(
                self._sync_schedule_ui
            )

    def addToolBar(self: Any, toolbar) -> None:  # noqa: N802 (Qt-compatible shim)
        # FluentWindow has no toolbar areas: keep the bar as a hidden action
        # holder so every legacy command/shortcut stays functional.
        toolbar.setParent(self)
        toolbar.setVisible(False)

    def create_toolbar(self: Any) -> None:
        # 범용 툴바를 중복 노출하지 않고, 기존 실행 명령·단축키는 숨김
        # QAction으로 보존한다 (계획서 3.1.5).
        before = set(self.findChildren(QToolBar))
        MainWindowUiShellMixin.create_toolbar(self)
        for bar in self.findChildren(QToolBar):
            if bar not in before:
                bar.setVisible(False)

    def apply_theme(self: Any, theme_name: str) -> None:
        mode = "dark" if str(theme_name).lower() == "dark" else "light"
        setTheme(Theme.DARK if mode == "dark" else Theme.LIGHT)
        setThemeColor(BRAND_PRIMARY)
        self.settings.setValue("app/theme", mode)
        self.tree_widget.set_theme_mode(mode)
        if hasattr(self, "toast_manager") and self.toast_manager:
            try:
                self.toast_manager.set_theme_mode(mode)
            except Exception:
                pass
        if hasattr(self, "scan_notice_bar") and self.scan_notice_bar is not None:
            try:
                from contextlib import suppress

                with suppress(Exception):
                    self.scan_notice_bar.apply_mode(mode)
            except Exception:
                pass
        if hasattr(self, "action_theme"):
            self.action_theme.setChecked(mode == "dark")
        if hasattr(self, "btn_theme_settings"):
            self.btn_theme_settings.setChecked(mode == "dark")

    def _attach_status_strip(self: Any, strip: QWidget) -> None:
        """루트 수평 레이아웃을 내용 + 하단 스트립 구조로 바꾼다."""
        from shiboken6 import delete

        root = self.layout()
        content = QWidget(self)
        inner = QHBoxLayout(content)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        if root is not None:
            while root.count():
                item = root.takeAt(0)
                child = item.widget()
                if child is not None:
                    inner.addWidget(child)
                elif item.layout() is not None:
                    inner.addLayout(item.layout())
            delete(root)
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(content, 1)
        outer.addWidget(strip)
        self.setLayout(outer)

    # -- 내비게이션 (레거시 page_stack/sidebar 대신 Fluent switchTo) -----

    def _scan_running(self: Any) -> bool:
        btn = getattr(self, "btn_stop_scan", None)
        try:
            return bool(btn is not None and btn.isEnabled())
        except Exception:
            return False

    def _after_page_changed(self: Any, page_name: str) -> None:
        # NavigationController와 동일한 새로고침·상태 계약 (스택/사이드바 제외).
        try:
            if page_name == "tools":
                try:
                    self.refresh_quarantine_list()
                    self.refresh_operations_list()
                    self.refresh_exemption_list()
                except Exception:
                    pass
            elif page_name == "insights":
                try:
                    self.refresh_insights_page()
                except Exception:
                    pass
            label = strings.tr(
                NavigationController.PAGE_LABEL_KEYS.get(page_name, "")
            )
            if label and not self._scan_running():
                self.status_label.setText(label)
            if hasattr(self, "toast_manager") and self.toast_manager and label:
                self.toast_manager.info(label, duration=2000)
        except Exception:
            pass

    def _on_page_changed(self: Any, page_name: str) -> None:
        self._navigate_to(page_name)

    def _navigate_to(self: Any, page_name: str) -> None:
        interface = self._fluent_interfaces.get(page_name)
        if interface is not None:
            self._raw_switch_to(interface)
        self._after_page_changed(page_name)
        if page_name == "results":
            self._update_results_orientation()
            QTimer.singleShot(0, self._update_results_orientation)

    def _guard_navigation_during_scan(self: Any) -> None:
        """스캔 실행 중 탭 전환 방지 (KTrain 예매 중 가드와 같은 위치)."""
        self._raw_switch_to = self.switchTo

        def guarded_switch(interface) -> None:
            try:
                current = self.stackedWidget.currentWidget()
            except Exception:
                current = None
            if self._scan_running() and interface is not current:
                MessageBox(
                    strings.tr("msg_title_notice"),
                    strings.tr("msg_scan_running_no_nav"),
                    self,
                ).exec()
                return
            self._raw_switch_to(interface)

        self.switchTo = guarded_switch  # type: ignore[method-assign]

    def resizeEvent(self: Any, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._update_results_orientation()

    def showEvent(self: Any, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        # 첫 표시 시점에는 레이아웃 폭이 아직 확정되지 않을 수 있어 즉시 +
        # 지연 2회 갱신한다 (offscreen 포함).
        self._update_results_orientation()
        QTimer.singleShot(0, self._update_results_orientation)

    def _update_results_orientation(self: Any) -> None:
        """폭이 부족하면 결과 스플리터를 세로 배치로 전환한다 (KTrain과 동일 정책)."""
        splitter = getattr(self, "splitter", None)
        interface = self._fluent_interfaces.get("results")
        try:
            page_width = interface.width() if interface is not None else 0
        except Exception:
            return
        if splitter is None or page_width <= 0:
            return
        want = orientation_for_width(page_width, needed_horizontal_width())
        try:
            if want == "horizontal":
                if splitter.orientation() != Qt.Orientation.Horizontal:
                    splitter.setOrientation(Qt.Orientation.Horizontal)
                    splitter.setSizes(horizontal_split_sizes(page_width))
            else:
                if splitter.orientation() != Qt.Orientation.Vertical:
                    splitter.setOrientation(Qt.Orientation.Vertical)
                    page_height = interface.height() or 600
                    splitter.setSizes(vertical_split_sizes(page_height))
        except Exception:
            pass

    # -- 알림 · 종료 -----------------------------------------------------

    def notify_info(self: Any, title: str, message: str) -> None:
        InfoBar.success(
            title,
            message,
            parent=self,
            position=InfoBarPosition.TOP,
            duration=6000,
        )

    def notify_warning(self: Any, title: str, message: str) -> None:
        InfoBar.warning(
            title,
            message,
            parent=self,
            position=InfoBarPosition.TOP,
            duration=10000,
        )

    def closeEvent(self: Any, event) -> None:  # noqa: N802 (Qt override)
        if self._scan_running():
            box = MessageBox(
                strings.tr("msg_title_notice"),
                strings.tr("msg_scan_running_confirm_close"),
                self,
            )
            if not box.exec():
                event.ignore()
                return
            try:
                self.stop_scan()
            except Exception:
                pass
        DuplicateFinderApp.closeEvent(self, event)


def run_fluent() -> int:
    """Fluent 셸 실행 진입점 (``python main.py --fluent``)."""
    _require_fluent()
    from src.ui.app import create_application

    app = create_application()
    setTheme(Theme.AUTO)
    setThemeColor(BRAND_PRIMARY)
    window = FluentDuplicateFinderApp()
    window.show()
    return int(app.exec())


__all__ = [
    "FLUENT_NAV",
    "INTERFACE_NAMES",
    "FluentDuplicateFinderApp",
    "run_fluent",
]
