#!/usr/bin/env python3
"""Integration checks for install ownership recording and package delivery."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class InstallTrackingTests(unittest.TestCase):
    def test_online_npm_success_records_resolved_install(self):
        agent = {"id": "codex", "name": "Codex", "vendor": "OpenAI", "bin": "codex",
                 "method": "npm", "npm": "@openai/codex@0.90.0"}
        with mock.patch.object(menu, "load_registry", return_value=[agent]), \
                mock.patch.object(menu, "npm_install", return_value=True), \
                mock.patch.object(menu, "find_bin", return_value="/managed/npm/bin/codex"), \
                mock.patch.object(menu, "wire_agnes", return_value=({}, [])), \
                mock.patch.object(menu, "NPM_PREFIX", "/managed/npm"), \
                mock.patch.object(menu, "record_install") as record, \
                mock.patch.object(menu, "ensure_path_registered"):
            failures = menu.install_online(["codex"])
        self.assertEqual(failures, [])
        record.assert_called_once_with(agent, "online", "/managed/npm/bin/codex", "/managed/npm")

    def test_offline_success_records_agentboot_payload(self):
        agent = {"id": "codex", "name": "Codex", "bin": "codex", "method": "npm"}
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "payloads"
            source = payload / "agents" / "codex" / menu.plat_id() / "node_modules"
            source.mkdir(parents=True)
            with mock.patch.object(menu, "load_registry", return_value=[agent]), \
                    mock.patch.object(menu, "find_payload_dir", return_value=str(payload)), \
                    mock.patch.object(menu.shutil, "which", return_value="node"), \
                    mock.patch.object(menu, "node_ok", return_value=True), \
                    mock.patch.object(menu, "wire_agnes", return_value=({}, [])), \
                    mock.patch.object(menu, "write_shim", return_value=True), \
                    mock.patch.object(menu, "record_install") as record, \
                    mock.patch.object(menu, "ensure_path_registered"):
                failures = menu.offline_install(["codex"], str(payload))
        self.assertEqual(failures, [])
        self.assertEqual(record.call_args.args[:2], (agent, "offline"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
