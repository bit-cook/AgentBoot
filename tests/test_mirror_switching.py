#!/usr/bin/env python3
"""Multi-mirror switching: npm registries, node mirrors, GitHub accelerators, persistence."""

import io
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class MirrorCatalogTests(unittest.TestCase):
    def test_npm_mirrors_valid_and_unique(self):
        urls = [url for _, url in menu.NPM_MIRRORS]
        self.assertTrue(all(url.startswith("https://") for url in urls))
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(menu.NPM_MIRROR, urls[0])

    def test_node_mirrors_valid_and_unique(self):
        urls = [url for _, url in menu.NODE_MIRRORS]
        self.assertTrue(all(url.startswith("https://") for url in urls))
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(menu.NODE_MIRROR_CN, urls[0])
        self.assertNotIn(menu.NODE_MIRROR_GLOBAL, urls)

    def test_gh_proxies_have_trailing_slash_and_unique(self):
        urls = [url for _, url in menu.GH_PROXIES]
        self.assertTrue(all(url.startswith("https://") and url.endswith("/") for url in urls))
        self.assertEqual(len(urls), len(set(urls)))
        self.assertGreaterEqual(len(urls), 3, "至少提供 3 个 GitHub 加速源")

    def test_cn_mirror_hosts_differ_from_official(self):
        hosts = {urlsplit(u).hostname for _, u in menu.NPM_MIRRORS}
        self.assertNotIn("registry.npmjs.org", hosts)


class NpmRegistrySelectionTests(unittest.TestCase):
    def test_fixed_choice_wins(self):
        with mock.patch.object(menu, "load_env_json", return_value={"npm_registry": "https://mirror.example/npm/"}):
            self.assertEqual(menu.npm_registry(True), "https://mirror.example/npm/")
            self.assertEqual(menu.npm_registry(False), "https://mirror.example/npm/")

    def test_auto_cn_and_global(self):
        with mock.patch.object(menu, "load_env_json", return_value={}), \
             mock.patch.object(menu, "cn_mode", return_value=True):
            self.assertEqual(menu.npm_registry(), menu.NPM_MIRROR)
        with mock.patch.object(menu, "load_env_json", return_value={}), \
             mock.patch.object(menu, "cn_mode", return_value=False):
            self.assertEqual(menu.npm_registry(), menu.NPM_OFFICIAL)

    def test_set_npm_mirror_persists_and_clears(self):
        saved = {}

        def fake_save(data):
            saved.clear()
            saved.update(data)

        with mock.patch.object(menu, "load_env_json", return_value={}), \
                mock.patch.object(menu, "save_env_json", side_effect=fake_save), \
                mock.patch.object(menu, "npm_cmd", return_value=None):
            menu.set_npm_mirror("https://mirrors.cloud.tencent.com/npm/")
            self.assertEqual(saved.get("npm_registry"), "https://mirrors.cloud.tencent.com/npm/")
            menu.set_npm_mirror(None)
            self.assertNotIn("npm_registry", saved)


class GhMirrorSelectionTests(unittest.TestCase):
    def setUp(self):
        os_patcher = mock.patch.dict("os.environ", {}, clear=False)
        os_patcher.start()
        self.addCleanup(os_patcher.stop)
        import os as _os
        _os.environ.pop("AGENTBOOT_GH_PROXY", None)

    def test_off_returns_empty(self):
        with mock.patch.object(menu, "load_env_json", return_value={"gh_proxy": "off"}), \
                mock.patch.object(menu, "cn_mode", return_value=True):
            self.assertEqual(menu.gh_mirrors(), [])

    def test_global_network_direct_when_auto(self):
        with mock.patch.object(menu, "load_env_json", return_value={}), \
                mock.patch.object(menu, "cn_mode", return_value=False):
            self.assertEqual(menu.gh_mirrors(), [])

    def test_explicit_choice_first_with_fallbacks(self):
        chosen = "https://ghfast.top/"
        with mock.patch.object(menu, "load_env_json", return_value={"gh_proxy": chosen}), \
                mock.patch.object(menu, "cn_mode", return_value=False):
            mirrors = menu.gh_mirrors()
        self.assertEqual(mirrors[0], chosen)
        self.assertEqual(len(mirrors), len(menu.GH_PROXIES))
        self.assertIn("https://gh-proxy.com/", mirrors)

    def test_env_var_overrides_env_json(self):
        import os as _os
        _os.environ["AGENTBOOT_GH_PROXY"] = "https://custom.example/"
        with mock.patch.object(menu, "load_env_json", return_value={"gh_proxy": "off"}), \
                mock.patch.object(menu, "cn_mode", return_value=False):
            mirrors = menu.gh_mirrors()
        self.assertEqual(mirrors[0], "https://custom.example/")

    def test_auto_orders_alive_first(self):
        prefixes = [p for _, p in menu.GH_PROXIES]
        probes = {urlsplit(p).hostname: (i == 1) for i, p in enumerate(prefixes)}
        with mock.patch.object(menu, "load_env_json", return_value={}), \
                mock.patch.object(menu, "cn_mode", return_value=True), \
                mock.patch.object(menu.agent, "probe_hosts", return_value=probes):
            mirrors = menu.gh_mirrors()
        self.assertEqual(mirrors[0], prefixes[1])
        self.assertEqual(len(mirrors), len(prefixes), "探测不可达的源保留为兜底")

    def test_auto_all_dead_keeps_original_order(self):
        prefixes = [p for _, p in menu.GH_PROXIES]
        probes = {urlsplit(p).hostname: False for p in prefixes}
        with mock.patch.object(menu, "load_env_json", return_value={}), \
                mock.patch.object(menu, "cn_mode", return_value=True), \
                mock.patch.object(menu.agent, "probe_hosts", return_value=probes):
            self.assertEqual(menu.gh_mirrors(), prefixes)

    def test_set_gh_proxy_modes(self):
        saved = {}
        with mock.patch.object(menu, "load_env_json", return_value={}), \
                mock.patch.object(menu, "save_env_json", side_effect=lambda d: saved.update(d)):
            menu.set_gh_proxy("auto")
            self.assertNotIn("gh_proxy", saved)
            menu.set_gh_proxy("off")
            self.assertEqual(saved.get("gh_proxy"), "off")
            menu.set_gh_proxy("https://gh-proxy.com")
            self.assertEqual(saved.get("gh_proxy"), "https://gh-proxy.com/")
            menu.set_gh_proxy("not-a-url")
            self.assertNotEqual(saved.get("gh_proxy"), "not-a-url")


class InstallWiringTests(unittest.TestCase):
    def test_install_via_script_uses_selected_mirrors(self):
        tried = []

        def fake_download(url, suffix):
            tried.append(url)
            raise ValueError("stop")

        url = "https://github.com/bit-cook/coco/releases/download/installer-v0.1.1.1/agnes.key"
        with mock.patch.object(menu, "gh_mirrors",
                               return_value=["https://gh-proxy.com/", "https://ghproxy.net/"]), \
                mock.patch.object(menu, "_script_fallback_urls", return_value=[]), \
                mock.patch.object(menu, "_download_script", side_effect=fake_download), \
                mock.patch.object(menu, "child_env", return_value={}):
            menu.install_via_script({"script": url})
        self.assertEqual(tried[0], url)
        self.assertEqual(tried[1], "https://gh-proxy.com/" + url)
        self.assertEqual(tried[2], "https://ghproxy.net/" + url)

    def test_seed_uv_uses_selected_mirrors(self):
        tried = []

        def fake_download(urls, dest):
            tried.extend(urls)
            return False

        meta = ("v1.2.3", ("uv-x86_64-linux.tar.gz", "uv/uv"), "a" * 64)
        with mock.patch.object(menu, "_hermes_uv_meta", return_value=meta), \
                mock.patch.object(menu, "gh_mirrors", return_value=["https://p1/"]), \
                mock.patch.object(menu, "_download_mirror", side_effect=fake_download):
            menu._seed_uv(r"C:\fake\pkg")
        self.assertIn("https://github.com/astral-sh/uv/releases/download/v1.2.3/uv-x86_64-linux.tar.gz", tried[0])
        self.assertIn("https://p1/", tried[1])


class MirrorStatusSmokeTests(unittest.TestCase):
    def test_mirror_status_lists_all_sources(self):
        probes = {"registry.npmjs.org": True}
        probes.update({urlsplit(u).hostname: True for _, u in menu.NPM_MIRRORS})
        probes.update({urlsplit(p).hostname: True for _, p in menu.GH_PROXIES})
        captured = io.StringIO()
        with mock.patch.object(menu, "cn_mode", return_value=True), \
                mock.patch.object(menu, "npm_current_registry", return_value="https://registry.npmmirror.com"), \
                mock.patch.object(menu, "load_env_json", return_value={}), \
                mock.patch.object(menu.agent, "probe_hosts", return_value=probes), \
                mock.patch.object(menu, "npm_cmd", return_value=None), \
                mock.patch("sys.stdout", captured):
            menu.mirror_status()
        out = captured.getvalue()
        for label, _ in menu.NPM_MIRRORS:
            self.assertIn(label, out)
        for label, _ in menu.GH_PROXIES:
            self.assertIn(label, out)
        self.assertIn(menu.NPM_OFFICIAL, out)
        self.assertIn("GitHub", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
