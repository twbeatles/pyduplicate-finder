from .appearance import ResultsTreeAppearanceMixin
from .constants import (
    _ROLE_BASE,
    _ROLE_EXISTS,
    _ROLE_GROUP_BASE_LABEL,
    _ROLE_GROUP_ID,
    _ROLE_GROUP_KEY,
    _ROLE_LOWER_PATH,
    _ROLE_MTIME,
    _ROLE_PATH,
    _ROLE_SIZE_BYTES,
)
from .filtering import ResultsTreeFilterMixin
from .legacy import ResultsTreeWidget as _LegacyResultsTreeWidget
from .legacy import os, time
from .populate import ResultsTreePopulateMixin
from .state import ResultsTreeStateMixin


class ResultsTreeWidget(
    ResultsTreePopulateMixin,
    ResultsTreeStateMixin,
    ResultsTreeFilterMixin,
    ResultsTreeAppearanceMixin,
    _LegacyResultsTreeWidget,
):
    pass


__all__ = [
    "ResultsTreeWidget",
    "os",
    "time",
    "_ROLE_BASE",
    "_ROLE_PATH",
    "_ROLE_GROUP_KEY",
    "_ROLE_EXISTS",
    "_ROLE_GROUP_BASE_LABEL",
    "_ROLE_LOWER_PATH",
    "_ROLE_MTIME",
    "_ROLE_GROUP_ID",
    "_ROLE_SIZE_BYTES",
]
