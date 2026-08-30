#!/usr/bin/env python3
"""Download verification regressions for installers and builders."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))


class DownloaderSourceTests(unittest.TestCase):
    def test_posix_install_falls_back_when_curl_writes_nothing(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('rm -f "$2"', text)
        self.assertIn('[ -s "$2" ]', text)
        self.assertIn("command -v wget", text)

    def test_offline_builder_validates_downloaded_files(self):
        text = (ROOT / "scripts" / "build-offline.sh").read_text(encoding="utf-8")
        self.assertIn("fetch_file()", text)
        self.assertIn('rm -f "$2"', text)
        self.assertIn('[ -s "$2" ]', text)
        self.assertIn("verify_node_archive", text)
        self.assertNotIn("[ -f \"$ARC\" ] || curl", text)

    def test_powershell_download_removes_false_success(self):
        for relative in ("scripts/install.ps1", "scripts/build-offline.ps1"):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertIn("Remove-Item $out", text)
            self.assertIn("Length -gt 0", text)

    def test_windows_runtime_downloads_have_fixed_hash_checks(self):
        builder = (ROOT / "scripts/build-offline.ps1").read_text(encoding="utf-8-sig")
        installer = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Confirm-NodeArchive", builder)
        self.assertIn("4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3", builder)
        self.assertIn("4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3", installer)

    def test_runtime_node_download_verifies_official_checksum(self):
        text = (ROOT / "core" / "menu.py").read_text(encoding="utf-8")
        self.assertIn("SHASUMS256.txt", text)
        self.assertIn("hashlib.sha256", text)
        self.assertIn("Node 运行时 SHA-256 校验失败", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
