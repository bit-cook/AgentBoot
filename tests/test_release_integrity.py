#!/usr/bin/env python3
"""Release integrity and transactional installer regressions."""

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OnlinePackageTests(unittest.TestCase):
    def test_builder_emits_reproducible_hash_sidecars(self):
        spec = importlib.util.spec_from_file_location(
            "build_online", ROOT / "scripts" / "build-online.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            module.OUTPUTS = {
                "tar": out / "agentboot-online-v1.0.0.tar.gz",
                "zip": out / "agentboot-online-v1.0.0.zip",
            }
            module.main()
            first = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in module.OUTPUTS.values()}
            module.main()
            second = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in module.OUTPUTS.values()}
            self.assertEqual(first, second)
            for path in module.OUTPUTS.values():
                sidecar = Path(str(path) + ".sha256")
                self.assertTrue(sidecar.is_file())
                self.assertEqual(sidecar.read_text(encoding="ascii").split()[0], first[path.name])

    def test_posix_installer_requires_checksum_and_atomic_stage(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('"${url}.sha256"', text)
        self.assertIn("verify_sha256", text)
        self.assertIn('app.new.', text)
        self.assertIn('app.old.', text)
        self.assertNotIn('cp -R "${SRC_DIR}/." "$APP_DIR/"', text)

    def test_windows_installer_requires_checksum_and_atomic_stage(self):
        text = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('"$u.sha256"', text)
        self.assertIn("Get-Sha256", text)
        self.assertIn("Install-AppAtomic", text)
        self.assertNotIn("Copy-Item -Path (Join-Path $srcDir '*') -Destination $AppDir", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
