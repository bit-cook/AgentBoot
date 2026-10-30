#!/usr/bin/env python3
"""Worker 双源兜底测试：功能级（node 驱动）+ 源码级断言。

背景：GitHub Release CDN 对 Cloudflare Worker 间歇返回 618（本机直连却正常），
导致 /rel/ 大资产间歇 502。修复：Release 为主、Pages CDN（jsDelivr 镜像
gh-pages）兜底；health 用同一逻辑探测。功能测试 mock fetch 验证行为。
"""

from pathlib import Path
import shutil
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WorkerFallbackFunctionalTests(unittest.TestCase):
    """node 驱动 worker handler，mock fetch 断言双源行为。"""

    def setUp(self):
        if shutil.which("node") is None:
            self.skipTest("node 不可用")

    def test_worker_fallback_behavior(self):
        proc = subprocess.run(
            ["node", str(ROOT / "tests" / "worker_fallback_test.mjs")],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("WORKER-FALLBACK-ALL-PASS", proc.stdout)


class WorkerFallbackSourceTests(unittest.TestCase):
    def test_worker_declares_pages_cdn_fallback(self):
        text = (ROOT / "cloudflare" / "worker.js").read_text(encoding="utf-8")
        self.assertIn("cdn.jsdelivr.net", text)
        self.assertIn("PAGES_CDN", text)
        self.assertIn("fetchAsset", text)
        self.assertIn("proxyRelease", text)

    def test_health_uses_same_dual_source_logic(self):
        text = (ROOT / "cloudflare" / "worker.js").read_text(encoding="utf-8")
        self.assertIn("await fetchAsset(name, PROBE_HEADERS)", text)

    def test_rel_route_passes_incoming_request(self):
        text = (ROOT / "cloudflare" / "worker.js").read_text(encoding="utf-8")
        self.assertIn('proxyRelease(name, null, 21600, request)', text)

    def test_installer_entrypoints_use_release_proxy(self):
        text = (ROOT / "cloudflare" / "worker.js").read_text(encoding="utf-8")
        self.assertIn('proxyRelease("install.sh"', text)
        self.assertIn('proxyRelease("install.ps1"', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
