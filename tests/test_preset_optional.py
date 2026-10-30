#!/usr/bin/env python3
"""回归测试：模型预置从「安装即写」改为「可选，默认原版」。

背景：v1.4.4 之前安装任何 Agent 都会预置 Agnes 免费模型（写
~/.codex/config.toml、opencode.json、shell shim 注入环境变量等）。
用户明确要求：安装的 Agent 保持原版，预置改为可选功能、默认关闭。

锁定的行为：
1. 默认关（env.json 无键、无环境变量）——原版安装
2. 环境变量 AGENTBOOT_PRESET_MODEL 可一次性覆盖
3. set_preset_model 持久化 / 关闭即删键（回到默认）
4. --preset / --no-preset 解析（含冲突报错）
5. install_online / offline_install 的门控：默认不调用 wire_agnes
6. CoCo 离线安装：默认不写 auth.json / settings.json
"""

import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "core"))

import menu  # noqa: E402


class PresetSettingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name
        self._env_patch = mock.patch.dict(os.environ)
        self._env_patch.start()
        os.environ.pop("AGENTBOOT_PRESET_MODEL", None)
        self._env_json = mock.patch.object(menu, "ENV_JSON",
                                           os.path.join(self.home, "env.json"))
        self._env_json.start()
        menu._ENV_JSON_CACHE["data"] = None
        menu._ENV_JSON_CACHE["mtime"] = None

    def tearDown(self):
        self._env_json.stop()
        self._env_patch.stop()
        menu._ENV_JSON_CACHE["data"] = None
        menu._ENV_JSON_CACHE["mtime"] = None
        self._tmp.cleanup()

    def test_default_is_off(self):
        self.assertFalse(menu.preset_model_enabled())

    def test_set_on_persists_and_off_removes_key(self):
        menu.set_preset_model(True)
        self.assertTrue(menu.preset_model_enabled())
        data = json.loads(Path(self.home, "env.json").read_text(encoding="utf-8"))
        self.assertTrue(data.get("preset_agent_model"))
        menu.set_preset_model(False)
        self.assertFalse(menu.preset_model_enabled())
        data = json.loads(Path(self.home, "env.json").read_text(encoding="utf-8"))
        self.assertNotIn("preset_agent_model", data)

    def test_env_var_overrides_persisted_setting(self):
        menu.set_preset_model(True)
        os.environ["AGENTBOOT_PRESET_MODEL"] = "0"
        self.assertFalse(menu.preset_model_enabled())
        os.environ["AGENTBOOT_PRESET_MODEL"] = "1"
        self.assertTrue(menu.preset_model_enabled())

    def test_resolve_preset_none_uses_setting(self):
        self.assertIs(menu._resolve_preset(None), False)
        os.environ["AGENTBOOT_PRESET_MODEL"] = "1"
        self.assertIs(menu._resolve_preset(None), True)
        self.assertIs(menu._resolve_preset(False), False)
        self.assertIs(menu._resolve_preset(True), True)


class PresetFlagParsingTests(unittest.TestCase):
    def test_flag_matrix(self):
        self.assertIsNone(menu._preset_flag(["codex"]))
        self.assertIs(menu._preset_flag(["--preset", "codex"]), True)
        self.assertIs(menu._preset_flag(["--no-preset", "codex"]), False)

    def test_conflicting_flags_exit_2(self):
        with self.assertRaises(SystemExit) as ctx:
            menu._preset_flag(["--preset", "--no-preset", "codex"])
        self.assertEqual(ctx.exception.code, 2)


class InstallGateTests(unittest.TestCase):
    """install_online / offline_install 必须按 preset 决定是否接线。"""

    AGENT = {"id": "codex", "name": "Codex", "vendor": "OpenAI", "bin": "codex",
             "method": "npm", "npm": "@openai/codex@0.90.0"}

    def test_online_default_does_not_wire_agnes(self):
        with mock.patch.object(menu, "load_registry", return_value=[self.AGENT]), \
                mock.patch.object(menu, "npm_install", return_value=True), \
                mock.patch.object(menu, "find_bin", return_value="/managed/bin/codex"), \
                mock.patch.object(menu, "wire_agnes") as wire, \
                mock.patch.object(menu, "record_install"), \
                mock.patch.object(menu, "preset_model_enabled", return_value=False):
            failures = menu.install_online(["codex"])
        self.assertEqual(failures, [])
        wire.assert_not_called()

    def test_online_preset_flag_wires_agnes(self):
        with mock.patch.object(menu, "load_registry", return_value=[self.AGENT]), \
                mock.patch.object(menu, "npm_install", return_value=True), \
                mock.patch.object(menu, "find_bin", return_value="/managed/bin/codex"), \
                mock.patch.object(menu, "write_online_shim", return_value=True), \
                mock.patch.object(menu, "wire_agnes",
                                  return_value=({"K": "v"}, [])) as wire, \
                mock.patch.object(menu, "record_install"), \
                mock.patch.object(menu, "preset_model_enabled", return_value=False):
            failures = menu.install_online(["codex"], preset=True)
        self.assertEqual(failures, [])
        wire.assert_called_once()

    def test_online_setting_on_wires_agnes(self):
        with mock.patch.object(menu, "load_registry", return_value=[self.AGENT]), \
                mock.patch.object(menu, "npm_install", return_value=True), \
                mock.patch.object(menu, "find_bin", return_value="/managed/bin/codex"), \
                mock.patch.object(menu, "write_online_shim", return_value=True), \
                mock.patch.object(menu, "wire_agnes",
                                  return_value=({"K": "v"}, [])) as wire, \
                mock.patch.object(menu, "record_install"), \
                mock.patch.object(menu, "preset_model_enabled", return_value=True):
            failures = menu.install_online(["codex"])
        self.assertEqual(failures, [])
        wire.assert_called_once()

    def test_offline_default_does_not_wire_agnes(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "payloads"
            source = payload / "agents" / "codex" / menu.plat_id() / "node_modules"
            source.mkdir(parents=True)
            with mock.patch.object(menu, "load_registry", return_value=[self.AGENT]), \
                    mock.patch.object(menu, "find_payload_dir", return_value=str(payload)), \
                    mock.patch.object(menu, "AGENTS_DIR", str(Path(tmp) / "agents")), \
                    mock.patch.object(menu, "AB_HOME", str(tmp)), \
                    mock.patch.object(menu, "node_ok", return_value=True), \
                    mock.patch.object(menu, "write_shim", return_value=True), \
                    mock.patch.object(menu, "wire_agnes") as wire, \
                    mock.patch.object(menu, "record_install"), \
                    mock.patch.object(menu, "preset_model_enabled", return_value=False):
                failures = menu.offline_install(["codex"], str(payload))
        self.assertEqual(failures, [])
        wire.assert_not_called()


class CocoPresetGateTests(unittest.TestCase):
    """CoCo 离线安装：原版不写 auth/settings；开启才写。"""

    def _payload(self, tmp):
        payload = Path(tmp) / "payload"
        payload.mkdir()
        tgz = payload / "coco-0.8.1.tgz"
        with tarfile.open(tgz, "w:gz") as t:
            data = b"fake coco package"
            info = tarfile.TarInfo("package/bin/coco")
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
        import hashlib
        digest = hashlib.sha256(tgz.read_bytes()).hexdigest()
        (payload / "coco-0.8.1.tgz.sha256").write_text(digest + "\n", encoding="ascii")
        (payload / "agnes.key").write_text("test-key\n", encoding="ascii")
        return str(payload)

    def _run(self, tmp, preset):
        agent = {"id": "coco", "name": "CoCo", "coco_version": "0.8.1"}
        with mock.patch.object(menu, "AB_HOME", str(Path(tmp) / "ab")), \
                mock.patch.object(menu.shutil, "which", return_value="/usr/bin/node"):
            return menu.coco_offline_install(agent, self._payload(tmp), preset=preset)

    def test_vanilla_install_writes_no_auth_or_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                self.assertTrue(self._run(tmp, preset=False))
            agent_dir = home / ".coco" / "agent"
            self.assertTrue((agent_dir / "models.json").exists())   # 厂商注册表骨架仍写
            self.assertFalse((agent_dir / "auth.json").exists())
            self.assertFalse((agent_dir / "settings.json").exists())

    def test_preset_install_writes_auth_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                self.assertTrue(self._run(tmp, preset=True))
            agent_dir = home / ".coco" / "agent"
            auth = json.loads((agent_dir / "auth.json").read_text(encoding="utf-8"))
            self.assertEqual(auth["agnes"]["key"], "test-key")
            settings = json.loads((agent_dir / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["defaultProvider"], "agnes")


if __name__ == "__main__":
    unittest.main(verbosity=2)
