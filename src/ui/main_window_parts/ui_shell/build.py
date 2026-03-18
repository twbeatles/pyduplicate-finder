from .legacy import MainWindowUiShellMixin as _LegacyMainWindowUiShellMixin


class MainWindowUiShellBuildMixin:
    _on_use_trash_toggled = _LegacyMainWindowUiShellMixin._on_use_trash_toggled
    dragEnterEvent = _LegacyMainWindowUiShellMixin.dragEnterEvent
    dropEvent = _LegacyMainWindowUiShellMixin.dropEvent
    _create_separator = _LegacyMainWindowUiShellMixin._create_separator
    init_ui = _LegacyMainWindowUiShellMixin.init_ui
    create_toolbar = _LegacyMainWindowUiShellMixin.create_toolbar
    open_empty_finder = _LegacyMainWindowUiShellMixin.open_empty_finder
