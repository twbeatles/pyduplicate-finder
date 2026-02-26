import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.cache_manager import CacheManager
from src.core.quarantine_manager import QuarantineManager
from src.core.history import HistoryManager
from src.utils.i18n import strings


class TestQuarantineManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "scan_cache.db")
        self.qdir = os.path.join(self.tmp, "quarantine")
        self.cache = CacheManager(db_path=self.db_path)
        self.qm = QuarantineManager(self.cache, quarantine_dir=self.qdir)
        self.history = HistoryManager(cache_manager=self.cache, quarantine_manager=self.qm)

    def tearDown(self):
        try:
            self.cache.close_all()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_move_restore_purge(self):
        f1 = os.path.join(self.tmp, "a.txt")
        with open(f1, "w", encoding="utf-8") as f:
            f.write("hello")

        moved, failures = self.qm.move_to_quarantine([f1])
        self.assertEqual(len(failures), 0)
        self.assertEqual(len(moved), 1)
        self.assertFalse(os.path.exists(f1))
        self.assertTrue(os.path.exists(moved[0].quarantine_path))

        items = self.cache.list_quarantine_items(status_filter="quarantined")
        self.assertEqual(len(items), 1)
        item_id = int(items[0]["id"])

        ok, _msg, restored_path = self.qm.restore_item(item_id)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(restored_path))

        # After restore, it is not quarantined anymore.
        items2 = self.cache.list_quarantine_items(status_filter="quarantined")
        self.assertEqual(len(items2), 0)

    def test_move_rolls_back_when_quarantine_insert_fails(self):
        f1 = os.path.join(self.tmp, "rollback.txt")
        with open(f1, "w", encoding="utf-8") as f:
            f.write("rollback")

        with patch.object(self.cache, "insert_quarantine_item", return_value=0):
            moved, failures = self.qm.move_to_quarantine([f1])

        self.assertEqual(moved, [])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], f1)
        self.assertIn("db_insert_failed", failures[0][1])
        self.assertTrue(os.path.exists(f1))
        items = self.cache.list_quarantine_items(status_filter="quarantined")
        self.assertEqual(items, [])

    def test_retention_purges_by_size(self):
        # Create two files, quarantine both, then set max_bytes low to purge oldest.
        paths = []
        for i in range(2):
            p = os.path.join(self.tmp, f"f{i}.bin")
            with open(p, "wb") as f:
                f.write(b"x" * 1024)
            paths.append(p)

        moved, failures = self.qm.move_to_quarantine(paths)
        self.assertFalse(failures)
        self.assertEqual(len(moved), 2)

        purged = self.qm.apply_retention(max_days=9999, max_bytes=1024)  # keep only 1 file worth
        self.assertGreaterEqual(len(purged), 1)

    def test_history_delete_reflects_cancelled_state(self):
        files = []
        for i in range(2):
            p = os.path.join(self.tmp, f"cancel_{i}.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
            files.append(p)

        calls = {"n": 0}

        def check_cancel():
            calls["n"] += 1
            return calls["n"] > 1

        ok, msg = self.history.execute_delete(files, check_cancel=check_cancel)
        self.assertTrue(ok)
        self.assertIn(strings.tr("op_cancelled"), msg)

        items = self.cache.list_quarantine_items(status_filter="quarantined")
        self.assertEqual(len(items), 1)
        self.assertFalse(os.path.exists(files[0]))
        self.assertTrue(os.path.exists(files[1]))

    def test_restore_conflict_name_is_unique_for_multiple_items(self):
        orig = os.path.join(self.tmp, "same.txt")

        with open(orig, "w", encoding="utf-8") as f:
            f.write("first")
        moved1, failures1 = self.qm.move_to_quarantine([orig])
        self.assertFalse(failures1)
        self.assertEqual(len(moved1), 1)

        with open(orig, "w", encoding="utf-8") as f:
            f.write("second")
        moved2, failures2 = self.qm.move_to_quarantine([orig])
        self.assertFalse(failures2)
        self.assertEqual(len(moved2), 1)

        # Keep original destination occupied so both restores must resolve conflict names.
        with open(orig, "w", encoding="utf-8") as f:
            f.write("occupied")

        item_ids = [int(moved1[0].item_id), int(moved2[0].item_id)]
        with patch("src.core.quarantine_manager.time.strftime", return_value="20260225-120000"):
            ok1, _msg1, path1 = self.qm.restore_item(item_ids[0])
            ok2, _msg2, path2 = self.qm.restore_item(item_ids[1])

        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertTrue(path1 and path2)
        self.assertNotEqual(path1, path2)
        self.assertTrue(os.path.exists(path1))
        self.assertTrue(os.path.exists(path2))
        self.assertIn(".restored-20260225-120000-", path1)
        self.assertIn(".restored-20260225-120000-", path2)
