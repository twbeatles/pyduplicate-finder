from .legacy import MainWindowResultsFlowMixin as _LegacyMainWindowResultsFlowMixin


class MainWindowResultsRenderingMixin:
    populate_tree = _LegacyMainWindowResultsFlowMixin.populate_tree
    format_size = _LegacyMainWindowResultsFlowMixin.format_size
    _group_entries_with_items = _LegacyMainWindowResultsFlowMixin._group_entries_with_items
    _mtime_for_path = _LegacyMainWindowResultsFlowMixin._mtime_for_path
    _render_results = _LegacyMainWindowResultsFlowMixin._render_results
    _set_results_view = _LegacyMainWindowResultsFlowMixin._set_results_view
    _update_results_summary = _LegacyMainWindowResultsFlowMixin._update_results_summary
    _update_action_buttons_state = _LegacyMainWindowResultsFlowMixin._update_action_buttons_state
