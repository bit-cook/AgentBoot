#!/usr/bin/env python3
"""Runtime-version and offline target-platform regressions."""

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class NodeVersionTests(unittest.TestCase):
    def result(self, version, code=0):
        return subprocess.CompletedProcess([], code, stdout=version, stderr="")

    def test_semver_requirement_includes_minor_and_patch(self):
        with mock.patch.object(menu.subprocess, "run", return_value=self.result("v22.21.9")):
            self.assertFalse(menu.node_ok("node", ">=22.22.0"))
        with mock.patch.object(menu.subprocess, "run", return_value=self.result("v22.23.2")):
            self.assertTrue(menu.node_ok("node", ">=22.22.0"))

    def test_major_only_requirement_remains_supported(self):
        with mock.patch.object(menu.subprocess, "run", return_value=self.result("v20.1.0")):
            self.assertTrue(menu.node_ok("node", ">=20"))
            self.assertFalse(menu.node_ok("node", ">=22"))

    def test_npm_install_requests_agent_minimum(self):
        agent = {"id": "openclaw", "name": "OpenClaw", "vendor": "OpenClaw",
                 "bin": "openclaw", "method": "npm", "npm": "openclaw", "node": ">=22.22.0"}
        with mock.patch.object(menu, "load_registry", return_value=[agent]), \
                mock.patch.object(menu, "npm_install", return_value=False) as install, \
                mock.patch.object(menu, "ensure_path_registered"):
            menu.install_online(["openclaw"])
        install.assert_called_once_with("openclaw", ">=22.22.0")

    def test_portable_runtime_satisfies_strictest_registry_requirement(self):
        self.assertEqual(menu.NODE_VERSION, "v22.23.2")


class OfflineBuilderTests(unittest.TestCase):
    def test_default_build_targets_native_platform_only(self):
        shell = (ROOT / "scripts/build-offline.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts/build-offline.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('PLATFORMS="${PLATFORMS:-$HOST_PLAT}"', shell)
        self.assertIn("if (-not $Platforms) { $Platforms = $HostPlat }", powershell)
        self.assertIn("not a.get('os') or os_id in a['os']", shell)
        self.assertIn("$_.os -contains 'windows'", powershell)

    def test_coco_builder_maps_every_supported_target(self):
        shell = (ROOT / "scripts/build-offline.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts/build-offline.ps1").read_text(encoding="utf-8-sig")
        for platform in ("linux-x64", "linux-arm64", "darwin-x64", "darwin-arm64"):
            asset = "node-v22.23.2-%s.tar.gz" % platform
            self.assertIn(asset, shell)
            self.assertIn(asset, powershell)

    def test_uv_seeder_accepts_explicit_target_platform(self):
        seeder = (ROOT / "scripts/tools/seed_uv_generic.py").read_text(encoding="utf-8")
        self.assertIn("TARGETS", seeder)
        self.assertIn("sys.argv[2]", seeder)
        shell = (ROOT / "scripts/build-offline.sh").read_text(encoding="utf-8")
        self.assertIn('seed_uv_generic.py" "$PREFIX/node_modules/hermes-agent" "$PLAT"', shell)

    def test_online_uv_seed_verifies_downloaded_digest(self):
        source = (ROOT / "core" / "menu.py").read_text(encoding="utf-8")
        self.assertIn("hashlib.sha256(open(archive", source)
        self.assertIn("uv SHA-256 校验失败", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
