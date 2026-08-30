#!/usr/bin/env python3
"""Offline packages verify internal hashes and install only packed Agents."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OfflineManifestTests(unittest.TestCase):
    def test_builders_generate_internal_hash_manifest(self):
        for relative in ("scripts/build-offline.sh", "scripts/build-offline.ps1"):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertIn("hash_tree.py", text, relative)
            self.assertIn("PAYLOAD_SHA256SUMS.txt", text, relative)

    def test_installers_verify_internal_hash_manifest(self):
        for relative in ("scripts/install-offline.sh", "scripts/install-offline.ps1"):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertIn("PAYLOAD_SHA256SUMS.txt", text, relative)
            self.assertIn("SHA-256 校验", text, relative)

    def test_all_comes_from_package_manifest_not_global_registry(self):
        shell = (ROOT / "scripts/install-offline.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts/install-offline.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("MANIFEST.txt", shell)
        self.assertIn("MANIFEST.txt", powershell)
        self.assertNotIn("a.get('offline')", shell)

    def test_hash_manifest_is_generated_per_platform(self):
        shell = (ROOT / "scripts/build-offline.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts/build-offline.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('PAYLOAD_SHA256SUMS.txt" "$PLAT"', shell)
        self.assertIn("PAYLOAD_SHA256SUMS.txt') $plat", powershell)

    def test_windows_installer_preserves_single_agent_as_argument(self):
        powershell = (ROOT / "scripts/install-offline.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$menuArgs = @($menu, 'offline', '--payload', $PayloadDir) + @($ids)", powershell)
        self.assertIn("& $pyExe @menuArgs", powershell)
        self.assertIn("Agent 离线安装失败", powershell)


if __name__ == "__main__":
    unittest.main(verbosity=2)
