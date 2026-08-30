#!/usr/bin/env python3
"""Keep duplicated user-facing release facts synchronized."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocumentationConsistencyTests(unittest.TestCase):
    def test_chinese_guides_share_release_critical_facts(self):
        guides = [(ROOT / "安装指南.md").read_text(encoding="utf-8"),
                  (ROOT / "docs/zh/安装指南.md").read_text(encoding="utf-8")]
        facts = ("v1.1.0", "win-x64-codex.zip", "linux-x64-codex.tar.gz",
                 "PAYLOAD_SHA256SUMS.txt", "agentboot uninstall", "--purge",
                 "Hermes", "目标平台")
        for fact in facts:
            for guide in guides:
                self.assertIn(fact, guide, fact)

    def test_web_surfaces_share_release_critical_facts(self):
        surfaces = [(ROOT / "pages/index.html").read_text(encoding="utf-8"),
                    (ROOT / "pages/en/index.html").read_text(encoding="utf-8"),
                    (ROOT / "cloudflare/worker.js").read_text(encoding="utf-8")]
        for fact in ("v1.1.0", "Codex", "uninstall"):
            for surface in surfaces:
                self.assertIn(fact, surface, fact)

    def test_web_surfaces_include_mobile_overflow_and_touch_fixes(self):
        surfaces = [(ROOT / "pages/index.html").read_text(encoding="utf-8"),
                    (ROOT / "pages/en/index.html").read_text(encoding="utf-8"),
                    (ROOT / "cloudflare/worker.js").read_text(encoding="utf-8")]
        for surface in surfaces:
            self.assertIn("table-scroll", surface)
            self.assertIn("minmax(min(100%,280px),1fr)", surface)
            self.assertIn("min-height:44px", surface)
            self.assertIn("aria-live", surface)


if __name__ == "__main__":
    unittest.main(verbosity=2)
