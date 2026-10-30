#!/usr/bin/env python3
"""回归测试：安装器 PATH 注册与菜单输入重定向。

覆盖 v1.4.4 实测踩过的两个坑：
1. rc 文件不存在时静默跳过 PATH 写入 → 新系统（root 无 ~/.bashrc）
   装完 agentboot 命令找不到。修复：先创建再追加。
2. curl | sh 安装时脚本 stdin 是耗尽管道，菜单不重定向 /dev/tty
   则一启动就 EOF 退出。修复：read/exec 均走 /dev/tty。

测试方式：从安装脚本中原样抽出 PATH 注册代码段，在临时 HOME 中
真实执行，断言文件结果（行为级，不是静态 grep）。
"""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ONLINE = ROOT / "install.sh"
OFFLINE = ROOT / "scripts" / "install-offline.sh"
BLOCK_MARKER = "# >>> agentboot >>>"

STUBS = """ok() { :; }
err() { :; }
say() { :; }
step() { :; }
BIN_DIR="/opt/agentboot/bin"
export HOME="%s"
export PATH="%s"
"""


def extract_path_block(script_path):
    """抽出 `case ":$PATH:" in ... esac` 整段（含 PATH 注册注释）。"""
    lines = script_path.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        if "PATH 注册" in line or "PATH（幂等写入）" in line:
            start = i
            break
    if start is None:
        raise AssertionError("找不到 PATH 注册段: %s" % script_path)
    for j in range(start, len(lines)):
        if lines[j] == "esac":
            return "\n".join(lines[start:j + 1])
    raise AssertionError("PATH 注册段没有 esac 收尾: %s" % script_path)


def run_path_block(script_path, home, path="/usr/bin:/bin"):
    block = extract_path_block(script_path)
    script = STUBS % (home, path) + "\n" + block + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(script)
        tmp = fh.name
    try:
        return subprocess.run(["bash", tmp], capture_output=True, text=True, timeout=30)
    finally:
        Path(tmp).unlink(missing_ok=True)


def rc_content(home, name):
    p = Path(home) / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


class OnlineInstallerPathTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_missing_rc_files(self):
        """新系统无 ~/.bashrc / ~/.profile：必须创建并写入 PATH 块。"""
        self.assertFalse((Path(self.home) / ".bashrc").exists())
        run_path_block(ONLINE, self.home)
        for name in (".bashrc", ".profile"):
            content = rc_content(self.home, name)
            self.assertIn(BLOCK_MARKER, content, "%s 未写入 PATH 块" % name)
            self.assertIn("agentboot/bin", content)

    def test_is_idempotent(self):
        """跑两遍：PATH 块只能出现一次。"""
        run_path_block(ONLINE, self.home)
        run_path_block(ONLINE, self.home)
        content = rc_content(self.home, ".bashrc")
        self.assertEqual(content.count(BLOCK_MARKER), 1)

    def test_preserves_existing_content(self):
        """已有 rc 内容：原样保留，块追加一次。"""
        rc = Path(self.home) / ".bashrc"
        rc.write_text("export EDITOR=vim\n", encoding="utf-8")
        run_path_block(ONLINE, self.home)
        content = rc_content(self.home, ".bashrc")
        self.assertIn("export EDITOR=vim", content)
        self.assertEqual(content.count(BLOCK_MARKER), 1)

    def test_skips_when_bin_dir_already_in_path(self):
        """BIN_DIR 已在 PATH：保持旧行为，什么都不写。"""
        run_path_block(ONLINE, self.home, path="/usr/bin:/bin:/opt/agentboot/bin")
        self.assertEqual(rc_content(self.home, ".bashrc"), "")
        self.assertFalse((Path(self.home) / ".profile").exists())

    def test_final_hint_mentions_bashrc(self):
        """完成提示要告诉用户 PATH 写进了哪个文件。"""
        source = ONLINE.read_text(encoding="utf-8")
        self.assertIn('grep -q "# >>> agentboot >>>" "${HOME}/.bashrc"', source)
        self.assertIn("source ~/.bashrc", source)


class OfflineInstallerPathTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_missing_rc_files(self):
        run_path_block(OFFLINE, self.home)
        for name in (".bashrc", ".profile"):
            self.assertIn(BLOCK_MARKER, rc_content(self.home, name),
                          "%s 未写入 PATH 块" % name)

    def test_is_idempotent(self):
        run_path_block(OFFLINE, self.home)
        run_path_block(OFFLINE, self.home)
        self.assertEqual(rc_content(self.home, ".bashrc").count(BLOCK_MARKER), 1)


class MenuTtyRedirectTests(unittest.TestCase):
    """菜单输入必须走 /dev/tty，否则 curl | sh 下 EOF 秒退。"""

    def test_online_installer_redirects_menu_to_tty(self):
        source = ONLINE.read_text(encoding="utf-8")
        self.assertIn('read ans < /dev/tty', source)
        self.assertIn('exec "$PY" "${APP_DIR}/core/menu.py" < /dev/tty', source)

    def test_offline_installer_redirects_menu_to_tty(self):
        source = OFFLINE.read_text(encoding="utf-8")
        self.assertIn('read ans < /dev/tty', source)
        self.assertIn('exec "$PY" "${APP_DIR}/core/menu.py" < /dev/tty', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
