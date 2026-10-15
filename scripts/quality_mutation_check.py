"""Mutation negative-control runner (Phase 3).

Applies each mutant ONE at a time to the working tree, runs its killer test
(expecting RED / non-zero exit), then reverts and verifies the revert by
SHA-256. Refuses to start unless the tracked tree is clean, and refuses to
finish unless it is clean again.

Writes docs/quality/2026-10-file-safety/MUTATION_EVIDENCE.md from the real
run — no hand-written PASS claims.

Usage:  python scripts/quality_mutation_check.py
"""

from __future__ import annotations

import difflib
import hashlib
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOC_DIR = os.path.join(ROOT, "docs", "quality", "2026-10-file-safety")
EVIDENCE_MD = os.path.join(DOC_DIR, "MUTATION_EVIDENCE.md")


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(1024 * 1024)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


MUTANTS = [
    {
        "id": "M1",
        "desc": "같은 크기 파일이면 바이트 비교 생략 (해시 동점 그룹 무조건 병합)",
        "file": "src/core/scanner/folder_duplicates.py",
        "old": (
            "        else:\n"
            "            self._byte_compare_group(file_hash, size, paths, final_duplicates)\n"
        ),
        "new": (
            "        else:\n"
            '            final_duplicates[(file_hash, size, "byte_0")] = paths  # MUTANT-M1: skip byte comparison\n'
        ),
        "expect_count": 1,
        "killer": "tests/quality/test_dup_exact.py::test_dup02_seeded_hash_collision_resolved_by_byte_compare",
        "kills": "DUP-02",
    },
    {
        "id": "M2",
        "desc": "cached fingerprint 무조건 신뢰 (size/mtime 검사 제거, rust+python 경로)",
        "file": "src/core/scanner/hashing.py",
        "old": "if cached and cached[1] == size and cached[2] == mtime:",
        "new": "if cached:  # MUTANT-M2: trust cached fingerprint unconditionally",
        "expect_count": 2,
        "killer": "tests/quality/test_dup_backend.py::test_dup06_stale_session_hash_with_changed_size_is_rehashed",
        "kills": "DUP-05/06",
    },
    {
        "id": "M3",
        "desc": "하드링크 동등 파일을 별도 파일로 집계 (inode dedup 제거)",
        "file": "src/core/scanner/discovery.py",
        "old": (
            "                    if stat.st_ino:\n"
            "                        inode_key = (stat.st_dev, stat.st_ino)\n"
            "                        if inode_key in self.seen_inodes:\n"
            "                            continue\n"
            "                        self.seen_inodes.add(inode_key)\n"
            "\n"
            "                    size = int(stat.st_size)\n"
            "                    mtime = float(stat.st_mtime)\n"
            "                    self._track_file_record(entry.path, size, mtime, size_map, db_batch)\n"
        ),
        "new": (
            "                    if stat.st_ino:\n"
            "                        inode_key = (stat.st_dev, stat.st_ino)\n"
            "                        # MUTANT-M3: no inode dedup\n"
            "                        self.seen_inodes.add(inode_key)\n"
            "\n"
            "                    size = int(stat.st_size)\n"
            "                    mtime = float(stat.st_mtime)\n"
            "                    self._track_file_record(entry.path, size, mtime, size_map, db_batch)\n"
        ),
        "expect_count": 1,
        "killer": "tests/quality/test_dup_exact.py::test_dup03_hardlink_same_inode_not_double_counted_and_symlink_safe",
        "kills": "DUP-03",
    },
    {
        "id": "M4",
        "desc": "파일 이동 성공 뒤 DB INSERT 실패 무시 (롤백 제거)",
        "file": "src/core/quarantine_manager.py",
        "old": "                if item_id <= 0:\n",
        "new": "                if False:  # MUTANT-M4: ignore DB insert failure\n",
        "expect_count": 1,
        "killer": "tests/quality/test_fs_quarantine.py::test_fs02_insert_returning_zero_restores_file_to_origin",
        "kills": "FS-02",
    },
    {
        "id": "M5",
        "desc": "복원 시 기존 파일 무조건 덮어쓰기",
        "file": "src/core/quarantine_manager.py",
        "old": "                if not replaced:\n                    dest = _conflict_restore_path(orig_path)\n",
        "new": "                if not replaced:\n                    dest = orig_path  # MUTANT-M5: overwrite on collision\n",
        "expect_count": 1,
        "killer": "tests/quality/test_fs_quarantine.py::test_fs04_restore_collision_preserves_both_files",
        "kills": "FS-04",
    },
    {
        "id": "M6",
        "desc": "작업 계획의 stale 검사 건너뛰기 (fresh stat 미사용)",
        "file": "src/core/quarantine_manager.py",
        "old": (
            "                st = os.stat(p)\n"
            "                size = int(st.st_size)\n"
            "                mtime = float(st.st_mtime)\n"
        ),
        "new": (
            "                st = os.stat(p)\n"
            "                size = 0  # MUTANT-M6: skip fresh stat\n"
            "                mtime = 0.0  # MUTANT-M6: skip fresh stat\n"
        ),
        "expect_count": 1,
        "killer": "tests/quality/test_fs_hardlink_ops.py::test_fs06_move_records_fresh_stat_never_stale_caller_metadata",
        "kills": "FS-06",
    },
    {
        "id": "M7",
        "desc": "그룹 종류에 상관없이 hardlink 허용",
        "file": "src/core/result_groups.py",
        "old": "    hardlink_eligible = group_type == GROUP_TYPE_DUPLICATE\n",
        "new": "    hardlink_eligible = True  # MUTANT-M7: allow hardlink for any group\n",
        "expect_count": 1,
        "killer": "tests/quality/test_dup_policy_schema.py::test_dup07_result_group_hardlink_eligibility_matrix",
        "kills": "DUP-07/FS-05",
    },
    {
        "id": "M8",
        "desc": "격리 retention 기준 반전",
        "file": "src/core/quarantine_manager.py",
        "old": "            over_age = (max_days > 0) and (age_days > max_days)\n",
        "new": "            over_age = (max_days > 0) and (age_days < max_days)  # MUTANT-M8: inverted\n",
        "expect_count": 1,
        "killer": "tests/quality/test_fs_quarantine.py::test_fs09_retention_purges_only_expired_live_records_survive",
        "kills": "FS-09",
    },
    {
        "id": "M9",
        "desc": "오류 발생 후 무조건 completed 처리",
        "file": "src/core/operation_queue.py",
        "old": (
            "        else:\n"
            "            if res.failed and res.succeeded:\n"
            '                res.status = "partial"\n'
            "            elif res.failed and not res.succeeded:\n"
            '                res.status = "failed"\n'
            "            else:\n"
            '                res.status = "completed"\n'
            '            res.message = strings.tr("op_moved_quarantine").format(ok=len(res.succeeded), total=total)\n'
        ),
        "new": (
            "        else:\n"
            '            res.status = "completed"  # MUTANT-M9: always completed\n'
            '            res.message = strings.tr("op_moved_quarantine").format(ok=len(res.succeeded), total=total)\n'
        ),
        "expect_count": 1,
        "killer": "tests/quality/test_fs_hardlink_ops.py::test_fs08_mixed_failures_are_separated_valid_work_survives",
        "kills": "FS-08/10",
    },
]


def main() -> int:
    tracked_dirty = _git("status", "--short").strip()
    tracked_dirty = "\n".join(
        line for line in tracked_dirty.splitlines() if not line.startswith("??")
    ).strip()
    if tracked_dirty:
        print("REFUSING: tracked tree is dirty:\n" + tracked_dirty)
        return 2

    head = _git("rev-parse", "HEAD").strip()
    results = []
    for m in MUTANTS:
        fpath = os.path.join(ROOT, m["file"].replace("/", os.sep))
        with open(fpath, "rb") as f:
            original_bytes = f.read()
        original_sha = _sha(fpath)
        old_b = m["old"].encode("utf-8")
        new_b = m["new"].encode("utf-8")
        # Anchor may be LF in source while the file uses CRLF: try both.
        if original_bytes.count(old_b) == m["expect_count"]:
            old_use, new_use = old_b, new_b
        elif original_bytes.count(old_b.replace(b"\n", b"\r\n")) == m["expect_count"]:
            old_use = old_b.replace(b"\n", b"\r\n")
            new_use = new_b.replace(b"\n", b"\r\n")
        else:
            print(f"{m['id']}: anchor count != expected {m['expect_count']}; marking ERROR")
            results.append({**m, "outcome": "ERROR", "original_sha": original_sha,
                            "revert_sha": original_sha, "exit": None, "log": "anchor mismatch",
                            "diff": ""})
            continue
        mutated_bytes = original_bytes.replace(old_use, new_use)
        with open(fpath, "wb") as f:
            f.write(mutated_bytes)
        original_text = original_bytes.decode("utf-8")
        mutated_text = mutated_bytes.decode("utf-8")
        diff = "".join(
            difflib.unified_diff(
                original_text.splitlines(True), mutated_text.splitlines(True),
                fromfile="a/" + m["file"], tofile="b/" + m["file"],
            )
        )
        cmd = [sys.executable, "-m", "pytest", m["killer"], "-q", "-p", "no:cacheprovider"]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-8:])
        killed = proc.returncode != 0
        with open(fpath, "wb") as f:
            f.write(original_bytes)
        revert_sha = _sha(fpath)
        status = "KILLED" if killed else "SURVIVED"
        print(f"{m['id']}: exit={proc.returncode} -> {status} (revert_ok={revert_sha == original_sha})")
        results.append({**m, "outcome": status, "original_sha": original_sha,
                        "revert_sha": revert_sha, "exit": proc.returncode, "log": tail,
                        "diff": diff})
        if revert_sha != original_sha:
            print(f"{m['id']}: REVERT MISMATCH — aborting")
            return 3

    final_dirty = _git("status", "--short").strip()
    final_dirty = "\n".join(
        line for line in final_dirty.splitlines() if not line.startswith("??")
    ).strip()
    if final_dirty:
        print("REFUSING TO FINISH: tracked tree dirty after run:\n" + final_dirty)
        return 4

    killed_n = sum(1 for r in results if r["outcome"] == "KILLED")
    os.makedirs(DOC_DIR, exist_ok=True)
    lines = [
        "# Mutation evidence (generated by scripts/quality_mutation_check.py)",
        "",
        f"HEAD: {head}",
        f"Result: {killed_n} killed / {len(results)} executed",
        "",
        "| Mutant | Change | Killer test | Exit | Verdict | Revert SHA ok |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['id']} | {r['desc']} | `{r['killer']}` | {r['exit']} | "
            f"{r['outcome']} | {r['revert_sha'] == r['original_sha']} |"
        )
    for r in results:
        lines += [
            "",
            f"## {r['id']} — {r['desc']} ({r['outcome']})",
            "",
            f"- File: `{r['file']}`",
            f"- Kills requirement: {r['kills']}",
            f"- Command: `python -m pytest {r['killer']} -q -p no:cacheprovider`",
            f"- Exit: `{r['exit']}` (non-zero = RED = killed)",
            f"- Original SHA-256: `{r['original_sha']}`",
            f"- Revert SHA-256: `{r['revert_sha']}`",
            "",
            "```diff",
            (r.get("diff") or "").strip(),
            "```",
            "",
            "```text",
            (r.get("log") or "").strip(),
            "```",
        ]
    lines += ["", f"Tracked-tree clean after run: {not bool(final_dirty)}", ""]
    with open(EVIDENCE_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"wrote {EVIDENCE_MD}")
    return 0 if killed_n >= 8 else 5


if __name__ == "__main__":
    raise SystemExit(main())
