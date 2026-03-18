from .legacy import ResultsTreeWidget as _LegacyResultsTreeWidget


class ResultsTreeStateMixin:
    begin_bulk_check_update = _LegacyResultsTreeWidget.begin_bulk_check_update
    end_bulk_check_update = _LegacyResultsTreeWidget.end_bulk_check_update
    get_group_paths = _LegacyResultsTreeWidget.get_group_paths
    set_group_checked = _LegacyResultsTreeWidget.set_group_checked
    _on_item_changed = _LegacyResultsTreeWidget._on_item_changed
    get_checked_files = _LegacyResultsTreeWidget.get_checked_files
    _rebuild_group_states = _LegacyResultsTreeWidget._rebuild_group_states
    _update_group_state_on_item_toggle = _LegacyResultsTreeWidget._update_group_state_on_item_toggle
