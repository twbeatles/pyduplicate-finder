from PySide6.QtCore import QThread, Signal
from src.utils.i18n import strings

class FileOperationWorker(QThread):
    progress_updated = Signal(int, str)
    operation_finished = Signal(bool, str) # Success, Message

    def __init__(self, manager, op_type, data=None):
        super().__init__()
        self.manager = manager
        self.op_type = op_type
        self.data = data # logic specific data (e.g. paths to delete)
        self.is_running = True

    def run(self):
        try:
            if self.op_type == 'delete':
                self._run_delete()
            elif self.op_type == 'undo':
                self._run_undo()
            elif self.op_type == 'redo':
                self._run_redo()
        except Exception as e:
            self.operation_finished.emit(False, str(e))

    def _run_delete(self):
        def progress_callback(current, total):
            # 0% ~ 100% calculation
            percent = int((current / total) * 100)
            self.progress_updated.emit(percent, f"{strings.tr('status_analyzing')} ({current}/{total})")

        success = self.manager.execute_delete(self.data, progress_callback=progress_callback)
        
        if success:
             self.operation_finished.emit(True, strings.tr("msg_delete_success").format(len(self.data)))
        else:
             self.operation_finished.emit(False, "Operation failed or nothing done.")

    def _run_undo(self):
        self.progress_updated.emit(0, strings.tr("status_undoing"))
        res = self.manager.undo()
        if res is not None:
            self.operation_finished.emit(True, strings.tr("msg_undo_complete"))
        else:
            self.operation_finished.emit(False, "Undo failed (Stack empty?)")

    def _run_redo(self):
        self.progress_updated.emit(0, strings.tr("status_redoing"))
        res = self.manager.redo()
        if res is not None:
             self.operation_finished.emit(True, strings.tr("msg_redo_complete").format(len(res)))
        else:
             self.operation_finished.emit(False, "Redo failed")
