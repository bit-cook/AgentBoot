#!/usr/bin/env python3
"""Ensure every independently distributed surface advertises one release version."""

from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="ascii").strip()
TAG = "v" + VERSION
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402
import menu  # noqa: E402


class VersionConsistencyTests(unittest.TestCase):
    def test_python_core_uses_version_file(self):
        self.assertEqual(agent.VERSION, VERSION)
        self.assertEqual(menu.VERSION, VERSION)

    def test_distributed_installers_pin_current_tag(self):
        shell = (ROOT / "install.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8-sig")
        worker = (ROOT / "cloudflare/worker.js").read_text(encoding="utf-8")
        self.assertIn('TAG="%s"' % TAG, shell)
        self.assertIn("$Tag       = '%s'" % TAG, powershell)
        self.assertIn('const TAG = "%s"' % TAG, worker)

    def test_pages_mirror_copies_match_canonical_sources(self):
        """Pages 镜像上的安装器副本必须与权威源同版本。

        曾漂移：pages/install.ps1 停在 v1.5.1、pages/VERSION 停在 1.7.3
        （v1.7.5 实测发现）——这些副本由发布流水线构建时拷贝，仓库里却
        没人同步，严格测试也不查它们。gh-pages 服务的就是这些文件，
        用户从 Pages 镜像下载到的安装器版本由仓库副本决定。
        """
        mirror_version = (ROOT / "pages" / "VERSION").read_text(encoding="ascii").strip()
        self.assertEqual(mirror_version, VERSION, "pages/VERSION 与 VERSION 不一致")
        mirror_ps1 = (ROOT / "pages" / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$Tag       = '%s'" % TAG, mirror_ps1,
                      "pages/install.ps1 与 scripts/install.ps1 不同版本")
        mirror_sh = (ROOT / "pages" / "install.sh").read_text(encoding="utf-8")
        self.assertIn('TAG="%s"' % TAG, mirror_sh,
                      "pages/install.sh 与 install.sh 不同版本")
        # 不只比版本号：副本必须与权威源逐字节一致。
        # v1.8.0 的教训——ps1 加了 Assert-NoTraversal，版本号同步了但内容
        # 没同步，Pages 镜像的 Windows 用户拿到缺越界检查的旧安装器，
        # 纯版本号守卫看不见。CRLF 由发布流水线负责，仓库副本保持 LF。
        self.assertEqual(mirror_ps1,
                         (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8-sig"),
                         "pages/install.ps1 与 scripts/install.ps1 内容不一致——"
                         "Pages 镜像用户拿到的不是当前安装器")
        self.assertEqual(mirror_sh,
                         (ROOT / "install.sh").read_text(encoding="utf-8"),
                         "pages/install.sh 与 install.sh 内容不一致——"
                         "Pages 镜像用户拿到的不是当前安装器")

    def test_pages_mirror_content_drift_is_caught(self):
        """变异验证：副本内容被改旧（版本号不动）时守卫必须失败。

        v1.8.0 真实发生过——scripts/install.ps1 新增 Assert-NoTraversal
        后 pages/install.ps1 没同步，版本号一致所以纯字符串守卫放过，
        Pages 镜像的 Windows 用户拿到无越界检查的安装器。
        """
        import unittest as _ut
        mirror = (ROOT / "pages" / "install.ps1")
        original = mirror.read_text(encoding="utf-8-sig")
        try:
            drifted = original.replace("function Assert-NoTraversal", "function Assert-NoTraversalUnused")
            self.assertNotEqual(original, drifted, "v1.8.1 的 ps1 应含 Assert-NoTraversal")
            mirror.write_text(drifted, encoding="utf-8-sig", newline="")
            with self.assertRaises(AssertionError):
                self.test_pages_mirror_copies_match_canonical_sources()
        finally:
            mirror.write_text(original, encoding="utf-8-sig", newline="")

    def test_web_and_guides_show_current_version(self):
        for relative in ("pages/index.html", "pages/en/index.html", "cloudflare/worker.js",
                         "docs/zh/安装指南.md", "docs/en/install-guide.md", "安装指南.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(TAG, text, relative)

    def test_pages_have_no_stale_version_strings(self):
        """页面里每一个版本样字符串都必须是当前版本。

        曾因只断言「包含当前版本」而漏掉 en/index.html hero 徽章残留的
        v1.4.3（英文用户看到旧版本号，中文页却是新的）。
        """
        pattern = re.compile(r"[vV]?\d+\.\d+\.\d+")
        for relative in ("pages/index.html", "pages/en/index.html", "pages/404.html"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            stale = [m for m in pattern.findall(text)
                     if m.lstrip("vV") != VERSION]
            self.assertEqual(stale, [], "%s 残留旧版本串: %s" % (relative, stale))

    def test_web_asset_cache_busters_match_version(self):
        for relative in ("pages/index.html", "pages/en/index.html"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("site.css?v=%s" % VERSION, text, relative)
            self.assertIn("site.js?v=%s" % VERSION, text, relative)

    def test_online_builder_names_current_version(self):
        text = (ROOT / "scripts/build-online.py").read_text(encoding="utf-8")
        self.assertIn('ROOT / "VERSION"', text)
        self.assertNotIn('TAG = "v1.0.0"', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
