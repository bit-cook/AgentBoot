#!/usr/bin/env python3
"""Offline builder must reject incomplete requested payloads."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "tools" / "validate_offline_payload.py"
ZIP_TREE = ROOT / "scripts" / "tools" / "zip_tree.py"


class OfflinePayloadValidationTests(unittest.TestCase):
    def test_missing_npm_payload_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            (stage / "agents").mkdir()
            (stage / "agents" / "registry.json").write_text(json.dumps({"agents": [{
                "id": "demo", "method": "npm", "npm": "@scope/demo", "bin": "demo", "offline": True}]}),
                encoding="utf-8")
            (stage / "payloads" / "node" / "linux-x64").mkdir(parents=True)
            result = subprocess.run([sys.executable, str(VALIDATOR), str(stage),
                                     "linux-x64", "demo"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing package.json", result.stderr)

    def test_zip_tool_preserves_every_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tree"
            root.mkdir()
            (root / "a.txt").write_text("a", encoding="ascii")
            (root / "b.txt").write_text("b", encoding="ascii")
            output = Path(tmp) / "tree.zip"
            subprocess.run([sys.executable, str(ZIP_TREE), str(output), str(root), "AgentBoot"],
                           check=True)
            import zipfile
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {"AgentBoot/a.txt", "AgentBoot/b.txt"})

    def test_unsupported_requested_platform_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            (stage / "agents").mkdir()
            (stage / "agents" / "registry.json").write_text(json.dumps({"agents": [{
                "id": "coco", "method": "script", "bin": "coco", "offline": True,
                "os": ["linux", "darwin"]}]}),
                encoding="utf-8")
            result = subprocess.run([sys.executable, str(VALIDATOR), str(stage),
                                     "win-x64", "coco"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not support", result.stderr)

    def test_agent_not_marked_offline_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            (stage / "agents").mkdir()
            (stage / "agents" / "registry.json").write_text(json.dumps({"agents": [{
                "id": "online", "method": "npm", "npm": "online", "bin": "online", "offline": False}]}),
                encoding="utf-8")
            result = subprocess.run([sys.executable, str(VALIDATOR), str(stage), "linux-x64", "online"],
                                    capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not marked offline-capable", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
