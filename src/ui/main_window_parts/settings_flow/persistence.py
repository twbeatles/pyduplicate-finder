from .legacy import MainWindowSettingsFlowMixin as _LegacyMainWindowSettingsFlowMixin


class MainWindowSettingsPersistenceMixin:
    save_settings = _LegacyMainWindowSettingsFlowMixin.save_settings
    load_settings = _LegacyMainWindowSettingsFlowMixin.load_settings
