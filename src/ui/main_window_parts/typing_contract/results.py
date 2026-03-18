from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .shared import CommonWindowHost


class ResultsFlowHost(CommonWindowHost):
    if TYPE_CHECKING:
        action_newest: Any
        action_oldest: Any
        action_pattern: Any
        action_smart: Any
        btn_delete: Any
        btn_export: Any
        btn_select_rules: Any
        btn_select_smart: Any
        lbl_action_meta: Any
        lbl_image_preview: Any
        lbl_info_preview: Any
        lbl_preview_meta: Any
        lbl_preview_name: Any
        lbl_preview_path: Any
        preview_info: Any
        txt_result_filter: Any
        txt_text_preview: Any
