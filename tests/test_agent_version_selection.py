#!/usr/bin/env python3
"""回归测试：Agent 安装版本选择。

背景：v1.5.2 起所有 npm 类 Agent 默认安装最新版（注册表 spec 一律不带
版本号），用户可自选版本：
- CLI：agentboot install <id>@<版本> 或 --version <版本>
- 菜单：[2] 选完 Agent 后逐个询问（回车=最新）
- 查询：agentboot versions <id>

锁定内容：
1. 注册表不变量——任何 npm spec 不得带版本号（默认即最新）
2. resolve_npm_spec：默认透传 / 指定版本替换或追加
3. parse_agent_version_tokens：<id>@<version> 解析
4. agent_npm_versions：过滤预发布与平台分包、最新在前（mock 网络）
5. install_online 透传 versions（mock npm_install，断言 spec）
6. preset + codex 高版本警告
"""

import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class RegistryUnpinnedTests(unittest.TestCase):
    """默认安装最新版：npm spec 一律不带版本号。"""

    def test_no_npm_spec_is_version_pinned(self):
        registry = json.loads((ROOT / "agents/registry.json").read_text(encoding="utf-8"))
        pinned = [a["id"] for a in registry["agents"]
                  if a.get("npm") and "@" in a["npm"].split("/")[-1]]
        self.assertEqual(pinned, [], "这些 Agent 仍钉着版本: %s" % pinned)


class ResolveSpecTests(unittest.TestCase):
    AGENT = {"id": "opencode", "npm": "opencode-ai"}

    def test_none_returns_registry_default(self):
        self.assertEqual(menu.resolve_npm_spec(self.AGENT), "opencode-ai")

    def test_version_replaces_existing_pin(self):
        agent = {"id": "codex", "npm": "@openai/codex@0.90.0"}
        self.assertEqual(menu.resolve_npm_spec(agent, "0.166.0"),
                         "@openai/codex@0.166.0")

    def test_version_appended_to_unpinned(self):
        self.assertEqual(menu.resolve_npm_spec(self.AGENT, "1.19.5"),
                         "opencode-ai@1.19.5")

    def test_version_tolerates_v_prefix(self):
        self.assertEqual(menu.resolve_npm_spec(self.AGENT, "v1.19.5"),
                         "opencode-ai@1.19.5")

    def test_scoped_package_not_broken_by_at(self):
        agent = {"id": "codebuddy", "npm": "@tencent-ai/codebuddy-code"}
        self.assertEqual(menu.resolve_npm_spec(agent, "1.2.3"),
                         "@tencent-ai/codebuddy-code@1.2.3")


class TokenParsingTests(unittest.TestCase):
    def test_id_at_version_tokens(self):
        parsed = menu.parse_agent_version_tokens(
            ["opencode@1.19.5", "codex@0.90.0", "cline"])
        self.assertEqual(parsed, {"opencode": "1.19.5", "codex": "0.90.0"})

    def test_scoped_id_not_mistaken_for_version(self):
        parsed = menu.parse_agent_version_tokens(["@openai/codex"])
        self.assertEqual(parsed, {})


class VersionListTests(unittest.TestCase):
    AGENT = {"id": "opencode", "npm": "opencode-ai"}

    def _packument(self):
        return {
            "dist-tags": {"latest": "1.19.5"},
            "versions": {
                "1.19.5": {}, "1.19.4": {}, "1.19.3": {},
                "1.18.35": {}, "1.18.34": {},
                "2.0.0-beta.1": {},               # 预发布：过滤
                "0.0.0-dev-20261030": {},          # dev 构建：过滤
                "0.166.0-linux-x64": {},           # 平台分包：过滤
            },
        }

    def test_filters_prerelease_and_platform_variants_latest_first(self):
        class FakeResp:
            def __init__(self, payload):
                self._payload = payload

            def read(self):
                return _json.dumps(self._payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        import json as _json
        with mock.patch.object(menu, "cn_mode", return_value=False), \
                mock.patch("urllib.request.urlopen",
                           return_value=FakeResp(self._packument())):
            found = menu.agent_npm_versions(self.AGENT)
        self.assertEqual(found[:5], ["1.19.5", "1.19.4", "1.19.3",
                                     "1.18.35", "1.18.34"])
        self.assertNotIn("2.0.0-beta.1", found)
        self.assertNotIn("0.166.0-linux-x64", found)

    def test_network_failure_returns_empty(self):
        with mock.patch.object(menu, "cn_mode", return_value=False), \
                mock.patch("urllib.request.urlopen",
                           side_effect=urllib.error.URLError("boom")):
            self.assertEqual(menu.agent_npm_versions(self.AGENT), [])


class InstallThreadingTests(unittest.TestCase):
    AGENT = {"id": "opencode", "name": "OpenCode", "vendor": "opencode.ai",
             "bin": "opencode", "method": "npm", "npm": "opencode-ai"}

    def _run_install(self, **kwargs):
        with mock.patch.object(menu, "load_registry", return_value=[self.AGENT]), \
                mock.patch.object(menu, "npm_install", return_value=True) as npm, \
                mock.patch.object(menu, "find_bin", return_value="/managed/bin/opencode"), \
                mock.patch.object(menu, "resolve_shim_target",
                                  return_value="/managed/bin/opencode"), \
                mock.patch.object(menu, "write_online_shim", return_value=True), \
                mock.patch.object(menu, "wire_agnes", return_value=({}, [])), \
                mock.patch.object(menu, "record_install"):
            failures = menu.install_online(["opencode"], **kwargs)
        self.assertEqual(failures, [])
        return npm.call_args.args[0]

    def test_default_installs_latest_spec(self):
        spec = self._run_install()
        self.assertEqual(spec, "opencode-ai")

    def test_chosen_version_reaches_npm(self):
        spec = self._run_install(versions={"opencode": "1.19.4"})
        self.assertEqual(spec, "opencode-ai@1.19.4")

    def test_preset_codex_new_version_warns(self):
        codex = {"id": "codex", "name": "Codex", "bin": "codex",
                 "method": "npm", "npm": "@openai/codex"}
        with mock.patch.object(menu, "load_registry", return_value=[codex]), \
                mock.patch.object(menu, "npm_install", return_value=True), \
                mock.patch.object(menu, "find_bin", return_value="/managed/bin/codex"), \
                mock.patch.object(menu, "resolve_shim_target",
                                  return_value="/managed/bin/codex"), \
                mock.patch.object(menu, "write_online_shim", return_value=True), \
                mock.patch.object(menu, "wire_agnes", return_value=({}, [])), \
                mock.patch.object(menu, "record_install"):
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                menu.install_online(["codex"], preset=True,
                                    versions={"codex": "0.166.0"})
        self.assertIn("chat 协议", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
