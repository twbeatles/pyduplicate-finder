from .legacy import MainWindowScanFlowMixin as _LegacyMainWindowScanFlowMixin


class MainWindowScanFoldersMixin:
    _on_folders_changed = _LegacyMainWindowScanFlowMixin._on_folders_changed
    add_path_to_list = _LegacyMainWindowScanFlowMixin.add_path_to_list
    add_folder = _LegacyMainWindowScanFlowMixin.add_folder
    add_drive_dialog = _LegacyMainWindowScanFlowMixin.add_drive_dialog
    clear_folders = _LegacyMainWindowScanFlowMixin.clear_folders
    remove_selected_folder = _LegacyMainWindowScanFlowMixin.remove_selected_folder
