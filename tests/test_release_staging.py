#!/usr/bin/env python3
"""Release staging excludes ambient and ignored workspace files."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
STAGER = ROOT / "scripts" / "tools" / "stage_application.py"


class ReleaseStagingTests(unittest.TestCase):
    def test_online_package_excludes_deploy_and_benchmark_sources(self):
        source = (ROOT / "scripts" / "build-online.py").read_text(encoding="utf-8")
        self.assertNotIn('"cloudflare", "core"', source)
        self.assertIn('"scripts/benchmark-performance.py"', source)
        self.assertIn('"scripts/sync-web-assets.py"', source)

    def test_explicit_stage_excludes_workspace_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "stage"
            subprocess.run([sys.executable, str(STAGER), str(ROOT), str(stage)], check=True)
            self.assertTrue((stage / "core" / "agent.py").is_file())
            self.assertTrue((stage / "core" / "launch.py").is_file())
            for relative in ("tests", "pages", ".github", "results.tsv", "run.log", ".env"):
                self.assertFalse((stage / relative).exists(), relative)

    def test_builders_use_explicit_stager(self):
        for relative in ("scripts/build-offline.sh", "scripts/build-offline.ps1"):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertIn("stage_application.py", text, relative)

    def test_online_package_ships_precompiled_bytecode(self):
        """v1.7.0 启动性能优化：安装包必须带 __pycache__/*.pyc。

        首启免现场编译（实测省 5.1ms）；.pyc 带 Python 魔数，目标机版本
        不匹配时解释器自动忽略重编译，无害。构建脚本需先预编译再打包，
        且不得再把 __pycache__/.pyc 排除掉。
        """
        source = (ROOT / "scripts" / "build-online.py").read_text(encoding="utf-8")
        self.assertIn("def precompile_bytecode", source)
        self.assertIn("precompile_bytecode()", source)
        self.assertNotIn('"__pycache__"', source.split("SKIP_PARTS = ")[1].split(")")[0])
        self.assertNotIn('path.suffix != ".pyc"', source)

    def test_staged_application_precompiles_core(self):
        """离线包 stage 后 core/ 必须带 .pyc（首启同样免编译）。"""
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "stage"
            subprocess.run([sys.executable, str(STAGER), str(ROOT), str(stage)], check=True)
            pyc = list((stage / "core" / "__pycache__").glob("*.pyc"))
            self.assertTrue(pyc, "staged core/ 缺少预编译 .pyc")
            names = {p.name.split(".")[0] for p in pyc}
            for module in ("agent", "menu", "i18n", "launch"):
                self.assertIn(module, names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
