import os
import shutil
import uuid
import time
from dataclasses import dataclass
from typing import Callable, Optional, List, Dict, Tuple
from src.utils.i18n import strings


def _safe_filename(name: str) -> str:
    # Keep it simple and filesystem-friendly.
    keep = []
    for ch in (name or ""):
        if ch.isalnum() or ch in (" ", ".", "-", "_", "(", ")", "[", "]"):
            keep.append(ch)
        else:
            keep.append("_")
    out = "".join(keep).strip()
    return out or "file"


def _conflict_restore_path(orig_path: str, *, max_attempts: int = 16) -> str:
    base, ext = os.path.splitext(orig_path)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    attempts = max(1, int(max_attempts or 1))
    for _ in range(attempts):
        suffix = uuid.uuid4().hex[:8]
        candidate = f"{base}.restored-{stamp}-{suffix}{ext}"
        if not os.path.exists(candidate):
            return candidate
    return f"{base}.restored-{stamp}-{uuid.uuid4().hex}{ext}"


@dataclass(frozen=True)
class QuarantineMoveResult:
    item_id: int
    orig_path: str
    quarantine_path: str
    size: int
    mtime: float


class QuarantineManager:
    """
    Persistent quarantine:
    - Moves files into a per-user quarantine directory
    - Records items in CacheManager.quarantine_items
    - Supports restore/purge + retention
    """

    def __init__(self, cache_manager, quarantine_dir: Optional[str] = None):
        self.cache_manager = cache_manager
        self._quarantine_dir = quarantine_dir

    def get_quarantine_dir(self) -> str:
        if self._quarantine_dir:
            qdir = self._quarantine_dir
        else:
            base = os.path.dirname(os.path.abspath(getattr(self.cache_manager, "db_path", "") or os.getcwd()))
            qdir = os.path.join(base, "quarantine")
        os.makedirs(qdir, exist_ok=True)
        return qdir

    def move_to_quarantine(
        self,
        paths: List[str],
        *,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        check_cancel: Optional[Callable[[], bool]] = None,
    ) -> Tuple[List[QuarantineMoveResult], List[Tuple[str, str]]]:
        """
        Returns: (moved, failures)
        failures: [(path, reason)]
        """
        moved: List[QuarantineMoveResult] = []
        failures: List[Tuple[str, str]] = []
        qdir = self.get_quarantine_dir()

        total = len(paths or [])
        for idx, p in enumerate(paths or []):
            if check_cancel and check_cancel():
                break
            msg = f"{idx + 1}/{total}"
            if progress_callback:
                progress_callback(idx + 1, total, msg)

            try:
                if not p or (not os.path.exists(p)):
                    failures.append((p, "missing"))
                    continue
                if os.path.isdir(p):
                    failures.append((p, "is_dir"))
                    continue

                st = os.stat(p)
                size = int(st.st_size)
                mtime = float(st.st_mtime)

                fname = _safe_filename(os.path.basename(p))
                unique = f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{fname}"
                qpath = os.path.join(qdir, unique)
                shutil.move(p, qpath)

                item_id = int(
                    self.cache_manager.insert_quarantine_item(
                        orig_path=p,
                        quarantine_path=qpath,
                        size=size,
                        mtime=mtime,
                        status="quarantined",
                    )
                    or 0
                )
                if item_id <= 0:
                    rollback_reason = "db_insert_failed"
                    try:
                        parent = os.path.dirname(p)
                        if parent and not os.path.exists(parent):
                            os.makedirs(parent, exist_ok=True)
                        shutil.move(qpath, p)
                        rollback_reason = "db_insert_failed_rolled_back"
                    except Exception:
                        rollback_reason = "db_insert_failed_and_rollback_failed"
                    failures.append((p, rollback_reason))
                    continue

                moved.append(
                    QuarantineMoveResult(
                        item_id=item_id,
                        orig_path=p,
                        quarantine_path=qpath,
                        size=size,
                        mtime=mtime,
                    )
                )
            except Exception as e:
                failures.append((p, str(e)))

        return moved, failures

    def restore_item(
        self,
        item_id: int,
        *,
        allow_replace_hardlink_to: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Restore a quarantined item back to its original path.
        Returns: (success, message, restored_path)
        """
        item = self.cache_manager.get_quarantine_item(item_id)
        if not item:
            return False, strings.tr("qm_item_not_found"), None
        if item.get("status") != "quarantined":
            return False, strings.tr("qm_item_not_quarantined"), None

        orig_path = item.get("orig_path")
        qpath = item.get("quarantine_path")
        if not qpath or not os.path.exists(qpath):
            return False, strings.tr("qm_quarantine_file_missing"), None

        try:
            parent = os.path.dirname(orig_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)

            dest = orig_path
            if os.path.exists(dest):
                # Optional: if dest is a hardlink to the given canonical file, replace it (undo hardlink).
                replaced = False
                if allow_replace_hardlink_to and os.path.exists(allow_replace_hardlink_to):
                    try:
                        st_dest = os.stat(dest)
                        st_can = os.stat(allow_replace_hardlink_to)
                        if (st_dest.st_ino and st_can.st_ino) and (st_dest.st_ino == st_can.st_ino) and (st_dest.st_dev == st_can.st_dev):
                            os.remove(dest)
                            replaced = True
                    except Exception:
                        replaced = False

                if not replaced:
                    dest = _conflict_restore_path(orig_path)

            shutil.move(qpath, dest)
            self.cache_manager.update_quarantine_item_status(item_id, "restored")
            return True, strings.tr("qm_restored"), dest
        except Exception as e:
            return False, str(e), None

    def purge_item(self, item_id: int) -> Tuple[bool, str]:
        """Permanently delete the quarantined file and mark as purged."""
        item = self.cache_manager.get_quarantine_item(item_id)
        if not item:
            return False, strings.tr("qm_item_not_found")
        if item.get("status") != "quarantined":
            return False, strings.tr("qm_item_not_quarantined")
        qpath = item.get("quarantine_path")
        try:
            if qpath and os.path.exists(qpath):
                os.remove(qpath)
            self.cache_manager.update_quarantine_item_status(item_id, "purged")
            return True, strings.tr("qm_purged")
        except Exception as e:
            return False, str(e)

    def apply_retention(self, *, max_days: int, max_bytes: int) -> List[int]:
        """
        Purge oldest quarantined items until both constraints are satisfied.
        Returns list of purged item_ids.
        """
        purged: List[int] = []
        try:
            max_days = int(max_days)
            max_bytes = int(max_bytes)
        except Exception:
            return purged

        now = time.time()
        items = self.cache_manager.list_quarantine_items(limit=5000, offset=0, status_filter="quarantined")
        # Oldest first for purging.
        items_sorted = sorted(items, key=lambda x: float(x.get("created_at") or 0.0))

        def total_size(it_list: List[Dict]) -> int:
            s = 0
            for it in it_list:
                try:
                    s += int(it.get("size") or 0)
                except Exception:
                    pass
            return s

        current_total = total_size(items_sorted)

        for it in items_sorted:
            created = float(it.get("created_at") or 0.0)
            age_days = (now - created) / 86400.0 if created else 0.0
            over_age = (max_days > 0) and (age_days > max_days)
            over_size = (max_bytes > 0) and (current_total > max_bytes)

            if not (over_age or over_size):
                break

            item_id = int(it.get("id") or 0)
            ok, _ = self.purge_item(item_id)
            if ok:
                purged.append(item_id)
                try:
                    current_total -= int(it.get("size") or 0)
                except Exception:
                    pass

        return purged
