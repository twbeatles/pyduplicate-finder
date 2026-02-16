import os
import shutil
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Callable, Tuple

from src.utils.i18n import strings


SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_BLOCK = "block"


@dataclass(frozen=True)
class PreflightIssue:
    path: str
    severity: str
    code: str
    message: str


@dataclass
class PreflightReport:
    op_type: str
    issues: List[PreflightIssue] = field(default_factory=list)
    eligible_paths: List[str] = field(default_factory=list)
    bytes_total: int = 0
    bytes_saved_est: int = 0
    meta: Dict[str, object] = field(default_factory=dict)

    @property
    def has_blockers(self) -> bool:
        return any(i.severity == SEVERITY_BLOCK for i in self.issues)

    def summary_counts(self) -> Dict[str, int]:
        out = {SEVERITY_BLOCK: 0, SEVERITY_WARN: 0, SEVERITY_INFO: 0}
        for i in self.issues:
            out[i.severity] = out.get(i.severity, 0) + 1
        return out


def _same_volume(a: str, b: str) -> bool:
    if os.name == "nt":
        da = os.path.splitdrive(os.path.abspath(a))[0].lower()
        db = os.path.splitdrive(os.path.abspath(b))[0].lower()
        return bool(da) and (da == db)
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except Exception:
        return False


def _is_same_inode(a: str, b: str) -> bool:
    try:
        sa = os.stat(a)
        sb = os.stat(b)
        if not sa.st_ino or not sb.st_ino:
            return False
        return sa.st_ino == sb.st_ino and sa.st_dev == sb.st_dev
    except Exception:
        return False


class PreflightAnalyzer:
    def __init__(self, *, lock_checker=None):
        self.lock_checker = lock_checker

    def analyze_delete(self, paths: List[str], *, quarantine_dir: Optional[str] = None) -> PreflightReport:
        rep = PreflightReport(op_type="delete_quarantine")
        existing = []
        total_bytes = 0

        for p in paths or []:
            if not p:
                continue
            if not os.path.exists(p):
                rep.issues.append(PreflightIssue(p, SEVERITY_WARN, "missing", strings.tr("pf_missing")))
                continue
            if os.path.isdir(p):
                rep.issues.append(PreflightIssue(p, SEVERITY_BLOCK, "is_dir", strings.tr("pf_is_dir")))
                continue
            try:
                size = os.path.getsize(p)
                total_bytes += int(size)
                existing.append(p)
            except Exception:
                rep.issues.append(PreflightIssue(p, SEVERITY_WARN, "stat_failed", strings.tr("pf_stat_failed")))
                continue

            if self.lock_checker:
                try:
                    if self.lock_checker.is_file_locked(p):
                        rep.issues.append(PreflightIssue(p, SEVERITY_WARN, "locked", strings.tr("pf_locked")))
                except Exception:
                    pass

        rep.bytes_total = total_bytes
        rep.eligible_paths = existing

        if not existing:
            rep.issues.append(PreflightIssue("", SEVERITY_BLOCK, "no_eligible", strings.tr("pf_no_eligible")))
            return rep

        # Best-effort disk space check for quarantine moves.
        if quarantine_dir:
            try:
                usage = shutil.disk_usage(quarantine_dir)
                # Add a small margin.
                required = int(total_bytes * 1.05)
                if usage.free < required:
                    rep.issues.append(
                        PreflightIssue(
                            quarantine_dir,
                            SEVERITY_BLOCK,
                            "disk_space",
                            strings.tr("pf_disk_space").format(required=required),
                        )
                    )
            except Exception:
                pass

        return rep

    def analyze_delete_trash(self, paths: List[str]) -> PreflightReport:
        rep = PreflightReport(op_type="delete_trash")
        existing = []
        for p in paths or []:
            if not p:
                continue
            if not os.path.exists(p):
                rep.issues.append(PreflightIssue(p, SEVERITY_WARN, "missing", strings.tr("pf_missing")))
                continue
            if os.path.isdir(p):
                rep.issues.append(PreflightIssue(p, SEVERITY_BLOCK, "is_dir", strings.tr("pf_is_dir")))
                continue
            existing.append(p)
            if self.lock_checker:
                try:
                    if self.lock_checker.is_file_locked(p):
                        rep.issues.append(PreflightIssue(p, SEVERITY_WARN, "locked", strings.tr("pf_locked")))
                except Exception:
                    pass
        rep.eligible_paths = existing
        if not existing:
            rep.issues.append(PreflightIssue("", SEVERITY_BLOCK, "no_eligible", strings.tr("pf_no_eligible")))
        return rep

    def analyze_restore(self, quarantine_items: List[Dict[str, object]]) -> PreflightReport:
        rep = PreflightReport(op_type="restore")
        eligible = []
        for it in quarantine_items or []:
            orig = str(it.get("orig_path") or "")
            qpath = str(it.get("quarantine_path") or "")
            status = str(it.get("status") or "")
            if status != "quarantined":
                rep.issues.append(PreflightIssue(orig, SEVERITY_WARN, "not_quarantined", strings.tr("pf_not_quarantined")))
                continue
            if not qpath or not os.path.exists(qpath):
                rep.issues.append(
                    PreflightIssue(orig, SEVERITY_BLOCK, "missing_quarantine_file", strings.tr("pf_missing_quarantine_file"))
                )
                continue
            if os.path.exists(orig):
                rep.issues.append(PreflightIssue(orig, SEVERITY_WARN, "dest_exists", strings.tr("pf_dest_exists")))
            eligible.append(orig)
        rep.eligible_paths = eligible
        if not eligible:
            rep.issues.append(PreflightIssue("", SEVERITY_BLOCK, "no_eligible", strings.tr("pf_no_eligible_restore")))
        return rep

    def analyze_purge(self, quarantine_items: List[Dict[str, object]]) -> PreflightReport:
        rep = PreflightReport(op_type="purge")
        eligible = []
        for it in quarantine_items or []:
            orig = str(it.get("orig_path") or "")
            qpath = str(it.get("quarantine_path") or "")
            status = str(it.get("status") or "")
            if status != "quarantined":
                rep.issues.append(PreflightIssue(orig, SEVERITY_WARN, "not_quarantined", strings.tr("pf_not_quarantined")))
                continue
            if not qpath or not os.path.exists(qpath):
                rep.issues.append(
                    PreflightIssue(orig, SEVERITY_WARN, "missing_quarantine_file", strings.tr("pf_missing_quarantine_file_purge"))
                )
            eligible.append(orig)
        rep.eligible_paths = eligible
        if not eligible:
            rep.issues.append(PreflightIssue("", SEVERITY_BLOCK, "no_eligible", strings.tr("pf_no_eligible_purge")))
        return rep

    def analyze_hardlink(self, canonical: str, targets: List[str]) -> PreflightReport:
        rep = PreflightReport(op_type="hardlink_consolidate")
        if not canonical or not os.path.exists(canonical) or os.path.isdir(canonical):
            rep.issues.append(PreflightIssue(canonical or "", SEVERITY_BLOCK, "canonical_missing", strings.tr("pf_canonical_missing")))
            return rep

        eligible = []
        bytes_saved = 0

        for t in targets or []:
            if not t:
                continue
            if not os.path.exists(t):
                rep.issues.append(PreflightIssue(t, SEVERITY_WARN, "missing", strings.tr("pf_target_missing")))
                continue
            if os.path.isdir(t):
                rep.issues.append(PreflightIssue(t, SEVERITY_BLOCK, "is_dir", strings.tr("pf_is_dir")))
                continue
            if not _same_volume(canonical, t):
                rep.issues.append(PreflightIssue(t, SEVERITY_WARN, "cross_volume", strings.tr("pf_cross_volume")))
                continue
            if _is_same_inode(canonical, t):
                rep.issues.append(PreflightIssue(t, SEVERITY_INFO, "already_linked", strings.tr("pf_already_linked")))
                continue
            if self.lock_checker:
                try:
                    if self.lock_checker.is_file_locked(t):
                        rep.issues.append(PreflightIssue(t, SEVERITY_WARN, "locked", strings.tr("pf_locked")))
                except Exception:
                    pass
            try:
                bytes_saved += int(os.path.getsize(t))
            except Exception:
                pass
            eligible.append(t)

        rep.eligible_paths = eligible
        rep.bytes_saved_est = bytes_saved

        if not eligible:
            rep.issues.append(PreflightIssue("", SEVERITY_BLOCK, "no_eligible", strings.tr("pf_no_eligible_hardlink")))
        return rep
