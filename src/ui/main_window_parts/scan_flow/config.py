from .legacy import MainWindowScanFlowMixin as _LegacyMainWindowScanFlowMixin


class MainWindowScanConfigMixin:
    _normalize_extension_tokens = _LegacyMainWindowScanFlowMixin._normalize_extension_tokens
    _normalize_path_list = _LegacyMainWindowScanFlowMixin._normalize_path_list
    _normalize_pattern_list = _LegacyMainWindowScanFlowMixin._normalize_pattern_list
    _get_scan_hash_config = _LegacyMainWindowScanFlowMixin._get_scan_hash_config
