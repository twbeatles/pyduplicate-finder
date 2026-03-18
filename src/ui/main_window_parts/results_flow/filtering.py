from .legacy import MainWindowResultsFlowMixin as _LegacyMainWindowResultsFlowMixin


class MainWindowResultsFilterMixin:
    on_result_filter_text_changed = _LegacyMainWindowResultsFlowMixin.on_result_filter_text_changed
    _apply_result_filter = _LegacyMainWindowResultsFlowMixin._apply_result_filter
    filter_results_tree = _LegacyMainWindowResultsFlowMixin.filter_results_tree
