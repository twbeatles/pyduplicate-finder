from __future__ import annotations

import src.core.scanner as scanner_module
import src.ui.components.results_tree as results_tree_module
from src.core.cache_manager import CacheManager
from src.core.scanner import IMAGE_HASH_AVAILABLE, ScanWorker
from src.ui.main_window import DuplicateFinderApp
from src.ui.theme import ModernTheme
from src.utils.i18n import I18n, strings
from src.utils.i18n.catalog_en import CATALOG_EN
from src.utils.i18n.catalog_ko import CATALOG_KO


def test_public_facade_imports_are_stable():
    assert CacheManager.__name__ == "CacheManager"
    assert ScanWorker.__name__ == "ScanWorker"
    assert isinstance(IMAGE_HASH_AVAILABLE, bool)
    assert I18n.__name__ == "I18n"
    assert ModernTheme.__name__ == "ModernTheme"
    assert DuplicateFinderApp.__name__ == "DuplicateFinderApp"
    assert results_tree_module.ResultsTreeWidget.__name__ == "ResultsTreeWidget"


def test_cache_manager_public_inventory():
    for name in [
        "SCHEMA_VERSION",
        "create_scan_session",
        "update_scan_session",
        "save_scan_results",
        "load_scan_results",
        "save_selected_paths_delta",
        "insert_quarantine_item",
        "list_operations",
        "upsert_scan_job",
        "close_all",
    ]:
        assert hasattr(CacheManager, name), name

    assert CacheManager.SCHEMA_VERSION == 7


def test_scanner_public_inventory():
    for name in [
        "progress_updated",
        "stage_updated",
        "scan_finished",
        "scan_cancelled",
        "scan_failed",
        "stop",
        "run",
        "get_file_hash",
        "compare_files_byte_by_byte",
    ]:
        assert hasattr(ScanWorker, name), name

    assert hasattr(scanner_module, "os")
    assert hasattr(scanner_module, "time")


def test_results_tree_public_inventory():
    widget_cls = results_tree_module.ResultsTreeWidget
    for name in [
        "files_checked",
        "files_checked_delta",
        "populate",
        "apply_filter",
        "get_checked_files",
        "set_group_checked",
        "begin_bulk_check_update",
        "end_bulk_check_update",
    ]:
        assert hasattr(widget_cls, name), name

    assert hasattr(results_tree_module, "os")


def test_main_window_public_inventory():
    for name in [
        "init_ui",
        "create_toolbar",
        "apply_theme",
        "start_scan",
        "filter_results_tree",
        "save_settings",
        "refresh_quarantine_list",
        "hardlink_consolidate_checked",
    ]:
        assert hasattr(DuplicateFinderApp, name), name


def test_i18n_catalog_keys_remain_in_sync():
    assert set(CATALOG_EN) == set(CATALOG_KO)
    assert len(CATALOG_EN) == len(CATALOG_KO)
    assert len(CATALOG_EN) >= 300
    assert strings.tr("app_title")


def test_theme_palette_contract_is_stable():
    light = ModernTheme.get_palette("light")
    dark = ModernTheme.get_palette("dark")

    for palette in [light, dark]:
        for key in [
            "bg",
            "panel",
            "card_bg",
            "text_primary",
            "text_secondary",
            "primary",
            "danger",
            "border",
        ]:
            assert key in palette

    stylesheet = ModernTheme.get_stylesheet("light")
    assert isinstance(stylesheet, str)
    assert "QMainWindow" in stylesheet
