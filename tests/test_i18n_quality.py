#!/usr/bin/env python3
"""Translation dictionaries have unique keys and visible format failures."""

import ast
import re
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


class DoctorI18nTests(unittest.TestCase):
    """回归：doctor/status 输出在英文模式不得漏中文（v1.8.0 排查实测 10/16 行漏中文后修复）。"""

    def _doctor_output(self, lang):
        import io
        import contextlib
        import re
        old = i18n.get_lang()
        try:
            i18n.set_lang(lang)
            import agent
            buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(buffer):
                    agent.doctor(agent.load_config())
            except Exception:
                pass
            return buffer.getvalue()
        finally:
            i18n.set_lang(old)

    def test_english_doctor_has_no_chinese_leakage(self):
        output = self._doctor_output("en")
        self.assertTrue(output.strip(), "doctor 应有输出")
        chinese = [line for line in output.splitlines()
                   if re.search(r"[一-鿿]", line)]
        self.assertEqual(chinese, [], "英文模式漏中文: %s" % chinese[:3])

    def test_chinese_doctor_still_localized(self):
        output = self._doctor_output("zh")
        self.assertIn("环境体检", output)
        self.assertIn("模型源", output)
