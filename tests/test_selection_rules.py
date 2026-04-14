import os
import tempfile
import time
import unittest

from src.core.scan_types import SelectionCandidate, SelectionPolicy
from src.core.selection_rules import (
    decide_keep_delete_for_group,
    decide_selection_for_candidates,
    parse_rules,
)


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

            # Set deterministic mtimes using current-era timestamps that work on
            # Windows filesystems with restricted epoch handling.
            now = max(int(time.time()), 10_000)
            os.utime(p1, (now - 300, now - 300))
            os.utime(p2, (now - 200, now - 200))
            os.utime(p3, (now - 100, now - 100))

            keep_set, delete_set = decide_keep_delete_for_group([p1, p2, p3], rules=[])
            self.assertEqual(keep_set, {p1})
            self.assertEqual(delete_set, {p2, p3})

    def test_selection_policy_precedence_explicit_keep_then_safelist_then_policy(self):
        candidates = [
            SelectionCandidate(path="/scan/keep-a.txt", mtime=300.0, explicit_keep=True),
            SelectionCandidate(path="/scan/safe-b.txt", mtime=100.0, safelisted=True),
            SelectionCandidate(path="/scan/c.txt", mtime=50.0),
        ]
        decision = decide_selection_for_candidates(candidates, rules=[], policy=SelectionPolicy(mode="oldest"))
        self.assertEqual(decision.keep_set, {"/scan/keep-a.txt"})
        self.assertIn("/scan/safe-b.txt", decision.delete_set)
        self.assertEqual(decision.reasons["/scan/keep-a.txt"], "explicit_keep")

    def test_selection_policy_primary_collection_preferred(self):
        candidates = [
            SelectionCandidate(path="/secondary/a.txt", mtime=10.0, collection_role="secondary"),
            SelectionCandidate(path="/primary/b.txt", mtime=20.0, collection_role="primary"),
        ]
        decision = decide_selection_for_candidates(
            candidates,
            rules=[],
            policy=SelectionPolicy(mode="primary_keep", collection_preference="primary"),
        )
        self.assertEqual(decision.keep_set, {"/primary/b.txt"})
        self.assertEqual(decision.reasons["/primary/b.txt"], "collection_primary_keep")


if __name__ == "__main__":
    unittest.main()
