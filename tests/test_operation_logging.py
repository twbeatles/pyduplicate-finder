import os
import shutil
import tempfile
import unittest

import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.cache_manager import CacheManager


class TestOperationLogging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "scan_cache.db")
        self.cache = CacheManager(db_path=self.db_path)

    def tearDown(self):
        try:
            self.cache.close_all()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_append_finish(self):
        op_id = self.cache.create_operation("delete_quarantine", {"foo": "bar"})
        self.assertTrue(op_id > 0)
        self.cache.append_operation_items(
            op_id,
            [
                ("a", "moved_to_quarantine", "ok", "", 1, 1.0, "q/a"),
                ("b", "moved_to_quarantine", "fail", "missing", None, None, ""),
            ],
        )
        self.cache.finish_operation(op_id, "partial", "done", bytes_total=1, bytes_saved_est=0)

        ops = self.cache.list_operations(limit=10, offset=0)
        self.assertTrue(any(int(o["id"]) == op_id for o in ops))

        items = self.cache.get_operation_items(op_id)
        self.assertEqual(len(items), 2)

