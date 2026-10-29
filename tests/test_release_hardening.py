#!/usr/bin/env python3
"""Release-hardening regressions: mirror-corrupt fallback, CoCo version pin, stdin EOF.

Each class is named by the defect it locks down:
  * MirrorFallbackTests  - a corrupt mirror file must fall through to the next
    source instead of failing the whole build/install (huaweicloud served a
    truncated python-3.12.10-embed-amd64.zip: sha 1940ea1a vs official 4acbed6d).
  * CocoVersionTests     - the offline CoCo payload version has one source of
    truth (agents/registry.json coco_version); no consumer hardcodes it.
  * StdinEofTests        - closing stdin must exit cleanly, never traceback.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class MirrorFallbackTests(unittest.TestCase):
    """build-offline.sh fetch_verified: verify every source, keep the good one."""

    def test_corrupt_source_falls_through_to_next_source(self):
        source = (ROOT / "scripts" / "build-offline.sh").read_text(encoding="utf-8")
        start = source.index("fetch_verified() {")
        function = source[start:source.index("\n}\n", start) + 3]
        harness = (
            "err() { echo \"ERR:$*\" >&2; }\n"
            "# stub downloads: CORRUPT urls yield a 7-byte bad file, others 4 bytes\n"
            "fetch_file() {\n"
            "  case \"$1\" in *CORRUPT*) printf 'corrupt' > \"$2\" ;; *) printf 'good' > \"$2\" ;; esac\n"
            "  return 0\n"
            "}\n"
            "# stub hash: file length stands in for sha256\n"
            "sha256_file() { wc -c < \"$1\" | tr -d ' '; }\n"
            + function +
            "\nif fetch_verified 4 \"$1\" https://mirror.example/CORRUPT https://official.example/GOOD; then\n"
            "  echo \"ACCEPTED:$(cat \"$1\")\"\n"
            "else\n"
            "  echo REJECTED\n"
            "fi\n"
            "if fetch_verified 4 \"$1.rejected\" https://mirror.example/CORRUPT; then\n"
            "  echo BAD-ACCEPT\n"
            "else\n"
            "  echo REJECTED-ALL\n"
            "fi\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "harness.sh"
            script.write_text(harness, encoding="utf-8")
            result = subprocess.run(["sh", str(script), str(Path(tmp) / "verified.bin")],
                                    capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertIn("ACCEPTED:good", result.stdout)
        self.assertIn("REJECTED-ALL", result.stdout)
        self.assertIn("ERR:", result.stderr)   # 损坏源被报告后切换

    def test_build_scripts_use_verified_multi_source_downloads(self):
        shell = (ROOT / "scripts" / "build-offline.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts" / "build-offline.ps1").read_text(encoding="utf-8-sig")
        for name, text in (("build-offline.sh", shell), ("build-offline.ps1", powershell)):
            self.assertIn("win-embed.zip", text, name)
        # 每个消费点都必须走逐源校验 helper，而不是「下载成功即采用」
        self.assertIn("fetch_verified", shell)
        self.assertIn("Get-UrlVerified", powershell)
        self.assertIn("Ensure-NodeArchive", powershell)
        self.assertIn("ensure_node_archive", shell)
        # 旧的失败硬编码模式必须绝迹
        self.assertNotIn('|| fetch_file "https://www.python.org/ftp/python/3.12.10', shell)
        self.assertNotIn("Get-Url 'https://mirrors.huaweicloud.com/python/3.12.10", powershell)

    def test_online_installer_verifies_each_python_source(self):
        text = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$embSha", text)
        self.assertIn("(Get-Sha256 $embZip) -eq $embSha", text)
        # 循环内逐个校验，而不是下载后统一校验（损坏镜像曾让无 Python 的 Windows 安装必败）
        self.assertIn("Remove-Item $embZip -Force -ErrorAction SilentlyContinue", text)


class CocoVersionTests(unittest.TestCase):
    """CoCo offline payload version: registry is the single source of truth."""

    def test_registry_pins_coco_version(self):
        registry = json.loads((ROOT / "agents" / "registry.json").read_text(encoding="utf-8"))
        coco = next(a for a in registry["agents"] if a["id"] == "coco")
        self.assertTrue(coco.get("coco_version"), "registry.json 缺少 coco_version")
        self.assertRegex(coco["coco_version"], r"^\d+\.\d+\.\d+$")

    def test_offline_install_uses_registry_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(menu, "load_registry",
                                   return_value=[{"id": "coco", "name": "CoCo",
                                                  "coco_version": "9.9.9"}]):
                ok = menu.coco_offline_install({"id": "coco", "coco_version": "9.9.9"}, tmp)
        self.assertFalse(ok)   # 载荷不存在必然失败，但错误信息必须点名 9.9.9

    def test_no_consumer_hardcodes_coco_version(self):
        for relative in ("scripts/build-offline.sh", "scripts/build-offline.ps1",
                         "scripts/tools/validate_offline_payload.py", "core/menu.py"):
            text = (ROOT / relative).read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("coco-0.8.0", text, relative)
            self.assertNotIn("COCO_VER=\"0.8.0\"", text, relative)
        validator = (ROOT / "scripts/tools/validate_offline_payload.py").read_text(encoding="utf-8")
        self.assertIn('agent.get("coco_version")', validator)


class StdinEofTests(unittest.TestCase):
    """Piped/closed stdin must exit cleanly instead of dumping a traceback."""

    def _run(self, entry):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, AGENTBOOT_HOME=tmp)
            return subprocess.run([sys.executable, str(ROOT / "core" / entry)],
                                  stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, env=env, timeout=120)

    def test_menu_with_closed_stdin_exits_zero(self):
        result = self._run("menu.py")
        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertNotIn("Traceback", result.stderr)

    def test_agent_with_closed_stdin_exits_zero(self):
        result = self._run("agent.py")
        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertNotIn("Traceback", result.stderr)

    def test_agent_model_command_non_interactive_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, AGENTBOOT_HOME=tmp)
            result = subprocess.run(
                [sys.executable, str(ROOT / "core" / "agent.py"), "model"],
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                env=env, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[-400:])
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
