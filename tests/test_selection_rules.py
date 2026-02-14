import os
import tempfile
import unittest

import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.selection_rules import parse_rules, decide_keep_delete_for_group


class TestSelectionRules(unittest.TestCase):
    def test_explicit_keep_deletes_rest(self):
        rules = parse_rules([{"pattern": "*keepme*", "action": "keep"}])
        paths = ["C:/x/keepme.txt", "C:/x/other.txt", "C:/x/another.txt"]
        keep, delete = decide_keep_delete_for_group(paths, rules)
        self.assertIn("C:/x/keepme.txt", keep)
        self.assertIn("C:/x/other.txt", delete)
        self.assertIn("C:/x/another.txt", delete)

    def test_explicit_delete_fallback_keeps_one(self):
        rules = parse_rules([{"pattern": "*tmp*", "action": "delete"}])
        paths = ["C:/x/a.txt", "C:/x/tmp_copy.txt", "C:/x/b.txt"]
        keep, delete = decide_keep_delete_for_group(paths, rules)
        self.assertEqual(len(keep), 1)
        self.assertIn("C:/x/tmp_copy.txt", delete)
        self.assertEqual(set(paths), keep | delete)

