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


if __name__ == "__main__":
    unittest.main(verbosity=2)
