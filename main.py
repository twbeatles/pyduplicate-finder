import sys
import platform
from PySide6.QtWidgets import QApplication
from src.ui.main_window import DuplicateFinderApp
from src.utils.i18n import strings

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    font = app.font()
    font.setFamily("Malgun Gothic" if platform.system()=="Windows" else "AppleGothic")
    font.setPointSize(10)
    app.setFont(font)
    
    def exception_hook(exctype, value, traceback):
        from PySide6.QtWidgets import QMessageBox
        import traceback as tb
        error_msg = "".join(tb.format_exception(exctype, value, traceback))
        print(error_msg, file=sys.stderr)
        # Issue #24: i18n applied to error message
        title = strings.tr("err_critical_title") if strings.tr("err_critical_title") != "err_critical_title" else "Critical Error"
        msg = strings.tr("err_unexpected") if strings.tr("err_unexpected") != "err_unexpected" else "An unexpected error occurred"
        QMessageBox.critical(None, title, f"{msg}:\n{value}\n\n{strings.tr('status_ready')}")
        sys.exit(1)

    sys.excepthook = exception_hook

    window = DuplicateFinderApp()
    window.show()
    sys.exit(app.exec())
