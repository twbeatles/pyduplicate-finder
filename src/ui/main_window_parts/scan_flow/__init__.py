from .config import MainWindowScanConfigMixin
from .folders import MainWindowScanFoldersMixin
from .legacy import MainWindowScanFlowMixin as _LegacyMainWindowScanFlowMixin
from .lifecycle import MainWindowScanLifecycleMixin


class MainWindowScanFlowMixin(
    MainWindowScanFoldersMixin,
    MainWindowScanLifecycleMixin,
    MainWindowScanConfigMixin,
    _LegacyMainWindowScanFlowMixin,
):
    pass


__all__ = ["MainWindowScanFlowMixin"]
