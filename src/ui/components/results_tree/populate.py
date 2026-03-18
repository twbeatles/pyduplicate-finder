from .legacy import ResultsTreeWidget as _LegacyResultsTreeWidget


class ResultsTreePopulateMixin:
    populate = _LegacyResultsTreeWidget.populate
    _update_group_summary = _LegacyResultsTreeWidget._update_group_summary
    _process_batch = _LegacyResultsTreeWidget._process_batch
    _add_group_item = _LegacyResultsTreeWidget._add_group_item
