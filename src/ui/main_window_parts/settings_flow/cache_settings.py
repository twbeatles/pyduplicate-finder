from .legacy import MainWindowSettingsFlowMixin as _LegacyMainWindowSettingsFlowMixin


class MainWindowSettingsCacheMixin:
    _get_current_config = _LegacyMainWindowSettingsFlowMixin._get_current_config
    _apply_config = _LegacyMainWindowSettingsFlowMixin._apply_config
    _apply_shortcuts = _LegacyMainWindowSettingsFlowMixin._apply_shortcuts
    _sync_advanced_visibility = _LegacyMainWindowSettingsFlowMixin._sync_advanced_visibility
    open_cache_db_folder = _LegacyMainWindowSettingsFlowMixin.open_cache_db_folder
    copy_cache_db_path = _LegacyMainWindowSettingsFlowMixin.copy_cache_db_path
    apply_cache_settings = _LegacyMainWindowSettingsFlowMixin.apply_cache_settings
