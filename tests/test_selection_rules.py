import os
import tempfile
import unittest

from src.core.selection_rules import decide_keep_delete_for_group, parse_rules


class SelectionRulesTests(unittest.TestCase):
    def test_parse_rules_ignores_invalid(self):
        parsed = parse_rules(
            [
                {"pattern": "", "action": "keep"},
                {"pattern": "*.tmp", "action": "invalid"},
                {"pattern": "*.jpg", "action": "keep"},
            ]
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].pattern, "*.jpg")
        self.assertEqual(parsed[0].action, "keep")

    def test_explicit_keep_wins(self):
        paths = [
            "/a/keep.jpg",
            "/a/delete.jpg",
            "/a/other.jpg",
        ]
        rules = parse_rules(
            [
                {"pattern": "*keep*", "action": "keep"},
                {"pattern": "*.jpg", "action": "delete"},
            ]
        )
        keep_set, delete_set = decide_keep_delete_for_group(paths, rules)
        self.assertIn("/a/keep.jpg", keep_set)
        self.assertIn("/a/delete.jpg", delete_set)
        self.assertIn("/a/other.jpg", delete_set)

    def test_fallback_keeps_oldest(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = os.path.join(td, "a.bin")
            p2 = os.path.join(td, "b.bin")
            p3 = os.path.join(td, "c.bin")
            for p in (p1, p2, p3):
                with open(p, "wb") as f:
                    f.write(b"x")

            # Set deterministic mtimes: p1 oldest.
            os.utime(p1, (1000, 1000))
            os.utime(p2, (2000, 2000))
            os.utime(p3, (3000, 3000))

            keep_set, delete_set = decide_keep_delete_for_group([p1, p2, p3], rules=[])
            self.assertEqual(keep_set, {p1})
            self.assertEqual(delete_set, {p2, p3})


if __name__ == "__main__":
    unittest.main()
