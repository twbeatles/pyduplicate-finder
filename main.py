import sys
import platform
from PySide6.QtWidgets import QApplication
from src.ui.main_window import DuplicateFinderApp

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
        QMessageBox.critical(None, "Critical Error", f"An unexpected error occurred:\n{value}\n\nSee console log for details.")
        sys.exit(1)

    sys.excepthook = exception_hook

    window = DuplicateFinderApp()
    window.show()
    sys.exit(app.exec())