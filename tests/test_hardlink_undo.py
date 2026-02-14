import os
import shutil
import tempfile
import unittest

import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.cache_manager import CacheManager
from src.core.quarantine_manager import QuarantineManager


class TestHardlinkUndo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "scan_cache.db")
        self.qdir = os.path.join(self.tmp, "quarantine")
        self.cache = CacheManager(db_path=self.db_path)
        self.qm = QuarantineManager(self.cache, quarantine_dir=self.qdir)

    def tearDown(self):
        try:
            self.cache.close_all()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restore_replaces_hardlink(self):
        if os.name != "nt":
            self.skipTest("Windows-only hardlink behavior test")

        canonical = os.path.join(self.tmp, "canonical.txt")
        target = os.path.join(self.tmp, "target.txt")

        with open(canonical, "w", encoding="utf-8") as f:
            f.write("AAA")
        with open(target, "w", encoding="utf-8") as f:
            f.write("BBB")

        moved, failures = self.qm.move_to_quarantine([target])
        self.assertFalse(failures)
        item_id = moved[0].item_id

        # Replace target with a hardlink to canonical.
        os.link(canonical, target)
        with open(target, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "AAA")

        # Restore should remove the hardlink and put the original back.
        ok, _msg, restored_path = self.qm.restore_item(item_id, allow_replace_hardlink_to=canonical)
        self.assertTrue(ok)
        self.assertEqual(restored_path, target)
        with open(target, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "BBB")

