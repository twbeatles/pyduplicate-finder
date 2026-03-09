from __future__ import annotations

import logging
from typing import Any, cast

from src.ui.main_window_parts.typing_contract import NavigationHost
from src.utils.i18n import strings

logger = logging.getLogger(__name__)


class NavigationController:
    PAGE_INDICES = {
        "scan": 0,
        "results": 1,
        "tools": 2,
        "settings": 3,
    }

    PAGE_LABEL_KEYS = {
        "scan": "nav_scan",
        "results": "nav_results",
        "tools": "nav_tools",
        "settings": "nav_settings",
    }

    def on_page_changed(self, host: Any, page_name: str) -> None:
        h = cast(NavigationHost, host)
        try:
            if page_name not in self.PAGE_INDICES:
                return

            h.page_stack.setCurrentIndex(self.PAGE_INDICES[page_name])
            if page_name == "tools":
                try:
                    h.refresh_quarantine_list()
                    h.refresh_operations_list()
                except Exception:
                    pass

            label = strings.tr(self.PAGE_LABEL_KEYS.get(page_name, ""))
            is_scanning = bool(getattr(h, "btn_stop_scan", None) and h.btn_stop_scan.isEnabled())
            if label and not is_scanning:
                h.status_label.setText(label)

            if hasattr(h, "toast_manager") and h.toast_manager and label:
                h.toast_manager.info(label, duration=2000)
        except Exception:
            logger.exception("Navigation error: %s", page_name)

    def navigate_to(self, host: Any, page_name: str) -> None:
        h = cast(NavigationHost, host)
        if hasattr(h, "sidebar"):
            h.sidebar.set_page(page_name)
        self.on_page_changed(h, page_name)
