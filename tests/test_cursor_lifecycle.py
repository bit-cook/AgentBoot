#!/usr/bin/env python3
"""Cursor official desktop install ownership and safety regressions."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class CursorLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.ab_home = self.home / ".agentboot"
        self.apps = self.ab_home / "apps"
        self.patches = [
            mock.patch.object(menu, "AB_HOME", str(self.ab_home)),
            mock.patch.object(menu, "APPS_DIR", str(self.apps)),
            mock.patch.dict(os.environ, {"HOME": str(self.home)}, clear=False),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    def test_registry_uses_cursor_special_installer(self):
        registry = json.loads((ROOT / "agents" / "registry.json").read_text(encoding="utf-8"))
        cursor = next(agent for agent in registry["agents"] if agent["id"] == "cursor")
        self.assertEqual((cursor["method"], cursor["special_install"]), ("cursor", "cursor"))
        self.assertFalse(cursor["offline"])

    def test_linux_cursor_install_and_remove_stay_inside_agentboot(self):
        download = self.home / "Cursor.AppImage"
        download.write_bytes(b"\x7fELF" + b"x" * 128)
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(menu, "plat_id", return_value="linux-x64"), \
                mock.patch.dict(menu.CURSOR_SHA256, {"linux-x64": "a" * 64}), \
                mock.patch.object(menu, "_download_cursor_asset",
                                  return_value=(str(download), "https://downloads.cursor.com/production/x/Cursor.AppImage", "a" * 64)), \
                mock.patch.object(menu.subprocess, "run", return_value=completed):
            self.assertTrue(menu.install_cursor({"id": "cursor"}))
        root = self.apps / "cursor"
        self.assertTrue((root / "Cursor.AppImage").is_file())
        marker = json.loads((root / "agentboot-managed.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["managed_by"], "AgentBoot")
        self.assertIn("AgentBoot Cursor launcher", (self.ab_home / "bin" / "cursor").read_text())
        menu._remove_cursor_install()
        self.assertFalse(root.exists())

    def test_cursor_remove_refuses_unmarked_directory(self):
        root = self.apps / "cursor"
        root.mkdir(parents=True)
        (root / "keep.txt").write_text("user data", encoding="utf-8")
        with self.assertRaisesRegex(OSError, "归属标记"):
            menu._remove_cursor_install()
        self.assertTrue((root / "keep.txt").exists())

    def test_cursor_upgrade_refuses_unmarked_directory(self):
        root = self.apps / "cursor"
        root.mkdir(parents=True)
        with mock.patch.object(menu, "plat_id", return_value="linux-x64"), \
                mock.patch.object(menu, "_download_cursor_asset") as download:
            self.assertFalse(menu.install_cursor({"id": "cursor"}))
        download.assert_not_called()

    def test_cursor_install_refuses_symlinked_managed_root(self):
        target = self.home / "outside"
        target.mkdir()
        self.apps.mkdir(parents=True)
        (self.apps / "cursor").symlink_to(target, target_is_directory=True)
        with mock.patch.object(menu, "plat_id", return_value="linux-x64"), \
                mock.patch.object(menu, "_download_cursor_asset") as download:
            self.assertFalse(menu.install_cursor({"id": "cursor"}))
        download.assert_not_called()
        self.assertTrue(target.exists())

    def test_cursor_download_rejects_nonofficial_redirect(self):
        class Response:
            headers = {"Content-Length": "2000000"}
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def geturl(self): return "https://evil.example/Cursor.AppImage"
            def read(self, _size): return b""
        with mock.patch("urllib.request.urlopen", return_value=Response()), \
                self.assertRaisesRegex(ValueError, "非官方"):
            menu._download_cursor_asset(menu.CURSOR_DOWNLOADS["linux-x64"], ".AppImage")

    def test_cursor_platform_commands_preserve_signature_checks(self):
        source = (ROOT / "core" / "menu.py").read_text(encoding="utf-8")
        self.assertIn("Get-AuthenticodeSignature", source)
        self.assertIn('"codesign", "--verify", "--deep", "--strict"', source)
        self.assertIn('"spctl", "--assess", "--type", "execute"', source)
        self.assertIn('"hdiutil", "attach", "-readonly"', source)

    def test_cursor_marker_recovers_managed_detection_without_state(self):
        root = self.apps / "cursor"
        root.mkdir(parents=True)
        (root / "agentboot-managed.json").write_text(
            json.dumps({"managed_by": "AgentBoot"}), encoding="utf-8")
        status = menu.detect_install({"id": "cursor", "name": "Cursor", "bin": "cursor",
                                      "method": "cursor"})
        self.assertTrue(status["managed"])
        self.assertEqual(status["entry"]["method"], "cursor")


if __name__ == "__main__":
    unittest.main(verbosity=2)
