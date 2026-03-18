from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .shared import CommonWindowHost


class ScanFlowHost(CommonWindowHost):
    if TYPE_CHECKING:
        btn_add_drive: Any
        btn_add_folder: Any
        btn_clear_folder: Any
        btn_remove_folder: Any
        btn_show_options: Any
        btn_start_scan: Any
        btn_stop_scan: Any
        chk_byte_compare: Any
        chk_detect_folder_dup: Any
        chk_follow_symlinks: Any
        chk_incremental_rescan: Any
        chk_mixed_mode: Any
        chk_name_only: Any
        chk_protect_system: Any
        chk_same_name: Any
        chk_similar_image: Any
        chk_skip_hidden: Any
        chk_strict_mode: Any
        lbl_ext: Any
        lbl_min_size: Any
        lbl_similarity: Any
        lbl_strict_max_errors: Any
        list_folders: Any
        spin_min_size: Any
        spin_similarity: Any
        spin_strict_max_errors: Any
        txt_extensions: Any
