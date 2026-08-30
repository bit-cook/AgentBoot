#!/usr/bin/env python3
"""Offline Agent updates roll back when shim commit fails."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class OfflineTransactionTests(unittest.TestCase):
    def test_existing_payload_restored_when_shim_fails(self):
        agent = {"id": "demo", "name": "Demo", "bin": "demo", "method": "npm",
                 "npm": "demo", "node": ">=18"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / "payloads"
            source = payload / "agents" / "demo" / menu.plat_id() / "node_modules" / "demo"
            source.mkdir(parents=True)
            (source / "package.json").write_text('{"bin":{"demo":"demo.js"}}', encoding="utf-8")
            (source / "demo.js").write_text("new", encoding="utf-8")
            agents_dir = root / "managed"
            old = agents_dir / "demo" / "node_modules" / "demo"
            old.mkdir(parents=True)
            (old / "old.txt").write_text("keep", encoding="utf-8")
            with mock.patch.object(menu, "AGENTS_DIR", str(agents_dir)), \
                    mock.patch.object(menu, "RUNTIME_DIR", str(root / "runtime")), \
                    mock.patch.object(menu, "load_registry", return_value=[agent]), \
                    mock.patch.object(menu, "find_payload_dir", return_value=str(payload)), \
                    mock.patch.object(menu.shutil, "which", return_value="node"), \
                    mock.patch.object(menu, "node_ok", return_value=True), \
                    mock.patch.object(menu, "write_shim", return_value=False), \
                    mock.patch.object(menu, "ensure_path_registered"):
                failures = menu.offline_install(["demo"], str(payload))
            self.assertEqual(failures, ["demo"])
            self.assertTrue((old / "old.txt").is_file())


if __name__ == "__main__": unittest.main(verbosity=2)
