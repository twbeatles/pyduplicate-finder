from .legacy import ResultsTreeWidget as _LegacyResultsTreeWidget


class ResultsTreeFilterMixin:
    apply_filter = _LegacyResultsTreeWidget.apply_filter
