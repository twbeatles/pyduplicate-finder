from __future__ import annotations

import os
import pytest
from src.core.native.bridge import (
    RustCancellationToken,
    compare_files_byte_by_byte,
    hash_file,
    hash_files_batch,
    is_rust_available,
)


@pytest.mark.skipif(not is_rust_available(), reason="pydup_core is not compiled")
class TestCancellationParity:
    def test_token_lifecycle(self):
        token = RustCancellationToken()
        assert not token.is_cancelled()
        token.cancel()
        assert token.is_cancelled()
        token.reset()
        assert not token.is_cancelled()

    def test_cancel_single_hash(self, tmp_path):
        fp = tmp_path / "cancel_test.bin"
        fp.write_bytes(b"\x00" * (1024 * 1024))

        token = RustCancellationToken()
        token.cancel()

        digest, err = hash_file(str(fp), cancel_token=token)
        assert digest is None
        assert err is not None

    def test_cancel_batch_hash(self, tmp_path):
        items = []
        for i in range(10):
            fp = tmp_path / f"cancel_batch_{i}.bin"
            fp.write_bytes(b"DATA" * 10000)
            items.append((str(fp), fp.stat().st_size, fp.stat().st_mtime))

        token = RustCancellationToken()
        token.cancel()

        results = hash_files_batch(items, cancel_token=token)
        assert len(results) == len(items)
        for r in results:
            assert r.status == "cancelled"
            assert r.digest is None

    def test_cancel_byte_compare(self, tmp_path):
        fa = tmp_path / "a.bin"
        fb = tmp_path / "b.bin"
        data = b"X" * (1024 * 1024)
        fa.write_bytes(data)
        fb.write_bytes(data)

        token = RustCancellationToken()
        token.cancel()

        equal = compare_files_byte_by_byte(str(fa), str(fb), cancel_token=token)
        assert equal is False
