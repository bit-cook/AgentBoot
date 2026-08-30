#!/usr/bin/env python3
"""Translation dictionaries have unique keys and visible format failures."""

import ast
from collections import Counter
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
import i18n  # noqa: E402


class I18nQualityTests(unittest.TestCase):
    def test_source_dictionaries_have_unique_keys(self):
        tree = ast.parse((ROOT / "core/i18n.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("ZH", "EN") for t in node.targets):
                keys = [key.value for key in node.value.keys if isinstance(key, ast.Constant)]
                duplicates = [key for key, count in Counter(keys).items() if count > 1]
                self.assertEqual(duplicates, [])

    def test_format_mismatch_raises(self):
        old = i18n.get_lang()
        try:
            i18n.set_lang("en")
            with self.assertRaises((TypeError, ValueError)):
                i18n.t("menu.install_ok", "only-one")
        finally:
            i18n.set_lang(old)


if __name__ == "__main__": unittest.main(verbosity=2)
