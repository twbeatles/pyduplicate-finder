from src.core.scan_engine import ScanConfig, build_scan_worker_kwargs


def test_build_scan_worker_kwargs_includes_new_flags():
    cfg = ScanConfig(
        folders=["C:/data"],
        use_similar_image=True,
        use_mixed_mode=True,
        detect_duplicate_folders=True,
        incremental_rescan=True,
        baseline_session_id=99,
    )
    kwargs = build_scan_worker_kwargs(cfg, session_id=12, use_cached_files=True)
    assert kwargs["use_similar_image"] is True
    assert kwargs["use_mixed_mode"] is True
    assert kwargs["detect_duplicate_folders"] is True
    assert kwargs["incremental_rescan"] is True
    assert kwargs["base_session_id"] == 99
    assert kwargs["session_id"] == 12
    assert kwargs["use_cached_files"] is True

