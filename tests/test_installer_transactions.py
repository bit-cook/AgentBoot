#!/usr/bin/env python3
"""Static regression gates for transactional installers and owned launchers."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallerTransactionTests(unittest.TestCase):
    def test_posix_installers_use_atomic_app_switch(self):
        for relative in ("install.sh", "scripts/install-offline.sh"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("app.new.", text, relative)
            self.assertIn("app.old.", text, relative)
            self.assertIn('mv "$OLD_APP" "$APP_DIR"', text, relative)

    def test_installers_refuse_unowned_launcher_collision(self):
        for relative in ("install.sh", "scripts/install-offline.sh",
                         "scripts/install.ps1", "scripts/install-offline.ps1"):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertIn("拒绝覆盖不属于 AgentBoot 的命令", text, relative)

    def test_powershell_extract_checks_tar_exit_and_content(self):
        for relative in ("scripts/install.ps1", "scripts/install-offline.ps1"):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertIn("$LASTEXITCODE -eq 0", text, relative)
            self.assertIn("Get-ChildItem $dest", text, relative)

    def test_powershell_path_uses_component_comparison(self):
        for relative in ("scripts/install.ps1", "scripts/install-offline.ps1"):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertIn("[StringComparison]::OrdinalIgnoreCase", text, relative)
            self.assertNotIn('$userPath -notlike "*$_*"', text, relative)

    def test_offline_installers_copy_version_source(self):
        for relative in ("scripts/install-offline.sh", "scripts/install-offline.ps1"):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertIn("VERSION", text, relative)

    def test_launchers_reject_links_and_write_atomically(self):
        for relative in ("install.sh", "scripts/install-offline.sh"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('[ -L "$launcher" ]', text, relative)
            self.assertIn('.agentboot.new.', text, relative)
            self.assertIn('mv -f "$agentboot_tmp"', text, relative)
        for relative in ("scripts/install.ps1", "scripts/install-offline.ps1"):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertIn("ReparsePoint", text, relative)
            self.assertIn("Set-LauncherAtomic", text, relative)


if __name__ == "__main__":
    unittest.main(verbosity=2)
