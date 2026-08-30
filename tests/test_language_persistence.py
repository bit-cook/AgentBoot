#!/usr/bin/env python3
"""Language changes persist in the active config and prompt."""

from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
import agent  # noqa: E402
import i18n  # noqa: E402
import menu  # noqa: E402


class LanguagePersistenceTests(unittest.TestCase):
    def test_language_switch_mutates_live_config(self):
        cfg = agent.default_config()
        with mock.patch.object(menu.agent, "save_config"):
            menu.set_lang_persist("en", cfg)
        self.assertEqual(cfg["lang"], "en")

    def test_english_prompt_does_not_order_chinese(self):
        previous = i18n.get_lang()
        try:
            i18n.set_lang("en")
            prompt = agent.system_prompt()
        finally:
            i18n.set_lang(previous)
        self.assertIn("English", prompt)
        self.assertNotIn("简体中文", prompt)


if __name__ == "__main__": unittest.main(verbosity=2)
