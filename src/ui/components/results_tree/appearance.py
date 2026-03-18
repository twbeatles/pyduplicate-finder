from .legacy import ResultsTreeWidget as _LegacyResultsTreeWidget


class ResultsTreeAppearanceMixin:
    _get_file_icon = _LegacyResultsTreeWidget._get_file_icon
    set_theme_mode = _LegacyResultsTreeWidget.set_theme_mode
    _format_reclaim = _LegacyResultsTreeWidget._format_reclaim
    _format_size = _LegacyResultsTreeWidget._format_size
