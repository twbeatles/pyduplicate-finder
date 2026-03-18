from .build import MainWindowUiShellBuildMixin
from .legacy import MainWindowUiShellMixin as _LegacyMainWindowUiShellMixin
from .navigation import MainWindowUiShellNavigationMixin
from .theme import MainWindowUiShellThemeMixin
from .translate import MainWindowUiShellTranslateMixin


class MainWindowUiShellMixin(
    MainWindowUiShellBuildMixin,
    MainWindowUiShellTranslateMixin,
    MainWindowUiShellThemeMixin,
    MainWindowUiShellNavigationMixin,
    _LegacyMainWindowUiShellMixin,
):
    pass


__all__ = ["MainWindowUiShellMixin"]
