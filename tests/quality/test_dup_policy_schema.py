"""Phase 1 (DUP-07 / DUP-08): selection/exemption policy + result schema roundtrip.

All cases run on real files / real worker filter code. The KEEP-marked file
must never appear as a delete/link candidate, and a serialized v3 payload
must reload to identical group membership and decision state.
"""

from __future__ import annotations

import json
import os

from tests.quality.safety import find_group_containing, group_key_members


def _run_exact_scan(worker, *, byte_compare=True):
    worker.byte_compare = bool(byte_compare)
    size_map = worker._scan_files()
    candidates = []
    for size, paths in size_map.items():
        if len(paths) > 1:
            for path in paths:
                meta = worker._file_meta.get(path)
                if meta:
                    candidates.append((path, int(meta[0]), float(meta[1])))
    temp_hash_map = worker._calculate_hashes_parallel(candidates, is_quick_scan=True)
    final: dict = {}
    for key, paths in temp_hash_map.items():
        if len(paths) >= 2:
            worker._process_final_group(key[1], key[0], paths, final)
    return worker._apply_post_scan_filters(final)


def test_dup07_ignore_exemption_removes_path_safelist_keeps_with_status(
    quality_root, worker_factory
):
    from src.core.scan_types import EXEMPTION_ACTION_IGNORE, EXEMPTION_ACTION_SAFELIST

    payload = b"exemption-policy-bytes" * 64
    keep = quality_root / "data" / "keep_me.bin"
    ignored = quality_root / "data" / "ignore_me.bin"
    plain = quality_root / "data" / "plain.bin"
    for p in (keep, ignored, plain):
        p.write_bytes(payload)

    worker = worker_factory([str(quality_root / "data")], quality_root)
    worker._exemption_rules = [
        __import__("src.core.scan_types", fromlist=["ExemptionRule"]).ExemptionRule(
            kind="exact_path", value=str(ignored), action=EXEMPTION_ACTION_IGNORE, note=""
        ),
        __import__("src.core.scan_types", fromlist=["ExemptionRule"]).ExemptionRule(
            kind="exact_path", value=str(keep), action=EXEMPTION_ACTION_SAFELIST, note=""
        ),
    ]
    final = _run_exact_scan(worker)
    groups = group_key_members(final)

    surviving = find_group_containing(groups, str(keep), str(plain))
    assert surviving is not None
    assert str(ignored) not in surviving
    # The ignored path is excluded from every surviving group.
    for g in groups:
        assert str(ignored) not in g
    assert worker._path_exemption_status.get(str(ignored)) == "ignore"
    assert worker._path_exemption_status.get(str(keep)) == "safelisted"


def test_dup07_explicit_keep_rule_wins_over_policy(quality_root):
    from src.core.selection_rules import SelectionRule, decide_keep_delete_for_group

    from tests.quality.safety import write_bytes

    # NOTE: SelectionRule matches the full normalized path or the basename
    # (fnmatch, no implicit substring): the pattern must glob the basename.
    payload = b"keep-rule-bytes" * 32
    other = write_bytes(quality_root / "data" / "ordinary.bin", payload)
    keeper = write_bytes(quality_root / "data" / "must_keep_copy.bin", payload)

    keep, delete = decide_keep_delete_for_group(
        [other, keeper], [SelectionRule(pattern="*must_keep*", action="keep")]
    )
    assert keeper in keep
    assert other in delete
    # KEEP-marked file is never a delete candidate.
    assert keeper not in delete


def test_dup07_result_group_hardlink_eligibility_matrix():
    from src.core.result_groups import classify_result_group

    dup = classify_result_group(("abc123", 1024))
    assert dup.hardlink_eligible is True
    assert dup.risk_level == "low"

    name_only = classify_result_group(("NAME_ONLY", "report.txt"))
    assert name_only.hardlink_eligible is False
    assert name_only.risk_level == "high"

    similar = classify_result_group(("similar_0",))
    assert similar.hardlink_eligible is False


def test_dup08_v3_serialize_reload_preserves_meaning(quality_root, worker_factory, tmp_path):
    from src.core.result_schema import dump_results_v3, load_results_bundle_any

    payload = b"schema-roundtrip" * 64
    f1 = quality_root / "data" / "s1.bin"
    f2 = quality_root / "data" / "s2.bin"
    f1.write_bytes(payload)
    f2.write_bytes(payload)
    st = os.stat(str(f1))

    worker = worker_factory([str(quality_root / "data")], quality_root)
    final = _run_exact_scan(worker)
    assert find_group_containing(group_key_members(final), str(f1), str(f2)) is not None

    file_meta = {str(f1): (int(st.st_size), float(st.st_mtime))}
    dumped = dump_results_v3(
        scan_results=final,
        folders=[str(quality_root / "data")],
        source="quality-test",
        file_meta=file_meta,
        selection_reason_map={str(f1): "keep-newest", str(f2): "delete-duplicate"},
        collection_role_map={str(f1): "primary"},
    )
    assert dumped["version"] == 3
    # Persist through real JSON text (exercises the CLI's write path shape).
    text = json.dumps(dumped, ensure_ascii=False)
    reloaded = load_results_bundle_any(json.loads(text))

    before = sorted(sorted(g) for g in group_key_members(final))
    after = sorted(sorted(map(str, g)) for g in group_key_members(reloaded["results"]))
    assert before == after
    assert reloaded["file_meta"][str(f1)][0] == int(st.st_size)
    state_rows = dumped["meta"]["file_state"]
    assert state_rows[str(f1)]["selection_reason"] == "keep-newest"
    assert state_rows[str(f1)]["collection_role"] == "primary"


def test_dup08_legacy_loader_reads_v2_payload(quality_root, worker_factory):
    from src.core.result_schema import dump_results_v2, load_results_any

    f1 = quality_root / "data" / "l1.bin"
    f2 = quality_root / "data" / "l2.bin"
    f1.write_bytes(b"legacy-loader" * 64)
    f2.write_bytes(b"legacy-loader" * 64)

    worker = worker_factory([str(quality_root / "data")], quality_root)
    final = _run_exact_scan(worker)
    dumped = dump_results_v2(scan_results=final, folders=[str(quality_root / "data")])
    assert dumped["version"] == 2
    loaded = load_results_any(json.loads(json.dumps(dumped)))
    assert sorted(sorted(g) for g in group_key_members(loaded)) == sorted(
        sorted(g) for g in group_key_members(final)
    )
