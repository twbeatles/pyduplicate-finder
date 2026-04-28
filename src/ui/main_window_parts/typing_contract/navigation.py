from __future__ import annotations

from typing import Any, Protocol


class NavigationHost(Protocol):
    page_stack: Any
    status_label: Any
    sidebar: Any
    btn_stop_scan: Any
    toast_manager: Any

    def refresh_quarantine_list(self) -> None: ...
    def refresh_operations_list(self) -> None: ...
    def refresh_exemption_list(self) -> None: ...
    def refresh_insights_page(self) -> None: ...
