from .hardlink import MainWindowToolsHardlinkMixin
from .legacy import MainWindowToolsFlowMixin as _LegacyMainWindowToolsFlowMixin
from .operations import MainWindowToolsOperationsMixin
from .quarantine import MainWindowToolsQuarantineMixin
from .rules import MainWindowToolsRulesMixin


class MainWindowToolsFlowMixin(
    MainWindowToolsQuarantineMixin,
    MainWindowToolsOperationsMixin,
    MainWindowToolsRulesMixin,
    MainWindowToolsHardlinkMixin,
    _LegacyMainWindowToolsFlowMixin,
):
    pass


__all__ = ["MainWindowToolsFlowMixin"]
