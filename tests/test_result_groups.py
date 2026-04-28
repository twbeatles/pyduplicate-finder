from __future__ import annotations

from src.core.result_groups import (
    GROUP_KIND_FOLDER,
    GROUP_KIND_SIMILAR,
    GROUP_TYPE_DUPLICATE,
    GROUP_TYPE_FOLDER_DUP,
    GROUP_TYPE_NAME_ONLY,
    GROUP_TYPE_SIMILAR_DOCUMENT,
    GROUP_TYPE_SIMILAR_IMAGE,
    classify_result_group,
)
from src.ui.main_window_parts.tools_flow.legacy import MainWindowToolsFlowMixin


def test_result_group_classifier_covers_safety_sensitive_kinds():
    exact = classify_result_group(("deadbeef", 123))
    assert exact.group_type == GROUP_TYPE_DUPLICATE
    assert exact.hardlink_eligible is True
    assert exact.size_from_key == 123

    name_only = classify_result_group(("NAME_ONLY", "copy.txt"))
    assert name_only.group_type == GROUP_TYPE_NAME_ONLY
    assert name_only.hardlink_eligible is False

    image = classify_result_group(("similar_42", 999))
    assert image.group_type == GROUP_TYPE_SIMILAR_IMAGE
    assert image.group_kind == GROUP_KIND_SIMILAR
    assert image.hardlink_eligible is False

    document = classify_result_group(("doc_similar_7", 999))
    assert document.group_type == GROUP_TYPE_SIMILAR_DOCUMENT
    assert document.group_kind == GROUP_KIND_SIMILAR
    assert document.hardlink_eligible is False

    folder = classify_result_group(("FOLDER_DUP", "sig", 4096, 3))
    assert folder.group_type == GROUP_TYPE_FOLDER_DUP
    assert folder.group_kind == GROUP_KIND_FOLDER
    assert folder.bytes_reclaim_est == 4096
    assert folder.hardlink_eligible is False


def test_hardlink_ui_eligibility_uses_classifier():
    checker = MainWindowToolsFlowMixin._is_group_key_hardlink_eligible
    assert checker(None, ("hash", 10)) is True
    assert checker(None, ("NAME_ONLY", "same-name.txt")) is False
    assert checker(None, ("similar_1", 10)) is False
    assert checker(None, ("doc_similar_1", 10)) is False
    assert checker(None, ("FOLDER_DUP", "sig", 100, 2)) is False
