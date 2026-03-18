from .legacy import MainWindowScanFlowMixin as _LegacyMainWindowScanFlowMixin


class MainWindowScanLifecycleMixin:
    start_scan = _LegacyMainWindowScanFlowMixin.start_scan
    stop_scan = _LegacyMainWindowScanFlowMixin.stop_scan
    toggle_ui_state = _LegacyMainWindowScanFlowMixin.toggle_ui_state
    update_progress = _LegacyMainWindowScanFlowMixin.update_progress
    on_scan_stage_changed = _LegacyMainWindowScanFlowMixin.on_scan_stage_changed
    on_scan_finished = _LegacyMainWindowScanFlowMixin.on_scan_finished
    on_scan_cancelled = _LegacyMainWindowScanFlowMixin.on_scan_cancelled
    on_scan_failed = _LegacyMainWindowScanFlowMixin.on_scan_failed
