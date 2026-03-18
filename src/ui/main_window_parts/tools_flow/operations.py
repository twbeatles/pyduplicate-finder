from .legacy import MainWindowToolsFlowMixin as _LegacyMainWindowToolsFlowMixin


class MainWindowToolsOperationsMixin:
    refresh_operations_list = _LegacyMainWindowToolsFlowMixin.refresh_operations_list
    _selected_operation_row = _LegacyMainWindowToolsFlowMixin._selected_operation_row
    view_selected_operation = _LegacyMainWindowToolsFlowMixin.view_selected_operation
    _enqueue_operations = _LegacyMainWindowToolsFlowMixin._enqueue_operations
    _start_next_operation = _LegacyMainWindowToolsFlowMixin._start_next_operation
    _start_operation = _LegacyMainWindowToolsFlowMixin._start_operation
    _cancel_operation = _LegacyMainWindowToolsFlowMixin._cancel_operation
    _on_op_progress = _LegacyMainWindowToolsFlowMixin._on_op_progress
    _on_op_finished = _LegacyMainWindowToolsFlowMixin._on_op_finished
