"""Phase 1 (DUP-08 CLI): real `cli.py` process end-to-end (JSON v3).

Spawns the actual CLI as a subprocess over an isolated temp tree (duplicate
pair + same-size decoy), with the cache DB redirected into the temp dir so
the real user cache is never touched. The emitted v3 JSON must reload to
the identical group membership via the production loader.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from tests.quality.safety import assert_inside_root, files_byte_equal, write_bytes

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_dup08_cli_process_json_v3_roundtrip(tmp_path):
    data = tmp_path / "scanme"
    payload = b"cli-e2e-process-bytes" * 100
    dup_a = write_bytes(data / "a" / "dup.bin", payload)
    dup_b = write_bytes(data / "b" / "dup.bin", payload)
    decoy = write_bytes(data / "b" / "other.bin", b"different-content!!" * 100)
    out_json = tmp_path / "out.json"
    for p in (dup_a, dup_b, decoy):
        assert_inside_root(p, str(tmp_path))
    assert not files_byte_equal(dup_a, decoy)

    env = dict(os.environ)
    env["PYDUPLICATEFINDER_DB_PATH"] = str(tmp_path / "cli_cache.db")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "cli.py"), str(data),
         "--byte-compare", "--output-json", str(out_json)],
        cwd=ROOT, capture_output=True, text=True, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert os.path.exists(str(out_json))

    from src.core.result_schema import load_results_bundle_any

    with open(str(out_json), encoding="utf-8") as f:
        reloaded = load_results_bundle_any(json.load(f))
    groups = [sorted(map(str, v)) for v in reloaded["results"].values() if len(v) >= 2]
    assert len(groups) == 1
    assert sorted([dup_a, dup_b]) == groups[0]
    assert all(decoy not in g for g in groups)
