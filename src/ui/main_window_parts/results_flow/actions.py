from .legacy import MainWindowResultsFlowMixin as _LegacyMainWindowResultsFlowMixin


class MainWindowResultsActionsMixin:
    open_file = _LegacyMainWindowResultsFlowMixin.open_file
    export_results = _LegacyMainWindowResultsFlowMixin.export_results
    delete_selected_files = _LegacyMainWindowResultsFlowMixin.delete_selected_files
    _show_delete_dry_run = _LegacyMainWindowResultsFlowMixin._show_delete_dry_run
    perform_undo = _LegacyMainWindowResultsFlowMixin.perform_undo
    perform_redo = _LegacyMainWindowResultsFlowMixin.perform_redo
    show_context_menu = _LegacyMainWindowResultsFlowMixin.show_context_menu
    open_containing_folder = _LegacyMainWindowResultsFlowMixin.open_containing_folder
    copy_to_clipboard = _LegacyMainWindowResultsFlowMixin.copy_to_clipboard
