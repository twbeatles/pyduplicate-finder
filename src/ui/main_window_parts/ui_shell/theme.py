from .legacy import MainWindowUiShellMixin as _LegacyMainWindowUiShellMixin


class MainWindowUiShellThemeMixin:
    apply_theme = _LegacyMainWindowUiShellMixin.apply_theme
    toggle_theme = _LegacyMainWindowUiShellMixin.toggle_theme
