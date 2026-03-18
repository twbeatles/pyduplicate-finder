from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .shared import CommonWindowHost


class ScheduleFlowHost(CommonWindowHost):
    if TYPE_CHECKING:
        btn_schedule_apply: Any
        btn_schedule_pick: Any
        chk_schedule_enabled: Any
        chk_schedule_export_csv: Any
        chk_schedule_export_json: Any
        cmb_schedule_frequency: Any
        cmb_schedule_weekday: Any
        lbl_schedule_frequency: Any
        lbl_schedule_output: Any
        lbl_schedule_time: Any
        lbl_schedule_title: Any
        lbl_schedule_weekday: Any
        txt_schedule_output: Any
        txt_schedule_time: Any
