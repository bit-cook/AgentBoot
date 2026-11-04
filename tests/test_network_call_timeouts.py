#!/usr/bin/env python3
"""回归：网络类子进程命令必须带超时与进程树清理。

背景（v1.8.0 全面排查）：hermes 安装流、npm/pip 卸载、官方脚本安装器、
离线构建等调用点曾用裸 subprocess.run——网络挂起时菜单无限等待，用户
只能 kill。npm_install 早有 NPM_INSTALL_TIMEOUT + 进程树清理，v1.8.0
把同等保护推广到全部网络类调用点（run_with_timeout / _run_npm_process）。

本测试双保险：
1) 行为测试——run_with_timeout 超时后必须返回 None 且杀整棵进程树；
2) 静态门——关键调用点不得再出现裸 subprocess.run（防回归）。
"""

from pathlib import Path
import os
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


@unittest.skipIf(os.name == "nt", "POSIX process-group regression")
class RunWithTimeoutTests(unittest.TestCase):
    def test_timeout_returns_none_and_kills_tree(self):
        """超时必须返回 None，且后台子进程不得存活（进程树清理）。"""
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "survived"
            command = "(sleep 4; touch %s) & sleep 30" % marker
            started = time.time()
            code = menu.run_with_timeout(["sh", "-c", command], timeout=2)
            elapsed = time.time() - started
            self.assertIsNone(code, "超时必须以 None 表示失败")
            self.assertLess(elapsed, 10, "超时后应迅速返回，不得等到子进程自然结束")
            time.sleep(5)
            self.assertFalse(marker.exists(), "超时后后台子进程必须被杀掉")

    def test_success_returns_zero(self):
        self.assertEqual(menu.run_with_timeout(["true"], timeout=10), 0)

    def test_failure_returns_nonzero(self):
        code = menu.run_with_timeout(["sh", "-c", "exit 3"], timeout=10)
        self.assertEqual(code, 3)


class NetworkCallSitesUseTimeoutTests(unittest.TestCase):
    """静态门：网络类调用点不得回归到裸 subprocess.run。"""

    def test_hermes_and_script_and_pip_and_build_sites_are_guarded(self):
        source = (ROOT / "core" / "menu.py").read_text(encoding="utf-8")
        # hermes npm 安装与 npm 卸载走 _run_npm_process（带 ticker + 超时）
        self.assertIn("code, _output = _run_npm_process(cmd, env)", source)
        self.assertIn("code, _output = _run_npm_process(cmd, child_env())", source)
        # 官方脚本安装器 / pip / postinstall / 构建走 run_with_timeout
        for label in ("安装脚本 ", "pip 卸载 ", "pip ", "Hermes postinstall ", "离线构建 "):
            self.assertIn('label="%s"' % label, source, label)
        # 这些站点不得再出现裸 run（uninstall 两处 + 脚本 + pip×2 + hermes×2 + build）
        bare = source.count("subprocess.run(cmd")
        self.assertEqual(bare, 0, "仍有 %d 处裸 subprocess.run(cmd" % bare)


if __name__ == "__main__":
    unittest.main(verbosity=2)
