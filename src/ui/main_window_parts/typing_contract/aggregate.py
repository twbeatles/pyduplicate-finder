from __future__ import annotations

from .results import ResultsFlowHost
from .scan import ScanFlowHost
from .schedule import ScheduleFlowHost
from .settings import SettingsFlowHost
from .tools import ToolsFlowHost
from .ui_shell import UiShellHost


class DuplicateFinderTypingContract(
    UiShellHost,
    ScanFlowHost,
    ResultsFlowHost,
    SettingsFlowHost,
    ScheduleFlowHost,
    ToolsFlowHost,
):
    pass
