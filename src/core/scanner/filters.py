from __future__ import annotations

from .common import fnmatch, os, platform


class ScanFilterMixin:
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
