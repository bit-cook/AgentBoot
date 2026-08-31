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
    def test_matching_node_requirements_share_one_npm_install(self):
        agents = [
            {"id": "one", "name": "One", "vendor": "T", "desc": "", "bin": "one",
             "method": "npm", "npm": "pkg-one", "node": ">=18"},
            {"id": "two", "name": "Two", "vendor": "T", "desc": "", "bin": "two",
             "method": "npm", "npm": "pkg-two", "node": ">=18"},
        ]
        with mock.patch.object(menu, "load_registry", return_value=agents), \
                mock.patch.object(menu, "npm_install", return_value=True) as install, \
                mock.patch.object(menu, "find_bin", side_effect=lambda name: "/managed/" + name), \
                mock.patch.object(menu, "wire_agnes", return_value=({}, [])), \
                mock.patch.object(menu, "record_install"), \
                mock.patch.object(menu, "ensure_path_registered"):
            self.assertEqual(menu.install_online(["one", "two"]), [])
        install.assert_called_once()
        self.assertEqual(install.call_args.args[0], ["pkg-one", "pkg-two"])
        self.assertEqual(install.call_args.args[1], ">=18")

    def test_npm_batch_reuses_mirror_and_environment_detection(self):
        context = {}
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(menu, "npm_cmd", return_value="npm"), \
                mock.patch.object(menu, "ensure_npm_prefix"), \
                mock.patch.object(menu, "cn_mode", return_value=False) as mirror, \
                mock.patch.object(menu, "child_env", return_value={}) as child_env, \
                mock.patch.object(menu.subprocess, "run", return_value=completed):
            self.assertTrue(menu.npm_install("one", ">=18", context))
            self.assertTrue(menu.npm_install("two", ">=20", context))
        mirror.assert_called_once_with()
        child_env.assert_called_once_with()

    def test_opencode_offline_requires_native_regular_and_baseline_packages(self):
        registry = json.loads((ROOT / "agents/registry.json").read_text(encoding="utf-8"))
        opencode = next(agent for agent in registry["agents"] if agent["id"] == "opencode")
        self.assertTrue(opencode["offline"])
        self.assertEqual(opencode["npm"], "opencode-ai@1.18.25")
        self.assertEqual(opencode["offline_binary_packages"]["linux-x64"],
                         ["opencode-linux-x64", "opencode-linux-x64-baseline"])

    def test_opencode_selects_first_native_binary_that_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular = root / "node_modules/opencode-ai/node_modules/opencode-linux-x64/bin/opencode"
            baseline = root / "node_modules/opencode-ai/node_modules/opencode-linux-x64-baseline/bin/opencode"
            for path in (regular, baseline):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * (10 * 1024 * 1024 + 1))
            agent = {"offline_binary_packages": {"linux-x64":
                     ["opencode-linux-x64", "opencode-linux-x64-baseline"]}}
            failed = subprocess.CompletedProcess([], 1)
            passed = subprocess.CompletedProcess([], 0)
            with mock.patch.object(menu.subprocess, "run", side_effect=[failed, passed]) as run:
                selected = menu.select_opencode_binary(agent, str(root), "linux-x64")
            self.assertEqual(selected, str(baseline))
            self.assertEqual(run.call_count, 2)

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
