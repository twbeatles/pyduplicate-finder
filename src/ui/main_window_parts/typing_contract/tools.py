from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .shared import CommonWindowHost


class ToolsFlowHost(CommonWindowHost):
    if TYPE_CHECKING:
        btn_hardlink_checked: Any
        btn_ops_refresh: Any
        btn_ops_view: Any
        btn_quarantine_apply: Any
        btn_quarantine_pick: Any
        btn_quarantine_purge: Any
        btn_quarantine_purge_all: Any
        btn_quarantine_refresh: Any
        btn_quarantine_restore: Any
        btn_rules_apply: Any
        btn_rules_edit: Any
        chk_enable_hardlink: Any
        chk_quarantine_enabled: Any
        lbl_hardlink_title: Any
        lbl_ops_title: Any
        lbl_quarantine_days: Any
        lbl_quarantine_desc: Any
        lbl_quarantine_gb: Any
        lbl_quarantine_settings_title: Any
        lbl_quarantine_title: Any
        lbl_rules_desc: Any
        lbl_rules_title: Any
        spin_quarantine_days: Any
        spin_quarantine_gb: Any
        tbl_ops: Any
        tbl_quarantine: Any
        txt_quarantine_path: Any
        txt_quarantine_search: Any
