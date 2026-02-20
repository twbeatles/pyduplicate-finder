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

    def test_get_quarantine_items_by_ids(self):
        id1 = self.cache.insert_quarantine_item("o1", "q1", size=1, mtime=1.0, status="quarantined")
        id2 = self.cache.insert_quarantine_item("o2", "q2", size=2, mtime=2.0, status="quarantined")
        out = self.cache.get_quarantine_items_by_ids([id1, id2, 999999])
        self.assertIn(id1, out)
        self.assertIn(id2, out)
        self.assertEqual(out[id1]["orig_path"], "o1")
        self.assertEqual(out[id2]["quarantine_path"], "q2")

    def test_update_scan_job_run_session(self):
        self.cache.upsert_scan_job(
            name="default",
            enabled=True,
            schedule_type="daily",
            weekday=0,
            time_hhmm="03:00",
            output_dir="",
            output_json=True,
            output_csv=False,
            config_json="{}",
        )
        run_id = self.cache.create_scan_job_run("default", session_id=0, status="running")
        self.assertTrue(run_id > 0)
        self.cache.update_scan_job_run_session(run_id, session_id=123)

        conn = self.cache._get_conn()
        row = conn.execute("SELECT session_id FROM scan_job_runs WHERE id=?", (run_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(int(row[0] or 0), 123)
