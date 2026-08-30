#!/usr/bin/env python3
"""Static guarantees for coordinated release publication."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_supports_prerelease_dry_run_and_tag_only_publish(self):
        text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("pull_request:", text)
        self.assertIn("if: github.ref_type == 'tag'", text)
        self.assertIn("Smoke install, execute, and uninstall", text)
        self.assertIn("--prerelease", text)
        self.assertIn("verify-live-release.py", text)
        self.assertIn("--prerelease=false --latest", text)
        self.assertIn("needs: [validate, online, offline-linux, offline-windows]", text)
        self.assertIn("$smokeHome", text)
        self.assertNotIn("$home =", text)
        self.assertIn("install-offline.sh\" codex", text)
        self.assertIn("install-offline.ps1\" -Agents codex", text)

    def test_live_verifier_covers_primary_and_mirror(self):
        text = (ROOT / "scripts/verify-live-release.py").read_text(encoding="utf-8")
        self.assertIn("https://boot.ide.pub/health", text)
        self.assertIn("https://bit-cook.github.io/AgentBoot", text)
        self.assertIn("checksum mismatch", text)
        self.assertIn('"Range": "bytes=0-99"', text)
        self.assertIn("expected_status=206", text)

    def test_worker_has_reproducible_wrangler_config(self):
        text = (ROOT / "cloudflare/wrangler.jsonc").read_text(encoding="utf-8")
        self.assertIn('"name": "boot"', text)
        self.assertIn('"pattern": "boot.ide.pub/*"', text)

    def test_worker_health_checks_assets_and_proxy_forwards_ranges(self):
        text = (ROOT / "cloudflare/worker.js").read_text(encoding="utf-8")
        self.assertIn("const required =", text)
        self.assertIn("assets[name] = response.status", text)
        self.assertIn('"Range", "If-Range"', text)
        self.assertIn("cacheEverything: !requestHeaders.has(\"Range\")", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
