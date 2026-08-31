#!/usr/bin/env python3
"""Keep duplicated user-facing release facts synchronized."""

from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocumentationConsistencyTests(unittest.TestCase):
    def test_chinese_guides_share_release_critical_facts(self):
        guides = [(ROOT / "安装指南.md").read_text(encoding="utf-8"),
                  (ROOT / "docs/zh/安装指南.md").read_text(encoding="utf-8")]
        facts = ("v1.3.0", "win-x64-codex.zip", "linux-x64-codex.tar.gz",
                 "PAYLOAD_SHA256SUMS.txt", "agentboot uninstall", "--purge",
                 "Hermes", "目标平台")
        for fact in facts:
            for guide in guides:
                self.assertIn(fact, guide, fact)

    def test_web_surfaces_share_release_critical_facts(self):
        surfaces = [(ROOT / "pages/index.html").read_text(encoding="utf-8"),
                    (ROOT / "pages/en/index.html").read_text(encoding="utf-8"),
                    (ROOT / "cloudflare/web-assets.js").read_text(encoding="utf-8")]
        for fact in ("v1.3.0", "Codex", "OpenCode", "Cursor", "uninstall"):
            for surface in surfaces:
                self.assertIn(fact, surface, fact)

    def test_pages_include_accessible_responsive_interactions(self):
        pages = [(ROOT / "pages/index.html").read_text(encoding="utf-8"),
                 (ROOT / "pages/en/index.html").read_text(encoding="utf-8")]
        css = (ROOT / "pages/assets/site.css").read_text(encoding="utf-8")
        script = (ROOT / "pages/assets/site.js").read_text(encoding="utf-8")
        for surface in pages:
            self.assertIn("table-scroll", surface)
            self.assertIn("aria-live", surface)
            self.assertIn("<main", surface)
            self.assertIn("skip-link", surface)
            self.assertIn("data-copy", surface)
        self.assertIn("min-height: 44px", css)
        self.assertIn("@media (max-width: 480px)", css)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("navigator.clipboard", script)
        self.assertIn("document.execCommand", script)

    def test_pages_match_registry_agent_count_and_offline_claims(self):
        registry = json.loads((ROOT / "agents/registry.json").read_text(encoding="utf-8"))
        self.assertEqual(len(registry["agents"]), 15)
        for relative in ("pages/index.html", "pages/en/index.html"):
            page = (ROOT / relative).read_text(encoding="utf-8")
            self.assertEqual(page.count('<tr><td>'), 15, relative)
            self.assertIn("Cursor", page, relative)
            self.assertIn("OpenCode", page, relative)

    def test_worker_web_bundle_is_generated_and_cacheable(self):
        worker = (ROOT / "cloudflare/worker.js").read_text(encoding="utf-8")
        assets = (ROOT / "cloudflare/web-assets.js").read_text(encoding="utf-8")
        self.assertIn('import { WEB_ASSETS } from "./web-assets.js"', worker)
        self.assertIn("max-age=31536000, immutable", worker)
        self.assertIn('request.headers.get("If-None-Match")', worker)
        self.assertIn("status: 304", worker)
        self.assertIn('return webResponse(request, "/404.html", "no-store", 404)', worker)
        for fact in ("v1.3.0", "Codex", "OpenCode", "Cursor", "uninstall", "site.css", "site.js"):
            self.assertIn(fact, assets)


if __name__ == "__main__":
    unittest.main(verbosity=2)
