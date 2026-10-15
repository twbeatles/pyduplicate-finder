"""Safety + independent-oracle helpers for real-file quality tests.

Plan contract (Phase 0):
- destructive targets are confined to a per-test isolated root created by
  the harness itself (a fresh ``tmp_path`` subdirectory);
- any target outside that root is refused *before* execution;
- expectations are computed with independent primitives (``hashlib`` /
  streaming byte comparison / ``os.stat`` identity) and never by importing
  the production duplicate classifier to derive the expected value.
"""

from __future__ import annotations

import filecmp
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple


CHUNK = 1024 * 1024


def canonical(path: str | os.PathLike[str]) -> str:
    """Best-effort canonical path resolving symlinks/junctions and case."""
    p = os.path.realpath(os.path.abspath(str(path)))
    if os.name == "nt":
        # NTFS is case-insensitive: normalise for containment checks.
        p = os.path.normcase(p)
    return os.path.normpath(p)


def assert_inside_root(target: str | os.PathLike[str], root: str | os.PathLike[str]) -> str:
    """Return canonical target if it is strictly inside canonical root.

    Raises AssertionError (fail-closed) when the target escapes the root via
    ``..``, symlink/junction, or absolute-path tricks.
    """
    c_root = canonical(root)
    c_target = canonical(target)
    if c_target == c_root or not c_target.startswith(c_root + os.sep):
        raise AssertionError(f"refusing target outside test root: {target!r} (root={root!r})")
    return c_target


def assert_all_inside_root(targets: Iterable[str | os.PathLike[str]], root: str | os.PathLike[str]) -> List[str]:
    return [assert_inside_root(t, root) for t in targets]


def sha256_file(path: str | os.PathLike[str]) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(CHUNK)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def files_byte_equal(a: str | os.PathLike[str], b: str | os.PathLike[str]) -> bool:
    """Independent byte-equality oracle: size pre-check + full streaming compare."""
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
    except OSError:
        return False
    # filecmp with shallow=False does a full byte read; keep the explicit
    # streaming check as well so the oracle does not depend on one helper.
    if not filecmp.cmp(str(a), str(b), shallow=False):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            ba = fa.read(CHUNK)
            bb = fb.read(CHUNK)
            if ba != bb:
                return False
            if not ba:
                return True


def file_identity(path: str | os.PathLike[str]) -> Tuple[int, int]:
    """(st_dev, st_ino) identity; (0, 0) when the platform gives no inode."""
    st = os.stat(str(path))
    try:
        return (int(st.st_dev), int(st.st_ino or 0))
    except Exception:
        return (0, 0)


def write_bytes(path: str | os.PathLike[str], data: bytes) -> str:
    p = Path(str(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return str(p)


def write_text(path: str | os.PathLike[str], text: str) -> str:
    p = Path(str(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return str(p)


def snapshot_manifest(root: str | os.PathLike[str]) -> Dict[str, Dict[str, object]]:
    """Manifest of every regular file under root: sha256/size/file-id/mtime."""
    out: Dict[str, Dict[str, object]] = {}
    for dirpath, _dirnames, filenames in os.walk(str(root), followlinks=False):
        for name in filenames:
            full = os.path.join(dirpath, name)
            # Skip symlink files themselves for the byte manifest (record link).
            try:
                if os.path.islink(full):
                    out[os.path.relpath(full, str(root))] = {
                        "symlink": True,
                        "target": os.readlink(full),
                    }
                    continue
                st = os.stat(full)
                out[os.path.relpath(full, str(root))] = {
                    "sha256": sha256_file(full),
                    "size": int(st.st_size),
                    "mtime": float(st.st_mtime),
                    "file_id": (int(st.st_dev), int(getattr(st, "st_ino", 0) or 0)),
                    "nlink": int(getattr(st, "st_nlink", 0) or 0),
                }
            except OSError:
                continue
    return out


def group_key_members(results: Mapping[Any, List[str]]) -> List[frozenset]:
    """Normalise worker result groups to a set of frozensets of canonical paths."""
    groups = []
    for _key, paths in (results or {}).items():
        members = frozenset(canonical(p) for p in (paths or []))
        if len(members) >= 2:
            groups.append(members)
    return groups


def find_group_containing(groups: List[frozenset], *members: str) -> frozenset | None:
    wanted = frozenset(canonical(m) for m in members)
    for g in groups:
        if wanted.issubset(g):
            return g
    return None
