#!/usr/bin/env python3
"""Security regressions for remote script installation."""

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class ScriptInstallTests(unittest.TestCase):
    def agent(self, url):
        return {"id": "custom", "name": "Custom", "bin": "custom",
                "method": "script", "script": url}

    def test_rejects_non_https_url(self):
        with mock.patch.object(menu, "_download_script") as download:
            self.assertFalse(menu.install_via_script(self.agent("http://example.test/install.sh")))
        download.assert_not_called()

    def test_posix_executes_downloaded_file_without_shell_interpolation(self):
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(menu, "POSIX", True), \
                mock.patch.object(menu, "cn_mode", return_value=False), \
                mock.patch.object(menu, "_download_script", return_value="/tmp/agent;touch-pwned.sh"), \
                mock.patch.object(menu.subprocess, "run", return_value=completed) as run, \
                mock.patch.object(menu.os, "remove"):
            self.assertTrue(menu.install_via_script(self.agent("https://example.test/install.sh")))
        self.assertEqual(run.call_args.args[0], ["sh", "/tmp/agent;touch-pwned.sh"])
        self.assertNotIn("-c", run.call_args.args[0])

    def test_windows_uses_file_argument_not_iex(self):
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.object(menu, "POSIX", False), \
                mock.patch.object(menu, "cn_mode", return_value=False), \
                mock.patch.object(menu, "_download_script", return_value="C:\\Temp\\agent.ps1"), \
                mock.patch.object(menu.subprocess, "run", return_value=completed) as run, \
                mock.patch.object(menu.os, "remove"):
            self.assertTrue(menu.install_via_script(self.agent("https://example.test/install.ps1")))
        command = run.call_args.args[0]
        self.assertEqual(command[-2:], ["-File", "C:\\Temp\\agent.ps1"])
        self.assertNotIn("iex", " ".join(command).lower())

    def test_temporary_script_is_removed_after_failure(self):
        completed = subprocess.CompletedProcess([], 1)
        with mock.patch.object(menu, "POSIX", True), \
                mock.patch.object(menu, "cn_mode", return_value=False), \
                mock.patch.object(menu, "_download_script", return_value="/tmp/agent.sh"), \
                mock.patch.object(menu.subprocess, "run", return_value=completed), \
                mock.patch.object(menu.os, "remove") as remove:
            self.assertFalse(menu.install_via_script(self.agent("https://example.test/install.sh")))
        remove.assert_called_once_with("/tmp/agent.sh")

    def test_downloader_rejects_https_to_http_redirect(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return "http://example.test/install.sh"

            def read(self, _size):
                return b"echo unsafe"

        with mock.patch("urllib.request.urlopen", return_value=Response()), \
                self.assertRaisesRegex(ValueError, "非 HTTPS"):
            menu._download_script("https://example.test/install.sh", ".sh")


if __name__ == "__main__":
    unittest.main(verbosity=2)
