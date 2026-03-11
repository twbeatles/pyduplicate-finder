"""
File lock detection helpers.

Checks whether files are currently unavailable because another process holds a lock.
"""

from __future__ import annotations

import os
import platform
from typing import List, Tuple


class FileLockChecker:
    """Check whether a file appears to be locked by another process."""

    def __init__(self):
        self.is_windows = platform.system() == "Windows"

    def is_file_locked(self, path: str) -> bool:
        """Return True when the file appears locked/unavailable."""
        if not os.path.exists(path):
            return False

        if os.path.isdir(path):
            return False

        try:
            if self.is_windows:
                import msvcrt

                with open(path, "r+b") as f:
                    try:
                        # 0-byte files cannot be reliably byte-locked with length=1.
                        # If open() succeeded, treat that case as unlocked.
                        f.seek(0, os.SEEK_END)
                        if f.tell() > 0:
                            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        return False
                    except (IOError, OSError):
                        return True
            else:
                import fcntl

                with open(path, "r+b") as f:
                    try:
                        flock = getattr(fcntl, "flock", None)
                        lock_ex = getattr(fcntl, "LOCK_EX", 0)
                        lock_nb = getattr(fcntl, "LOCK_NB", 0)
                        lock_un = getattr(fcntl, "LOCK_UN", 0)
                        if flock is None:
                            return False
                        flock(f.fileno(), lock_ex | lock_nb)
                        flock(f.fileno(), lock_un)
                        return False
                    except (IOError, OSError):
                        return True
        except PermissionError:
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return True

    def check_files(self, paths: List[str]) -> List[Tuple[str, bool]]:
        """Check lock status for multiple files."""
        results = []
        for path in paths:
            locked = self.is_file_locked(path)
            results.append((path, locked))
        return results

    def get_locked_files(self, paths: List[str]) -> List[str]:
        """Return only locked files from the provided list."""
        return [path for path, locked in self.check_files(paths) if locked]

    def get_unlocked_files(self, paths: List[str]) -> List[str]:
        """Return only unlocked files from the provided list."""
        return [path for path, locked in self.check_files(paths) if not locked]

    def get_locking_processes(self, path: str, max_results: int = 5, timeout_seconds: float = 2.0) -> List[str]:
        """Best-effort process listing for Windows lock holders."""
        if not self.is_windows:
            return []

        try:
            import psutil
            import time

            abs_path = os.path.abspath(path).lower()
            locking_procs = []
            start_time = time.time()

            for proc in psutil.process_iter(["pid", "name"]):
                if time.time() - start_time > timeout_seconds:
                    break

                if len(locking_procs) >= max_results:
                    break

                try:
                    for f in proc.open_files():
                        if f.path.lower() == abs_path:
                            locking_procs.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
                            break
                except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue

            return locking_procs
        except ImportError:
            return []
        except Exception:
            return []


def check_single_file(path: str) -> bool:
    """Convenience function to check lock status for a single file."""
    checker = FileLockChecker()
    return checker.is_file_locked(path)
