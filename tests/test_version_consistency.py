#!/usr/bin/env python3
"""Ensure every independently distributed surface advertises one release version."""

from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="ascii").strip()
TAG = "v" + VERSION
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402
import menu  # noqa: E402


class VersionConsistencyTests(unittest.TestCase):
    def test_python_core_uses_version_file(self):
        self.assertEqual(agent.VERSION, VERSION)
        self.assertEqual(menu.VERSION, VERSION)

    def test_distributed_installers_pin_current_tag(self):
        shell = (ROOT / "install.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8-sig")
        worker = (ROOT / "cloudflare/worker.js").read_text(encoding="utf-8")
        self.assertIn('TAG="%s"' % TAG, shell)
        self.assertIn("$Tag       = '%s'" % TAG, powershell)
        self.assertIn('const TAG = "%s"' % TAG, worker)

    def test_web_and_guides_show_current_version(self):
        for relative in ("pages/index.html", "pages/en/index.html", "cloudflare/worker.js",
                         "docs/zh/安装指南.md", "docs/en/install-guide.md", "安装指南.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(TAG, text, relative)

    def test_web_asset_cache_busters_match_version(self):
        for relative in ("pages/index.html", "pages/en/index.html"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("site.css?v=%s" % VERSION, text, relative)
            self.assertIn("site.js?v=%s" % VERSION, text, relative)

    def test_online_builder_names_current_version(self):
        text = (ROOT / "scripts/build-online.py").read_text(encoding="utf-8")
        self.assertIn('ROOT / "VERSION"', text)
        self.assertNotIn('TAG = "v1.0.0"', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
