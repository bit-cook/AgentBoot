#!/usr/bin/env python3
"""menu.py 惰性模块代理的行为锁（v1.7.0 启动性能优化）。

背景：顶层导入 subprocess/shutil/platform 让每次 `agentboot` 启动多付约
15ms（实测 import menu ≈ 67ms vs import agent ≈ 50ms）。改为 _LazyModule
代理后：
- 内部裸名引用（subprocess.run）必须可用（PEP 562 的模块 __getattr__
  管不了模块内部引用，所以用代理对象而不是模块级 __getattr__）；
- mock.patch.object(menu, "subprocess") / patch.object(menu.subprocess,
  "Popen") 必须照旧工作（设置属性要转发到真模块）；
- 首次使用后才真正导入（导入时这三个模块不能已在 sys.modules 被加载）。
"""

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class LazyModuleProxyTests(unittest.TestCase):
    def test_proxy_identity(self):
        for name in ("subprocess", "shutil", "platform"):
            self.assertIsInstance(getattr(menu, name), menu._LazyModule, name)

    def test_internal_reference_works(self):
        # 模块内部函数里的裸名引用（如 plat_id 里的 platform.system）
        self.assertTrue(menu.plat_id())
        self.assertIsInstance(menu.shutil.which("sh"), str)
        r = menu.subprocess.run(["echo", "ok"], capture_output=True)
        self.assertEqual(r.returncode, 0)

    def test_proxy_forwards_getattr_to_real_module(self):
        self.assertIs(menu.subprocess.run, subprocess.run)
        self.assertIs(menu.shutil.rmtree.__module__, "shutil")

    def test_patch_object_on_proxy_attribute_forwards(self):
        # mock.patch.object(menu.subprocess, "Popen")：设置必须转发到真模块
        with mock.patch.object(menu.subprocess, "Popen") as fake:
            self.assertIs(subprocess.Popen, fake)
        self.assertIs(subprocess.Popen, subprocess.Popen)  # 还原

    def test_patch_whole_module_still_works(self):
        # mock.patch.object(menu, "subprocess")：整体替换代理
        with mock.patch.object(menu, "subprocess") as fake:
            menu.subprocess.run(["x"])
        fake.run.assert_called_once_with(["x"])

    def test_unknown_lazy_name_raises(self):
        with self.assertRaises(AttributeError):
            menu._LazyModule("json")._ab_missing_attr

    def test_lazy_load_is_deferred(self):
        # 新进程里 import menu 后，重模块尚未被加载（惰性的意义所在）
        code = (
            "import sys; sys.path.insert(0, %r); import menu; "
            "print('subprocess' in sys.modules, 'shutil' in sys.modules, "
            "'platform' in sys.modules)" % str(ROOT / "core")
        )
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(out, ["False", "False", "False"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
