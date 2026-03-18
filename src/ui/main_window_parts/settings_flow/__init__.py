from .cache_settings import MainWindowSettingsCacheMixin
from .dialogs import MainWindowSettingsDialogsMixin
from .legacy import MainWindowSettingsFlowMixin as _LegacyMainWindowSettingsFlowMixin
from .persistence import MainWindowSettingsPersistenceMixin
from .session_restore import MainWindowSettingsSessionRestoreMixin


class MainWindowSettingsFlowMixin(
    MainWindowSettingsPersistenceMixin,
    MainWindowSettingsSessionRestoreMixin,
    MainWindowSettingsDialogsMixin,
    MainWindowSettingsCacheMixin,
    _LegacyMainWindowSettingsFlowMixin,
):
    pass


__all__ = ["MainWindowSettingsFlowMixin"]
