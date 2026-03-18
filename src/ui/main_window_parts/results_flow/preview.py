from .legacy import MainWindowResultsFlowMixin as _LegacyMainWindowResultsFlowMixin


class MainWindowResultsPreviewMixin:
    update_preview = _LegacyMainWindowResultsFlowMixin.update_preview
    _on_preview_ready = _LegacyMainWindowResultsFlowMixin._on_preview_ready
    show_preview_info = _LegacyMainWindowResultsFlowMixin.show_preview_info
    _set_preview_info = _LegacyMainWindowResultsFlowMixin._set_preview_info
