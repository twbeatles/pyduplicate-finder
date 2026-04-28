from __future__ import annotations

from .common import fnmatch, os, platform
from .contracts import ScanWorkerHost
from src.core.scan_types import (
    COLLECTION_ROLE_NONE,
    EXEMPTION_ACTION_IGNORE,
    EXEMPTION_ACTION_SAFELIST,
    EXEMPTION_STATUS_IGNORE,
    EXEMPTION_STATUS_SAFELISTED,
    EXEMPTION_KIND_EXACT_PATH,
    EXEMPTION_KIND_PATH_GLOB,
)


class ScanFilterMixin(ScanWorkerHost):
    def _init_protected_paths(self):
        self.protected_paths = []
        if self.protect_system:
            if platform.system() == "Windows":
                sys_drive = os.environ.get("SystemDrive", "C:")
                candidates = [
                    os.environ.get("WINDIR") or os.environ.get("SystemRoot"),
                    os.environ.get("ProgramFiles"),
                    os.environ.get("ProgramFiles(x86)"),
                    os.environ.get("ProgramData"),
                    os.path.join(sys_drive + os.sep, "Windows"),
                    os.path.join(sys_drive + os.sep, "Program Files"),
                    os.path.join(sys_drive + os.sep, "Program Files (x86)"),
                    os.path.join(sys_drive + os.sep, "ProgramData"),
                ]
                self.protected_paths = [p for p in candidates if p]
            else:
                self.protected_paths = [
                    "/bin",
                    "/boot",
                    "/dev",
                    "/etc",
                    "/lib",
                    "/lib64",
                    "/proc",
                    "/root",
                    "/run",
                    "/sbin",
                    "/sys",
                    "/usr",
                    "/var",
                ]
            self.protected_paths = [self._normalize_path(p) for p in self.protected_paths]

    def _normalize_path(self, path: str) -> str:
        path = os.path.abspath(path)
        path = os.path.normpath(path)
        return os.path.normcase(path) if os.name == "nt" else path

    def is_protected(self, path):
        if not self.protect_system:
            return False
        try:
            norm_path = self._normalize_path(path)
            for p in self.protected_paths:
                try:
                    if os.path.commonpath([norm_path, p]) == p:
                        return True
                except ValueError:
                    continue
        except Exception:
            return False
        return False

    def _normalize_match(self, value: str) -> str:
        normalized = os.path.normpath(value).replace("\\", "/")
        if os.name == "nt":
            return normalized.lower()
        return normalized

    def _prepare_patterns(self, patterns):
        prepared = []
        for pattern in patterns or []:
            if not pattern:
                continue
            pattern_str = str(pattern)
            name_match = pattern_str.lower() if os.name == "nt" else pattern_str
            path_match = self._normalize_match(pattern_str)
            prepared.append((name_match, path_match))
        return prepared

    def _matches_any_pattern(self, path: str, matchers) -> bool:
        if not matchers:
            return False
        name = os.path.basename(path)
        name_match = name.lower() if os.name == "nt" else name
        path_match = self._normalize_match(path)

        for name_pat, path_pat in matchers:
            if fnmatch.fnmatchcase(name_match, name_pat):
                return True
            if fnmatch.fnmatchcase(path_match, path_pat):
                return True
        return False

    def _should_exclude(self, path: str) -> bool:
        return self._matches_any_pattern(path, self._exclude_matchers)

    def _should_include(self, path: str) -> bool:
        if not self._include_matchers:
            return True
        return self._matches_any_pattern(path, self._include_matchers)

    def _is_hidden_or_system_name(self, name: str) -> bool:
        if not name:
            return False
        n = name.lower() if os.name == "nt" else name
        if n.startswith("."):
            return True
        if n in ("thumbs.db", "desktop.ini", ".ds_store"):
            return True
        return False

    def _dir_key(self, path: str):
        try:
            st = os.stat(path, follow_symlinks=True)
            if getattr(st, "st_ino", 0):
                return (st.st_dev, st.st_ino)
        except Exception:
            pass
        try:
            return self._normalize_path(os.path.realpath(path))
        except Exception:
            return self._normalize_path(path)

    def _record_scan_dir(self, dir_path: str, mtime=None) -> None:
        try:
            norm = self._normalize_path(dir_path)
            if mtime is None:
                mtime = os.path.getmtime(dir_path)
            self._current_scan_dirs[norm] = float(mtime)
        except Exception:
            pass

    def _save_scan_dirs_snapshot(self) -> None:
        if not self.session_id:
            return
        try:
            merged = dict(self._base_scan_dirs or {})
            merged.update(self._current_scan_dirs or {})
            entries = [(p, m) for p, m in merged.items() if p]
            self.cache_manager.clear_scan_dirs(self.session_id)
            self.cache_manager.save_scan_dirs_batch(self.session_id, entries)
        except Exception:
            pass

    def _resolve_collection_role(self, path: str) -> str:
        if not path:
            return COLLECTION_ROLE_NONE
        norm_path = self._normalize_path(path)
        best_role = COLLECTION_ROLE_NONE
        best_len = -1
        for folder, role in (self.folder_roles or {}).items():
            try:
                norm_folder = self._normalize_path(folder)
                if os.path.commonpath([norm_path, norm_folder]) == norm_folder and len(norm_folder) > best_len:
                    best_role = str(role or COLLECTION_ROLE_NONE)
                    best_len = len(norm_folder)
            except Exception:
                continue
        return best_role

    def _match_path_exemption(self, path: str):
        if not self.apply_exemptions:
            return None
        norm_path = self._normalize_path(path)
        base = os.path.basename(norm_path)
        for rule in self._exemption_rules or []:
            if rule.kind == EXEMPTION_KIND_EXACT_PATH and self._normalize_path(rule.value) == norm_path:
                return rule
            if rule.kind == EXEMPTION_KIND_PATH_GLOB:
                pat = self._normalize_match(rule.value)
                if fnmatch.fnmatchcase(self._normalize_match(norm_path), pat) or fnmatch.fnmatchcase(base.lower() if os.name == "nt" else base, rule.value.lower() if os.name == "nt" else rule.value):
                    return rule
        return None

    def _should_ignore_path(self, path: str) -> bool:
        rule = self._match_path_exemption(path)
        if not rule:
            return False
        status = EXEMPTION_STATUS_SAFELISTED if rule.action == EXEMPTION_ACTION_SAFELIST else EXEMPTION_STATUS_IGNORE
        self._path_exemption_status[str(path)] = status
        return rule.action == EXEMPTION_ACTION_IGNORE

    def _mark_path_exemption_status(self, path: str) -> None:
        rule = self._match_path_exemption(path)
        if not rule:
            return
        self._path_exemption_status[str(path)] = (
            EXEMPTION_STATUS_SAFELISTED if rule.action == EXEMPTION_ACTION_SAFELIST else EXEMPTION_STATUS_IGNORE
        )
