#!/usr/bin/env python3
"""安装脚本执行必须优先用 bash（历史 bug：一律 sh 执行 bash 脚本必炸）。

背景：AgentBoot 曾一律以 sh 执行下载的安装脚本，而官方安装脚本（coco 等）
是 bash 脚本（数组/[[ ]]/process substitution），dash 在第一个 bash 专用
语法处即 Syntax error。coco v0.8.2 修了脚本本身，这里守住调用侧。
"""

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class ScriptInterpreterTests(unittest.TestCase):
    def test_prefers_bash_when_available(self):
        with mock.patch("shutil.which", return_value="/usr/bin/bash"):
            self.assertEqual(menu._script_interpreter(), "bash")

    def test_falls_back_to_sh_without_bash(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(menu._script_interpreter(), "sh")

    def test_install_via_script_uses_interpreter(self):
        agent = {"id": "demo", "script": "https://example.com/install.sh"}
        with mock.patch.object(menu, "_download_script", return_value="/tmp/x.sh"), \
                mock.patch.object(menu, "_script_interpreter", return_value="bash"), \
                mock.patch.object(menu.subprocess, "run", return_value=mock.Mock(returncode=0)) as run, \
                mock.patch("os.remove"):
            self.assertTrue(menu.install_via_script(agent))
        run.assert_called_once()
        self.assertEqual(run.call_args[0][0][0], "bash")

    def test_install_via_script_rejects_non_https(self):
        self.assertFalse(menu.install_via_script({"script": "http://insecure/install.sh"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
