#!/usr/bin/env python3
"""回归测试：shim 目标解析不得指向 AgentBoot 自己的 shim。

背景（v1.5.1 实测踩坑，v1.5.2 修复）：在线安装/重装时，旧代码用
find_bin 解析真身，而 find_bin 先搜 shim 目录——机器上已有旧 shim 时
返回旧 shim 自身，新 shim 的 exec 行指向自己 → `exec` 死循环，
命令永远跑不起来。全新机器没有旧 shim 所以复现不了，只有重装/
多 agent 场景才炸。

修复：resolve_shim_target——npm prefix 优先，PATH 跳过自身 shim
目录，旧 shim 的 exec 目标带环保护；write_online_shim 再加一道
「拒绝写入指向自身 shim 的 shim」的防御。
"""

import os
import sys
import contextlib
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402

# Windows 上 AgentBoot 的 shim 是 <bin>.cmd，npm 真身调用行也是 `"..." %*` 形态
BIN_NAME = "opencode" if menu.POSIX else "opencode.cmd"


def shim_call_line(target):
    """按当前平台生成 shim 里的调用行（与 write_online_shim 的写法一致）。"""
    if menu.POSIX:
        return 'exec "%s" "$@"\n' % target
    return '"%s" %%*\r\n' % target


class ShimTargetResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.bin_dir = root / "shim-bin"        # AgentBoot shim 目录
        self.prefix_bin = root / "npm-prefix/bin"  # npm prefix bin（真身在这）
        self.home_bin = root / "other-bin"       # PATH 上的无关目录
        for d in (self.bin_dir, self.prefix_bin, self.home_bin):
            d.mkdir(parents=True)
        self.real = self.prefix_bin / BIN_NAME
        self.real.write_text("#!/bin/sh\necho real\n")
        self.real.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    @contextlib.contextmanager
    def _patched(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                menu, "shim_bin_dir", return_value=str(self.bin_dir)))
            stack.enter_context(mock.patch.object(
                menu, "shim_bin_dirs", return_value=[str(self.bin_dir)]))
            stack.enter_context(mock.patch.object(
                menu, "prefix_bin_dirs", return_value=[str(self.prefix_bin)]))
            stack.enter_context(mock.patch.object(
                menu, "AB_HOME", str(self.tmp.name)))
            yield

    def test_prefers_prefix_binary_over_existing_shim(self):
        """复现 bug 的场景：shim 目录里已有旧 shim，必须解析到 prefix 真身。"""
        old_shim = self.bin_dir / BIN_NAME
        old_shim.write_text(shim_call_line(self.real))
        with self._patched():
            self.assertEqual(menu.resolve_shim_target("opencode"), str(self.real))

    def test_skips_self_referencing_shim(self):
        """v1.5.1 写出的自指 shim 不得被当真身返回。"""
        broken = self.bin_dir / BIN_NAME
        broken.write_text(shim_call_line(broken))
        with self._patched():
            # prefix 里没有真身、PATH 上也没有 → 解析失败而不是返回死循环 shim
            menu.prefix_bin_dirs.return_value = []
            with mock.patch.object(menu.shutil, "which", return_value=None):
                self.assertIsNone(menu.resolve_shim_target("opencode"))

    def test_follows_old_shim_exec_target_when_nothing_else(self):
        """真身只在旧 shim 的 exec 目标里时，沿目标解析（不返回 shim 自身）。"""
        old_shim = self.bin_dir / BIN_NAME
        old_shim.write_text(shim_call_line(self.real))
        with self._patched(), \
                mock.patch.object(menu, "prefix_bin_dirs", return_value=[]), \
                mock.patch.object(menu.shutil, "which", return_value=None):
            self.assertEqual(menu.resolve_shim_target("opencode"), str(self.real))

    def test_path_candidate_outside_shim_dirs_is_used(self):
        elsewhere = self.home_bin / BIN_NAME
        elsewhere.write_text("#!/bin/sh\necho elsewhere\n")
        elsewhere.chmod(0o755)
        with self._patched(), \
                mock.patch.object(menu, "prefix_bin_dirs", return_value=[]), \
                mock.patch.object(menu.shutil, "which",
                                  return_value=str(elsewhere)):
            self.assertEqual(menu.resolve_shim_target("opencode"), str(elsewhere))

    def test_missing_binary_returns_none(self):
        with self._patched(), \
                mock.patch.object(menu, "prefix_bin_dirs", return_value=[]), \
                mock.patch.object(menu.shutil, "which", return_value=None):
            self.assertIsNone(menu.resolve_shim_target("opencode"))


class WriteShimGuardTests(unittest.TestCase):
    """write_online_shim 的兜底防御：目标在 shim 目录内一律拒绝。"""

    AGENT = {"id": "opencode", "name": "OpenCode", "bin": "opencode"}

    def test_refuses_shim_pointing_at_own_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "shim-bin"
            bin_dir.mkdir()
            me = bin_dir / BIN_NAME
            me.write_text("#!/bin/sh\n")
            with mock.patch.object(menu, "shim_bin_dir", return_value=str(bin_dir)), \
                    mock.patch.object(menu, "shim_bin_dirs",
                                      return_value=[str(bin_dir)]):
                self.assertFalse(menu.write_online_shim(
                    self.AGENT, str(me), {}, []))
            # 什么都没写进去
            self.assertEqual(me.read_text(encoding="utf-8"), "#!/bin/sh\n")

    def test_writes_shim_for_real_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "shim-bin"
            real_dir = Path(tmp) / "prefix-bin"
            bin_dir.mkdir()
            real_dir.mkdir()
            real = real_dir / BIN_NAME
            real.write_text("#!/bin/sh\necho real\n")
            real.chmod(0o755)
            with mock.patch.object(menu, "shim_bin_dir", return_value=str(bin_dir)), \
                    mock.patch.object(menu, "shim_bin_dirs",
                                      return_value=[str(bin_dir)]):
                self.assertTrue(menu.write_online_shim(
                    self.AGENT, str(real), {}, []))
            written = (bin_dir / BIN_NAME).read_text(encoding="utf-8")
            self.assertIn(shim_call_line(real).strip(), written)
            self.assertNotIn('exec "%s/opencode" "$@"\n\n' % bin_dir, written)


if __name__ == "__main__":
    unittest.main(verbosity=2)
