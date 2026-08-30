#!/usr/bin/env python3
"""Custom Agent IDs remain unique and CLI deletion validates arguments."""

from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
import menu  # noqa: E402


class CustomAgentValidationTests(unittest.TestCase):
    def test_duplicate_custom_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom.json"
            custom.write_text('[{"id":"dup","bin":"dup"}]', encoding="utf-8")
            with mock.patch.object(menu, "CUSTOM_AGENTS", str(custom)):
                with self.assertRaisesRegex(ValueError, "已存在"):
                    menu.custom_add_entry({"id": "dup", "bin": "dup", "method": "npm", "npm": "dup"})

    def test_delete_without_id_exits_usage(self):
        with mock.patch.object(sys, "argv", ["menu.py", "add-agent", "--del"]), \
                mock.patch.object(menu, "resolve_lang"), mock.patch.object(menu.agent, "_utf8_console"):
            with self.assertRaisesRegex(SystemExit, "2"):
                menu.main()


if __name__ == "__main__": unittest.main(verbosity=2)
