import builtins
import os

from src.core.file_lock_checker import FileLockChecker


def test_zero_byte_file_does_not_bypass_lock_check_when_open_is_denied(tmp_path, monkeypatch):
    path = tmp_path / "zero.txt"
    path.write_bytes(b"")
    target = os.path.abspath(str(path))

    real_open = builtins.open

    def _fake_open(file, *args, **kwargs):
        if os.path.abspath(str(file)) == target:
            raise PermissionError("locked")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _fake_open)

    checker = FileLockChecker()
    assert checker.is_file_locked(str(path)) is True
