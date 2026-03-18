from .actions import MainWindowResultsActionsMixin
from .filtering import MainWindowResultsFilterMixin
from .legacy import MainWindowResultsFlowMixin as _LegacyMainWindowResultsFlowMixin
from .persistence import MainWindowResultsPersistenceMixin
from .preview import MainWindowResultsPreviewMixin
from .rendering import MainWindowResultsRenderingMixin
from .selection import MainWindowResultsSelectionMixin


class MainWindowResultsFlowMixin(
    MainWindowResultsRenderingMixin,
    MainWindowResultsSelectionMixin,
    MainWindowResultsFilterMixin,
    MainWindowResultsPreviewMixin,
    MainWindowResultsActionsMixin,
    MainWindowResultsPersistenceMixin,
    _LegacyMainWindowResultsFlowMixin,
):
    pass


__all__ = ["MainWindowResultsFlowMixin"]
