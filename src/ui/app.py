"""앱 부팅/의존성 확인/테마 초기화 (경로 B canonical 진입점).

KTrain ``ktrain/gui/app.py`` 와 같은 위치의 모듈이다: GUI 의존성 검증 →
DPI 초기화 → ``QApplication`` 생성 → 테마 초기화 → 셸 생성 → 실행.
기존 ``main.py`` 진입점은 그대로 동작한다 (호환 유지).
"""

from __future__ import annotations

import platform
import sys


def check_gui_dependencies() -> None:
    """GUI 필수 조건 확인. PySide6 없으면 즉시 종료, 바인딩 충돌은 안내한다."""
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print(
            "GUI 실행에 필요한 패키지가 설치되지 않았습니다.\n"
            "  누락: PySide6\n\n"
            "설치:\n"
            "  pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1)
    from src.ui.qt_binding import format_qt_binding_error, inspect_qt_bindings

    report = inspect_qt_bindings()
    if not report.ok:
        message = format_qt_binding_error(report)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "PyDuplicate Finder Pro", message)
            app.quit()
        except Exception:
            print(message, file=sys.stderr)
        raise SystemExit(1)


def create_application(argv: list[str] | None = None):
    """DPI·폰트까지 적용된 ``QApplication`` 생성 (QWidget 생성 전 호출)."""
    from PySide6.QtWidgets import QApplication

    from src.ui.adapters.settings_binding import APP_NAME
    from src.ui.design_system.hidpi import configure_high_dpi

    configure_high_dpi()
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("PyDuplicate Finder Pro")
    app.setOrganizationName(APP_NAME)
    font = app.font()
    font.setFamily("Malgun Gothic" if platform.system() == "Windows" else "AppleGothic")
    font.setPointSize(10)
    app.setFont(font)
    return app


def run(argv: list[str] | None = None) -> int:
    """GUI 실행. 의존성 실패 시 SystemExit(1), 정상 종료 시 0."""
    check_gui_dependencies()
    app = create_application(argv)

    from PySide6.QtCore import QSettings

    from src.ui.adapters.settings_binding import APP_NAME, ORG_NAME, migrate_settings
    from src.ui.main_window import DuplicateFinderApp

    settings = QSettings(ORG_NAME, APP_NAME)
    migrate_settings(settings)

    window = DuplicateFinderApp()
    window.show()
    return int(app.exec())


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
