from .legacy import MainWindowUiShellMixin as _LegacyMainWindowUiShellMixin


class MainWindowUiShellTranslateMixin:
    retranslate_ui = _LegacyMainWindowUiShellMixin.retranslate_ui
    change_language = _LegacyMainWindowUiShellMixin.change_language
