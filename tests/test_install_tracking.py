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

    def test_offline_npm_entry_uses_real_package_bin_not_dot_bin_copy(self):
        agent = {"id": "codex", "name": "Codex", "bin": "codex", "method": "npm",
                 "npm": "@openai/codex@0.90.0"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "agents" / "codex" / "node_modules" / "@openai" / "codex"
            (package / "bin").mkdir(parents=True)
            (package / "package.json").write_text(
                '{"name":"@openai/codex","bin":{"codex":"bin/codex.js"}}', encoding="utf-8")
            (package / "bin" / "codex.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
            with mock.patch.object(menu, "AGENTS_DIR", str(root / "agents")):
                entry = menu.offline_npm_entry(agent)
        self.assertEqual(entry, str(package / "bin" / "codex.js"))

    def test_offline_shim_uses_selected_node_path(self):
        agent = {"id": "codex", "name": "Codex", "bin": "codex", "method": "npm",
                 "npm": "@openai/codex@0.90.0"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "agents" / "codex" / "node_modules" / "@openai" / "codex"
            (package / "bin").mkdir(parents=True)
            (package / "package.json").write_text(
                '{"bin":{"codex":"bin/codex.js"}}', encoding="utf-8")
            (package / "bin" / "codex.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
            with mock.patch.object(menu, "AGENTS_DIR", str(root / "agents")), \
                    mock.patch.object(menu, "AB_HOME", str(root)), \
                    mock.patch.object(menu, "POSIX", True):
                self.assertTrue(menu.write_shim(agent, node_path="/portable/node"))
                shim = (root / "bin" / "codex").read_text(encoding="utf-8")
        self.assertIn('exec "/portable/node"', shim)

    def test_windows_offline_shim_escapes_cmd_percent_variables(self):
        agent = {"id": "codex", "name": "Codex", "bin": "codex", "method": "npm",
                 "npm": "@openai/codex@0.90.0"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "agents" / "codex" / "node_modules" / "@openai" / "codex"
            (package / "bin").mkdir(parents=True)
            (package / "package.json").write_text(
                '{"bin":{"codex":"bin/codex.js"}}', encoding="utf-8")
            (package / "bin" / "codex.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
            with mock.patch.object(menu, "AGENTS_DIR", str(root / "agents")), \
                    mock.patch.object(menu, "AB_HOME", str(root)), \
                    mock.patch.object(menu, "POSIX", False):
                self.assertTrue(menu.write_shim(agent, node_path="C:\\portable\\node.exe"))
                shim = (root / "bin" / "codex.cmd").read_text(encoding="ascii")
        self.assertIn("%AB_ROOT%", shim)
        self.assertIn("%PATH%", shim)
        self.assertIn('"C:\\portable\\node.exe"', shim)


if __name__ == "__main__":
    unittest.main(verbosity=2)
