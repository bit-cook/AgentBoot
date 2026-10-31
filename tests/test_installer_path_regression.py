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
import shutil
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
    """抽出 PATH 注册的 `case ... esac` 整段（含节标题注释）。

    起点必须匹配节标题本身（`# ---------- 4. PATH 注册（幂等）----------`），
    不能只搜「PATH 注册」——文件头部的目录选择注释里也含这个词。
    """
    lines = script_path.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (stripped.startswith("#") and "PATH 注册" in stripped
                and "幂等" in stripped) or \
           (stripped.startswith("#") and "PATH（幂等写入）" in stripped):
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


class ProbeFallbackTests(unittest.TestCase):
    """v1.6.x 修复：探写失败回落 ~/.local/bin + mktemp 容错（新机器实测三个场景的回归）。"""

    PROBE_STUBS = (
        'err() { echo "ERR:$*" >&2; }\n'
        "ok() { :; }\n"
        "say() { :; }\n"
        "step() { :; }\n"
        'BIN_DIR="%s"\n'
        'BIN_SUDO="%s"\n'
        'export HOME="%s"\n'
        'export TMPDIR="%s"\n'
    )

    def extract_probe_block(self, script_path):
        lines = script_path.read_text(encoding="utf-8").splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("probe_bin_dir()"))
        end = next(i for i, l in enumerate(lines) if "落盘：拒绝符号链接" in l)
        return "\n".join(lines[start:end])

    def run_probe(self, script_path, bin_dir, bin_sudo="", tmpdir="/tmp"):
        home = tempfile.mkdtemp(prefix="ab-probe-home-")
        self.addCleanup(shutil.rmtree, home, True)
        block = self.extract_probe_block(script_path)
        script = (self.PROBE_STUBS % (bin_dir, bin_sudo, home, tmpdir)) + "\n" + block + \
            '\necho "FINAL_BIN_DIR=$BIN_DIR"\necho "FINAL_TMP_BASE=$TMP_BASE"\n'
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
            fh.write(script)
            tmp = fh.name
        try:
            proc = subprocess.run(["bash", tmp], capture_output=True, text=True, timeout=30)
            out = dict(
                line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line
            )
            return proc, out, home
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_falls_back_to_local_bin_when_bin_dir_unwritable(self):
        """/proc 下 root 也建不了文件：探写失败必须回落到 ~/.local/bin 且安装继续。"""
        proc, out, home = self.run_probe(ONLINE, "/proc/ab-unwritable-probe")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out["FINAL_BIN_DIR"], f"{home}/.local/bin")
        self.assertTrue(Path(home, ".local/bin").is_dir())

    def test_offline_installer_falls_back_too(self):
        proc, out, home = self.run_probe(OFFLINE, "/proc/ab-unwritable-probe")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out["FINAL_BIN_DIR"], f"{home}/.local/bin")

    def test_keeps_writable_bin_dir(self):
        """BIN_DIR 可写时不做任何回落（不破坏 root/usr-local 正常路径）。"""
        with tempfile.TemporaryDirectory() as bin_dir:
            proc, out, _ = self.run_probe(ONLINE, bin_dir)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(out["FINAL_BIN_DIR"], bin_dir)

    def test_tmp_base_falls_back_when_tmpdir_unwritable(self):
        """sudo 分支：TMPDIR 不可写时 mktemp 回退 /tmp（Bug 2 回归）。"""
        proc, out, _ = self.run_probe(
            ONLINE, "/tmp", bin_sudo="true", tmpdir="/proc/ab-no-such-tmpdir"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(
            out["FINAL_TMP_BASE"].startswith("/tmp/"),
            "TMP_BASE 未回退到 /tmp: %s" % out.get("FINAL_TMP_BASE"),
        )

    def test_both_installers_have_probe_and_rollback(self):
        """静态断言：两个安装器都带探写回落、mktemp 容错与失败回滚。"""
        for script in (ONLINE, OFFLINE):
            source = script.read_text(encoding="utf-8")
            self.assertIn("probe_bin_dir()", source, script.name)
            self.assertIn("回落到 ~/.local/bin", source, script.name)
            self.assertIn("mktemp -d -p /tmp", source, script.name)
            self.assertIn("rollback_install()", source, script.name)
            self.assertNotIn('TMP_BASE="$(mktemp -d)"', source, script.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
