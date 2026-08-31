#!/usr/bin/env python3
"""Static regression gates for transactional installers and owned launchers."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallerTransactionTests(unittest.TestCase):
    def test_posix_online_installer_runs_one_visible_doctor_pass(self):
        shell = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertEqual(shell.count('"${APP_DIR}/core/agent.py" doctor'), 1)

    def test_posix_installers_use_atomic_app_switch(self):
        for relative in ("install.sh", "scripts/install-offline.sh"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("app.new.", text, relative)
            self.assertIn("app.old.", text, relative)
            self.assertIn('mv "$OLD_APP" "$APP_DIR"', text, relative)
            self.assertIn("SWAP_COMMITTED", text, relative)
            self.assertIn("trap", text, relative)

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
            self.assertIn("Restore-AppAtomic", text, relative)
            self.assertIn("Complete-AppAtomic", text, relative)
            self.assertIn("core\\launch.py", text, relative)

    def test_batch_bootstrap_propagates_installer_exit(self):
        text = (ROOT / "install.bat").read_text(encoding="utf-8")
        self.assertIn("set \"AB_EXIT=%ERRORLEVEL%\"", text)
        self.assertIn("exit /b %AB_EXIT%", text)

    def test_online_installers_validate_python_before_app_commit(self):
        shell = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertLess(shell.index("未能准备 Python3"), shell.index("安装程序到 ${APP_DIR}"))
        powershell = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8-sig")
        self.assertLess(powershell.index("未能准备 Python3"), powershell.index('Install-AppAtomic $srcDir $AppDir'))

    def test_online_installers_reject_untrusted_accelerators_and_oversized_archives(self):
        shell = (ROOT / "install.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8-sig")
        self.assertNotIn("ghfast.top", shell + powershell)
        self.assertNotIn("gh-proxy.com", shell + powershell)
        self.assertIn("20971520", shell)
        self.assertIn("20MB", powershell)
        self.assertIn("越界路径", shell)

    def test_online_installers_clean_temporary_directories(self):
        shell = (ROOT / "install.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('rm -rf "$TMP"', shell)
        self.assertIn("Remove-Item $tmp -Recurse -Force", powershell)


if __name__ == "__main__":
    unittest.main(verbosity=2)
