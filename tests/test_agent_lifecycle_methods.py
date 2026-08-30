#!/usr/bin/env python3
"""Special lifecycle and offline-support regressions."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class AgentLifecycleTests(unittest.TestCase):
    def test_opencode_not_advertised_offline_until_postinstall_is_supported(self):
        registry = json.loads((ROOT / "agents/registry.json").read_text(encoding="utf-8"))
        opencode = next(agent for agent in registry["agents"] if agent["id"] == "opencode")
        self.assertFalse(opencode["offline"])

    def test_aider_uses_private_venv_lifecycle(self):
        registry = json.loads((ROOT / "agents/registry.json").read_text(encoding="utf-8"))
        aider = next(agent for agent in registry["agents"] if agent["id"] == "aider")
        self.assertEqual((aider["method"], aider["pip"]), ("venv", "aider-chat"))

    def test_aider_install_dispatches_private_venv(self):
        agent = {"id": "aider", "name": "Aider", "vendor": "Aider", "bin": "aider",
                 "method": "venv", "pip": "aider-chat"}
        with mock.patch.object(menu, "load_registry", return_value=[agent]), \
                mock.patch.object(menu, "install_aider_venv", return_value=True) as install, \
                mock.patch.object(menu, "aider_venv_executable", return_value="/managed/aider"), \
                mock.patch.object(menu, "wire_agnes", return_value=({}, [])), \
                mock.patch.object(menu, "record_install") as record, \
                mock.patch.object(menu, "ensure_path_registered"):
            self.assertEqual(menu.install_online(["aider"]), [])
        install.assert_called_once_with(agent)
        record.assert_called_once()

    def test_hermes_postinstall_uses_node_matching_selected_npm(self):
        agent = {"id": "hermes", "name": "Hermes", "method": "npm", "npm": "hermes-agent", "node": ">=20"}
        runtime_npm = "/managed/runtime/bin/npm"
        runtime_node = "/managed/runtime/bin/node"
        completed = subprocess.CompletedProcess([], 0, stdout="/managed/root\n")
        with mock.patch.object(menu, "npm_cmd", return_value=runtime_npm), \
                mock.patch.object(menu, "ensure_npm_prefix"), \
                mock.patch.object(menu, "runtime_node_dir", return_value="/managed/runtime"), \
                mock.patch.object(menu, "node_exe", return_value=runtime_node), \
                mock.patch.object(menu, "node_ok", return_value=True), \
                mock.patch.object(menu, "_npm_global_root", return_value="/managed/root"), \
                mock.patch.object(menu.os.path, "isdir", return_value=True), \
                mock.patch.object(menu, "_seed_uv", return_value=True), \
                mock.patch.object(menu, "_github_git_reachable", return_value=True), \
                mock.patch.object(menu.subprocess, "run", return_value=completed) as run:
            self.assertTrue(menu.install_hermes_special(agent))
        self.assertEqual(run.call_args_list[-1].args[0][0], runtime_node)


if __name__ == "__main__": unittest.main(verbosity=2)
