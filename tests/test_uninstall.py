#!/usr/bin/env python3
"""Fixed acceptance tests for AgentBoot's Agent uninstall lifecycle."""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import i18n  # noqa: E402
import menu  # noqa: E402


class UninstallAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.ab_home = self.home / ".agentboot"
        self.agents_dir = self.ab_home / "agents"
        self.bin_dir = self.ab_home / "bin"
        self.npm_prefix = self.ab_home / "npm-prefix"
        self.state_path = self.ab_home / "installed-agents.json"
        self.patches = [
            mock.patch.object(menu, "AB_HOME", str(self.ab_home)),
            mock.patch.object(menu, "AGENTS_DIR", str(self.agents_dir)),
            mock.patch.object(menu, "NPM_PREFIX", str(self.npm_prefix)),
            mock.patch.object(menu, "INSTALL_STATE", str(self.state_path)),
            mock.patch.dict(os.environ, {"HOME": str(self.home)}, clear=False),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    @staticmethod
    def npm_agent(aid="codex", package="@openai/codex@0.90.0", binary="codex"):
        return {
            "id": aid,
            "name": aid,
            "bin": binary,
            "method": "npm",
            "npm": package,
        }

    def write_wrapper(self, binary="codex"):
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        path = self.bin_dir / binary
        path.write_text("#!/bin/sh\n# AgentBoot wrapper: test\n", encoding="utf-8")
        return path

    def test_missing_state_has_versioned_empty_shape(self):
        self.assertEqual(menu.load_install_state(), {"version": 1, "agents": {}})

    def test_record_install_is_atomic_and_tracks_ownership(self):
        executable = self.write_wrapper()
        menu.record_install(self.npm_agent(), "online", str(executable))

        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        entry = state["agents"]["codex"]
        self.assertEqual(entry["source"], "online")
        self.assertEqual(entry["method"], "npm")
        self.assertEqual(entry["package"], "@openai/codex@0.90.0")
        self.assertEqual(entry["executable"], str(executable))
        self.assertFalse(list(self.ab_home.glob("*.tmp")))

    def test_external_same_name_binary_is_not_claimed(self):
        with mock.patch.object(menu.shutil, "which", return_value="/usr/bin/codex"):
            status = menu.detect_install(self.npm_agent())
        self.assertEqual(status["status"], "external")
        self.assertFalse(status["managed"])

    def test_legacy_offline_directory_is_detected_as_managed(self):
        (self.agents_dir / "codex" / "node_modules").mkdir(parents=True)
        status = menu.detect_install(self.npm_agent())
        self.assertEqual(status["status"], "legacy")
        self.assertTrue(status["managed"])
        self.assertEqual(status["source"], "offline")

    def test_offline_uninstall_removes_payload_and_owned_shim_only(self):
        agent_dir = self.agents_dir / "codex"
        agent_dir.mkdir(parents=True)
        (agent_dir / "payload").write_text("x", encoding="utf-8")
        wrapper = self.write_wrapper()
        config = self.home / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("user settings", encoding="utf-8")
        menu.record_install(self.npm_agent(), "offline", str(wrapper))

        ok, _message = menu.uninstall_one(self.npm_agent())

        self.assertTrue(ok)
        self.assertFalse(agent_dir.exists())
        self.assertFalse(wrapper.exists())
        self.assertEqual(config.read_text(encoding="utf-8"), "user settings")
        self.assertNotIn("codex", menu.load_install_state()["agents"])

    def test_online_npm_uninstall_uses_exact_package_name(self):
        wrapper = self.write_wrapper()
        menu.record_install(self.npm_agent(), "online", str(wrapper))
        completed = subprocess.CompletedProcess([], 0)

        with mock.patch.object(menu, "npm_cmd", return_value="npm"), \
                mock.patch.object(menu.subprocess, "run", return_value=completed) as run:
            ok, _message = menu.uninstall_one(self.npm_agent())

        self.assertTrue(ok)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["npm", "uninstall", "-g", "@openai/codex"])
        self.assertFalse(wrapper.exists())

    def test_online_pip_uninstall_uses_noninteractive_mode(self):
        agent = {"id": "aider", "name": "Aider", "bin": "aider",
                 "method": "pip", "pip": "aider-install"}
        wrapper = self.write_wrapper("aider")
        menu.record_install(agent, "online", str(wrapper))
        completed = subprocess.CompletedProcess([], 0)

        with mock.patch.object(menu, "find_python", return_value="python3"), \
                mock.patch.object(menu.subprocess, "run", return_value=completed) as run:
            ok, _message = menu.uninstall_one(agent)

        self.assertTrue(ok)
        self.assertEqual(run.call_args.args[0],
                         ["python3", "-m", "pip", "uninstall", "-y", "aider-install"])

    def test_coco_uninstall_preserves_user_agent_data_by_default(self):
        agent = {"id": "coco", "name": "CoCo", "bin": "coco", "method": "script"}
        coco = self.home / ".coco"
        (coco / "agent" / "sessions").mkdir(parents=True)
        (coco / "agent" / "sessions" / "keep.json").write_text("{}", encoding="utf-8")
        (coco / "runtime").mkdir()
        (coco / "runtime" / "node").write_text("binary", encoding="utf-8")
        (coco / "bin").mkdir()
        self.write_wrapper("coco")
        menu.record_install(agent, "offline", str(self.bin_dir / "coco"))

        ok, _message = menu.uninstall_one(agent)

        self.assertTrue(ok)
        self.assertTrue((coco / "agent" / "sessions" / "keep.json").exists())
        self.assertFalse((coco / "runtime").exists())
        self.assertFalse((coco / "bin").exists())

    def test_purge_removes_coco_user_data_after_explicit_request(self):
        agent = {"id": "coco", "name": "CoCo", "bin": "coco", "method": "script"}
        coco = self.home / ".coco"
        (coco / "agent").mkdir(parents=True)
        menu.record_install(agent, "offline", None)

        ok, _message = menu.uninstall_one(agent, purge=True)

        self.assertTrue(ok)
        self.assertFalse(coco.exists())

    def test_generic_script_install_refuses_unsafe_automatic_removal(self):
        agent = {"id": "custom-script", "name": "Custom", "bin": "custom",
                 "method": "script", "script": "https://example.test/install.sh", "custom": True}
        external = self.home / "external" / "custom"
        external.parent.mkdir()
        external.write_text("do not delete", encoding="utf-8")
        menu.record_install(agent, "online", str(external))

        ok, message = menu.uninstall_one(agent)

        self.assertFalse(ok)
        self.assertIn("manual", message.lower())
        self.assertTrue(external.exists())
        self.assertIn("custom-script", menu.load_install_state()["agents"])

    def test_batch_deduplicates_ids_and_reports_unknown_or_failed(self):
        agents = [self.npm_agent(), {"id": "aider", "name": "Aider", "bin": "aider",
                                    "method": "pip", "pip": "aider-install"}]
        with mock.patch.object(menu, "load_registry", return_value=agents), \
                mock.patch.object(menu, "uninstall_one",
                                  side_effect=[(True, "removed"), (False, "failed")]) as one:
            failures = menu.uninstall_agents(["codex", "codex", "missing", "aider"])

        self.assertEqual(one.call_count, 2)
        self.assertEqual(failures, ["missing", "aider"])

    def test_cli_routes_uninstall_and_purge(self):
        with mock.patch.object(sys, "argv", ["menu.py", "uninstall", "codex,qwen-code", "--purge"]), \
                mock.patch.object(menu, "resolve_lang"), \
                mock.patch.object(menu.agent, "_utf8_console"), \
                mock.patch.object(menu, "uninstall_agents", return_value=[]) as uninstall:
            menu.main()
        uninstall.assert_called_once_with(["codex", "qwen-code"], purge=True)

    def test_localization_has_complete_uninstall_vocabulary(self):
        keys = {
            "menu.m4", "menu.uninstall_title", "menu.uninstall_confirm",
            "menu.uninstall_ok", "menu.uninstall_fail", "menu.uninstall_summary",
            "menu.uninstall_preserved", "menu.uninstall_nothing",
        }
        for table in (i18n.ZH, i18n.EN):
            self.assertFalse(keys - set(table))

    def test_user_documentation_covers_uninstall_and_purge(self):
        for relative in ("README.md", "README.en.md", "docs/zh/安装指南.md",
                         "docs/en/install-guide.md"):
            text = (ROOT / relative).read_text(encoding="utf-8").lower()
            self.assertIn("uninstall" if relative.endswith(".md") and "en/" in relative
                          or relative == "README.en.md" else "卸载", text)
        self.assertIn("--purge", (ROOT / "README.en.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
