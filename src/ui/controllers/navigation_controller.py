from __future__ import annotations

import logging
from typing import Any

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
        try:
            if page_name not in self.PAGE_INDICES:
                return

            host.page_stack.setCurrentIndex(self.PAGE_INDICES[page_name])
            if page_name == "tools":
                try:
                    host.refresh_quarantine_list()
                    host.refresh_operations_list()
                except Exception:
                    pass

            label = strings.tr(self.PAGE_LABEL_KEYS.get(page_name, ""))
            is_scanning = bool(getattr(host, "btn_stop_scan", None) and host.btn_stop_scan.isEnabled())
            if label and not is_scanning:
                host.status_label.setText(label)

            if hasattr(host, "toast_manager") and host.toast_manager and label:
                host.toast_manager.info(label, duration=2000)
        except Exception:
            logger.exception("Navigation error: %s", page_name)

    def navigate_to(self, host: Any, page_name: str) -> None:
        if hasattr(host, "sidebar"):
            host.sidebar.set_page(page_name)
        self.on_page_changed(host, page_name)
