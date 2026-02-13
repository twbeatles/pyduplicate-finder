from PySide6.QtCore import QThread, Signal
from src.utils.i18n import strings

class FileOperationWorker(QThread):
    progress_updated = Signal(int, str)
    operation_finished = Signal(bool, str) # Success, Message

    def __init__(self, manager, op_type, data=None, use_trash=False):
        super().__init__()
        self.manager = manager
        self.op_type = op_type
        self.data = data # logic specific data (e.g. paths to delete)
        self.use_trash = use_trash
        self.is_running = True

    def stop(self):
        """Issue #25: Allow external cancellation of operation."""
        self.is_running = False

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

        def check_cancel():
            return not self.is_running

        result = self.manager.execute_delete(
            self.data,
            progress_callback=progress_callback,
            use_trash=self.use_trash,
            check_cancel=check_cancel,
        )
        
        # Issue #2: execute_delete now returns Tuple[bool, str]
        if isinstance(result, tuple):
            success, message = result
        else:
            # Backwards compatibility fallback
            success = result
            message = strings.tr("msg_delete_success").format(len(self.data)) if success else strings.tr("err_operation_failed")
        
        self.operation_finished.emit(success, message)

    def _run_undo(self):
        self.progress_updated.emit(0, strings.tr("status_undoing"))
        res = self.manager.undo()
        
        if res is None:
            self.operation_finished.emit(False, strings.tr("err_undo_failed"))
            return
            
        # Issue #8: Handle tuple return (restored_paths, failed_count)
        if isinstance(res, tuple):
            restored_paths, failed_count = res
            if failed_count > 0:
                self.operation_finished.emit(True, f"{strings.tr('msg_undo_complete')} ({len(restored_paths)} restored, {failed_count} failed)")
            else:
                self.operation_finished.emit(True, strings.tr("msg_undo_complete"))
        else:
            # Backwards compatibility
            self.operation_finished.emit(True, strings.tr("msg_undo_complete"))

    def _run_redo(self):
        self.progress_updated.emit(0, strings.tr("status_redoing"))
        res = self.manager.redo()
        
        if res is None:
            self.operation_finished.emit(False, strings.tr("err_redo_failed"))
            return
            
        # Issue #8: Handle tuple return (deleted_paths, failed_count)
        if isinstance(res, tuple):
            deleted_paths, failed_count = res
            if failed_count > 0:
                self.operation_finished.emit(True, f"{strings.tr('msg_redo_complete').format(len(deleted_paths))} ({failed_count} failed)")
            else:
                self.operation_finished.emit(True, strings.tr("msg_redo_complete").format(len(deleted_paths)))
        else:
            # Backwards compatibility
            self.operation_finished.emit(True, strings.tr("msg_redo_complete").format(len(res)))
