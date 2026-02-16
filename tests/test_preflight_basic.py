import os
import tempfile
import unittest

from src.core.preflight import PreflightAnalyzer


class PreflightBasicTests(unittest.TestCase):
    def test_delete_trash_reports_missing_and_no_eligible(self):
        analyzer = PreflightAnalyzer(lock_checker=None)
        rep = analyzer.analyze_delete_trash(["/this/path/should/not/exist"])

        codes = [i.code for i in rep.issues]
        self.assertIn("missing", codes)
        self.assertIn("no_eligible", codes)
        self.assertEqual(rep.eligible_paths, [])

    def test_delete_trash_accepts_existing_file(self):
        analyzer = PreflightAnalyzer(lock_checker=None)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "x.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("abc")

            rep = analyzer.analyze_delete_trash([p])
            self.assertIn(p, rep.eligible_paths)
            # Should not block when one valid file exists.
            block_codes = [i.code for i in rep.issues if i.severity == "block"]
            self.assertNotIn("no_eligible", block_codes)


if __name__ == "__main__":
    unittest.main()
