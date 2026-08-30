#!/usr/bin/env python3
"""Regression tests for high-impact v1.0.0 defects found during uninstall review."""

from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402
import menu  # noqa: E402


class HighImpactRegressionTests(unittest.TestCase):
    def test_installed_ab_wrappers_forward_subcommands(self):
        files = ("install.sh", "scripts/install-offline.sh", "scripts/install.ps1",
                 "scripts/install-offline.ps1")
        for relative in files:
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertNotRegex(text, r"agent\.py['\"]?\s+chat\s")

    def test_windows_platform_id_matches_payload_layout(self):
        with mock.patch.object(menu.platform, "system", return_value="Windows"), \
                mock.patch.object(menu.platform, "machine", return_value="AMD64"):
            self.assertEqual(menu.plat_id(), "win-x64")

    def test_linux_kb_indexes_every_markdown_section(self):
        expected = 0
        for path in Path(agent.KB_DIR).glob("*.md"):
            expected += sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                            if line.startswith("## "))
        original = agent._KB_CACHE
        try:
            agent._KB_CACHE = None
            sections = agent._kb_sections()
        finally:
            agent._KB_CACHE = original
        self.assertGreaterEqual(expected, 60)
        self.assertEqual(len(sections), expected)

    def test_npm_install_is_scoped_to_agentboot_prefix(self):
        completed = mock.Mock(returncode=0)
        with mock.patch.object(menu, "npm_cmd", return_value="npm"), \
                mock.patch.object(menu.shutil, "which", return_value="npm"), \
                mock.patch.object(menu, "cn_mode", return_value=False), \
                mock.patch.object(menu, "NPM_PREFIX", "/managed/agentboot/npm-prefix"), \
                mock.patch.object(menu.os, "makedirs"), \
                mock.patch.object(menu.subprocess, "run", return_value=completed) as run:
            self.assertTrue(menu.npm_install("@openai/codex@0.90.0"))
        command = run.call_args.args[0]
        self.assertIn("--prefix", command)
        self.assertEqual(command[command.index("--prefix") + 1], "/managed/agentboot/npm-prefix")

    def test_ttfb_does_not_wait_for_remaining_response_body(self):
        class Response:
            def __init__(self):
                self.lines = iter([b"data: {\"choices\":[]}\n"])

            def readline(self):
                return next(self.lines, b"")

            def read(self):
                raise AssertionError("TTFB must not drain the response body")

        connection = mock.Mock()
        connection.getresponse.return_value = Response()
        cfg = {"active": "agnes", "providers": {}}
        with mock.patch.object(agent, "_connect", return_value=connection), \
                mock.patch.object(agent, "_drop_pool") as drop:
            latency = agent._ttfb(cfg)
        self.assertIsInstance(latency, float)
        drop.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
