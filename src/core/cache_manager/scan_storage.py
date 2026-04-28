from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from src.core.scan_types import normalize_exemption_status

from .contracts import CacheManagerHost

logger = logging.getLogger(__name__)


class CacheScanStorageMixin(CacheManagerHost):
    def save_scan_files_batch(self, session_id: int, entries):
        if not session_id or not entries:
            return
        try:
            conn = self._get_conn()
            with conn:
                cursor = conn.cursor()
                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO scan_files (session_id, path, size, mtime)
                    VALUES (?, ?, ?, ?)
                    """,
                    [(session_id, p, s, m) for p, s, m in entries],
                )
        except Exception:
            logger.exception("Save scan files error")

    def save_scan_dirs_batch(self, session_id: int, entries):
        if not session_id or not entries:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO scan_dirs (session_id, path, mtime)
                    VALUES (?, ?, ?)
                    """,
                    [(session_id, p, m) for p, m in entries if p],
                )
        except Exception:
            logger.exception("Save scan dirs error")

    def load_scan_dirs(self, session_id: int):
        out = {}
        if not session_id:
            return out
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT path, mtime FROM scan_dirs WHERE session_id=?", (session_id,))
            for p, m in cursor.fetchall():
                out[p] = m
        except Exception:
            logger.exception("Load scan dirs error")
        return out

    def clear_scan_dirs(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_dirs WHERE session_id=?", (session_id,))
        except Exception:
            logger.exception("Clear scan dirs error")

    def save_scan_folder_sigs_batch(self, session_id: int, entries):
        if not session_id or not entries:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO scan_folder_sigs
                    (session_id, dir_path, sig_quick, sig_full, bytes_total, file_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [(session_id, d, sq, sf, bt, fc) for d, sq, sf, bt, fc in entries if d],
                )
        except Exception:
            logger.exception("Save scan folder sigs error")

    def load_scan_files(self, session_id: int):
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT path, size, mtime FROM scan_files WHERE session_id=?", (session_id,))
            return cursor.fetchall()
        except Exception:
            logger.exception("Load scan files error")
            return []

    def has_scan_files(self, session_id: int) -> bool:
        if not session_id:
            return False
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM scan_files WHERE session_id=? LIMIT 1", (session_id,))
            return cursor.fetchone() is not None
        except Exception:
            return False

    def iter_scan_files(self, session_id: int, batch_size: int = 5000):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT path, size, mtime FROM scan_files WHERE session_id=?", (session_id,))
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    yield row
        except Exception:
            logger.exception("Iter scan files error")

    def load_scan_hashes_for_paths(self, session_id: int, paths, hash_type: Optional[str] = None):
        result = {}
        if not session_id or not paths:
            return result

        chunk_size = 400
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            path_list = list(paths)
            for i in range(0, len(path_list), chunk_size):
                chunk = path_list[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                if hash_type:
                    cursor.execute(
                        f"""
                        SELECT path, size, mtime, hash_type, hash_value
                        FROM scan_hashes
                        WHERE session_id=? AND hash_type=? AND path IN ({placeholders})
                        """,
                        [session_id, hash_type, *chunk],
                    )
                else:
                    cursor.execute(
                        f"""
                        SELECT path, size, mtime, hash_type, hash_value
                        FROM scan_hashes
                        WHERE session_id=? AND path IN ({placeholders})
                        """,
                        [session_id, *chunk],
                    )
                for path, size, mtime, htype, hval in cursor.fetchall():
                    result[(path, htype)] = (hval, size, mtime)
        except Exception:
            logger.exception("Load scan hashes for paths error")
        return result

    def clear_scan_files(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_files WHERE session_id=?", (session_id,))
        except Exception:
            logger.exception("Clear scan files error")

    def remove_scan_files(self, session_id: int, paths):
        if not session_id or not paths:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.executemany("DELETE FROM scan_files WHERE session_id=? AND path=?", [(session_id, p) for p in paths])
        except Exception:
            logger.exception("Remove scan files error")

    def save_scan_hashes_batch(self, session_id: int, entries):
        if not session_id or not entries:
            return
        try:
            conn = self._get_conn()
            with conn:
                cursor = conn.cursor()
                cursor.executemany(
                    """
                    INSERT OR REPLACE INTO scan_hashes (session_id, path, size, mtime, hash_type, hash_value)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [(session_id, p, s, m, t, v) for p, s, m, t, v in entries],
                )
        except Exception:
            logger.exception("Save scan hashes error")

    def load_scan_hashes(self, session_id: int, hash_type: Optional[str] = None):
        result = {}
        if not session_id:
            return result
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            if hash_type:
                cursor.execute(
                    """
                    SELECT path, size, mtime, hash_type, hash_value
                    FROM scan_hashes WHERE session_id=? AND hash_type=?
                    """,
                    (session_id, hash_type),
                )
            else:
                cursor.execute(
                    """
                    SELECT path, size, mtime, hash_type, hash_value
                    FROM scan_hashes WHERE session_id=?
                    """,
                    (session_id,),
                )
            for path, size, mtime, htype, hval in cursor.fetchall():
                result[(path, htype)] = (hval, size, mtime)
        except Exception:
            logger.exception("Load scan hashes error")
        return result

    def clear_scan_hashes(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_hashes WHERE session_id=?", (session_id,))
        except Exception:
            logger.exception("Clear scan hashes error")

    def clear_scan_results(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_results WHERE session_id=?", (session_id,))
                conn.execute("DELETE FROM scan_file_state WHERE session_id=?", (session_id,))
        except Exception:
            logger.exception("Clear scan results error")

    def save_scan_results(self, session_id: int, results: dict[Any, list[str]]):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_results WHERE session_id=?", (session_id,))
                entries = []
                for key, paths in results.items():
                    key_str = json.dumps(key, ensure_ascii=False)
                    for path in paths:
                        entries.append((session_id, key_str, path))
                if entries:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO scan_results (session_id, group_key, path)
                        VALUES (?, ?, ?)
                        """,
                        entries,
                    )
        except Exception:
            logger.exception("Save scan results error")

    def _normalize_scan_file_state_entries(self, entries) -> list[tuple]:
        rows = []
        if isinstance(entries, dict):
            iterator = entries.items()
        else:
            iterator = []
            try:
                iterator = [(row.get("path"), row) for row in (entries or []) if isinstance(row, dict)]
            except Exception:
                iterator = []

        now = time.time()
        for path, row in iterator:
            try:
                path_str = str(path or row.get("path") or "")
                if not path_str:
                    continue
                size_value = row.get("size")
                mtime_value = row.get("mtime")
                exists_raw = row.get("exists")
                exists_value = None if exists_raw is None else (1 if bool(exists_raw) else 0)
                delta = str(row.get("baseline_delta") or "")
                if delta not in {"new", "changed", "revalidated"}:
                    delta = ""
                rows.append(
                    (
                        path_str,
                        int(size_value) if size_value is not None else None,
                        float(mtime_value) if mtime_value is not None else None,
                        exists_value,
                        str(row.get("selection_reason") or ""),
                        normalize_exemption_status(row.get("exemption_status")),
                        str(row.get("review_state") or ""),
                        str(row.get("collection_role") or ""),
                        delta,
                        now,
                    )
                )
            except Exception:
                continue
        return rows

    def save_scan_file_state(self, session_id: int, entries) -> None:
        if not session_id:
            return
        rows = self._normalize_scan_file_state_entries(entries)
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_file_state WHERE session_id=?", (session_id,))
                if rows:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO scan_file_state
                        (
                            session_id, path, size, mtime, file_exists, selection_reason,
                            exemption_status, review_state, collection_role,
                            baseline_delta, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [(session_id, *row) for row in rows],
                    )
        except Exception:
            logger.exception("Save scan file state error")

    def load_scan_file_state(self, session_id: int) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        if not session_id:
            return out
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT path, size, mtime, file_exists, selection_reason, exemption_status,
                       review_state, collection_role, baseline_delta
                FROM scan_file_state
                WHERE session_id=?
                """,
                (session_id,),
            )
            for path, size, mtime, exists, reason, status, review, role, delta in cursor.fetchall():
                path_str = str(path or "")
                if not path_str:
                    continue
                row: dict[str, Any] = {
                    "selection_reason": str(reason or ""),
                    "exemption_status": normalize_exemption_status(status),
                    "review_state": str(review or ""),
                    "collection_role": str(role or ""),
                    "baseline_delta": str(delta or "") if str(delta or "") in {"new", "changed", "revalidated"} else "",
                }
                if size is not None:
                    row["size"] = int(size)
                if mtime is not None:
                    row["mtime"] = float(mtime)
                if exists is not None:
                    row["exists"] = bool(exists)
                out[path_str] = row
        except Exception:
            logger.exception("Load scan file state error")
        return out

    def load_scan_results(self, session_id: int):
        results = {}
        if not session_id:
            return results
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT group_key, path FROM scan_results
                WHERE session_id=?
                ORDER BY group_key
                """,
                (session_id,),
            )
            for group_key, path in cursor.fetchall():
                try:
                    key = tuple(json.loads(group_key))
                except Exception:
                    key = (group_key,)
                results.setdefault(key, []).append(path)
        except Exception:
            logger.exception("Load scan results error")
        return results

    def save_selected_paths(self, session_id: int, paths):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_selected WHERE session_id=?", (session_id,))
                if paths:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO scan_selected (session_id, path, selected)
                        VALUES (?, ?, 1)
                        """,
                        [(session_id, p) for p in paths],
                    )
        except Exception:
            logger.exception("Save selected paths error")

    def save_selected_paths_delta(self, session_id: int, add_paths=None, remove_paths=None):
        if not session_id:
            return
        add_values = [p for p in (add_paths or []) if p]
        remove_values = [p for p in (remove_paths or []) if p]
        if not add_values and not remove_values:
            return
        try:
            conn = self._get_conn()
            with conn:
                if add_values:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO scan_selected (session_id, path, selected)
                        VALUES (?, ?, 1)
                        """,
                        [(session_id, p) for p in add_values],
                    )
                if remove_values:
                    conn.executemany(
                        "DELETE FROM scan_selected WHERE session_id=? AND path=?",
                        [(session_id, p) for p in remove_values],
                    )
        except Exception:
            logger.exception("Save selected delta error")

    def load_selected_paths(self, session_id: int):
        if not session_id:
            return set()
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT path FROM scan_selected
                WHERE session_id=? AND selected=1
                """,
                (session_id,),
            )
            return {row[0] for row in cursor.fetchall()}
        except Exception:
            logger.exception("Load selected paths error")
            return set()

    def clear_selected_paths(self, session_id: int):
        if not session_id:
            return
        try:
            conn = self._get_conn()
            with conn:
                conn.execute("DELETE FROM scan_selected WHERE session_id=?", (session_id,))
        except Exception:
            logger.exception("Clear selected paths error")
