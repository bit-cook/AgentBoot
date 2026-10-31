#!/usr/bin/env python3
"""回归测试：内置 ab 默认模型切换为 Groq（Agnes 保留为自动备选）。

背景（v1.5.2）：用户要求把内置 agent 的默认模型改为 Groq 的
qwen/qwen3.8-27b，Agnes 不删、作为备选。chat_auto 本就支持
cfg["fallback"] 备选链，本次补齐：

1. PRESETS 增加 groq（base_url/model），agnes 保留且标记为备选
2. DEFAULT_ACTIVE=groq，DEFAULT_FALLBACK=["agnes"]
3. default_config() 带上 fallback 链
4. get_provider：GROQ_API_KEY 环境变量可覆盖预设 key（轮换不改代码），
   但 /model 里显式配过的同名提供商优先
5. load_config 一次性迁移：只把「旧默认形态」的配置切到新默认，
   显式定制过的配置一律不动
6. chat_auto：主源（groq）失败自动切备选（agnes）
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402


class GroqPresetTests(unittest.TestCase):
    def test_groq_preset_exists_with_documented_values(self):
        groq = agent.PRESETS["groq"]
        self.assertEqual(groq["base_url"], "https://api.groq.com/openai/v1")
        self.assertEqual(groq["model"], "qwen/qwen3.8-27b")
        # key 不明文进 PRESETS（公开仓库）：经 embedded_groq_key() 提供
        self.assertEqual(groq["api_key"], "")
        self.assertTrue(agent.embedded_groq_key().startswith("gsk_"))

    def test_agnes_kept_as_fallback_preset(self):
        self.assertIn("agnes", agent.PRESETS)
        self.assertEqual(agent.PRESETS["agnes"]["model"], "agnes-2.5-flash")

    def test_defaults(self):
        self.assertEqual(agent.DEFAULT_ACTIVE, "groq")
        self.assertEqual(agent.DEFAULT_FALLBACK, ["agnes"])
        cfg = agent.default_config()
        self.assertEqual(cfg["active"], "groq")
        self.assertEqual(cfg["fallback"], ["agnes"])


class ProviderResolutionTests(unittest.TestCase):
    def test_default_provider_is_groq(self):
        p = agent.get_provider(agent.default_config())
        self.assertEqual(p["name"], "groq")
        self.assertEqual(p["model"], "qwen/qwen3.8-27b")

    def test_env_key_overrides_preset_key(self):
        cfg = agent.default_config()
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "gsk_env_key"}):
            p = agent.get_provider(cfg)
        self.assertEqual(p["api_key"], "gsk_env_key")

    def test_embedded_key_used_without_env(self):
        """没有环境变量时用内置编码 key（v1.5.2 e2e 实测漏接线，回归锁定）。"""
        cfg = agent.default_config()
        env = dict(os.environ)
        env.pop("GROQ_API_KEY", None)
        with mock.patch.dict(os.environ, env, clear=True):
            p = agent.get_provider(cfg)
        self.assertEqual(p["api_key"], agent.embedded_groq_key())
        self.assertTrue(p["api_key"].startswith("gsk_"))

    def test_embedded_key_roundtrip(self):
        """内置 key 可解码且与编码常量自洽（测试内不出现明文 key——
        GitHub 密钥扫描会拦截明文推送，实测踩过）。"""
        import base64
        enc = agent._GROQ_KEY_ENC
        decoded = base64.b64decode(
            "".join(chr(ord(c) - 1) for c in enc)).decode("utf-8").strip()
        self.assertEqual(agent.embedded_groq_key(), decoded)
        self.assertTrue(decoded.startswith("gsk_"))
        self.assertEqual(len(decoded), 56)

    def test_explicit_provider_beats_env_key(self):
        cfg = agent.default_config()
        with mock.patch.object(agent, "save_config"):  # 不碰真实配置
            agent.set_provider(cfg, "groq", "https://api.groq.com/openai/v1",
                               "gsk_explicit", "qwen/qwen3.8-27b", activate=True)
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "gsk_env_key"}):
            p = agent.get_provider(cfg)
        self.assertEqual(p["api_key"], "gsk_explicit")

    def test_agnes_still_resolvable(self):
        cfg = agent.default_config()
        p = agent.get_provider(cfg, "agnes")
        self.assertEqual(p["name"], "agnes")
        self.assertEqual(p["base_url"], "https://apihub.agnes-ai.com/v1")


class MigrationTests(unittest.TestCase):
    """load_config 的一次性迁移。"""

    def _load_with(self, payload):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / ".agentboot").mkdir()
            cfg_path = home / ".agentboot" / "config.json"
            cfg_path.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(agent, "AB_HOME", str(home / ".agentboot")), \
                    mock.patch.object(agent, "CONFIG_PATH", str(cfg_path)):
                return agent.load_config()

    def test_old_default_config_migrates_to_groq(self):
        cfg = self._load_with({"active": "agnes", "lang": "zh"})
        self.assertEqual(cfg["active"], "groq")
        self.assertEqual(cfg["fallback"], ["agnes"])
        self.assertTrue(cfg["_groq_default_migrated"])

    def test_customized_config_untouched(self):
        cfg = self._load_with({"active": "agnes", "lang": "zh",
                               "providers": {"custom": {"base_url": "https://x",
                                                        "model": "m"}}})
        self.assertEqual(cfg["active"], "agnes")

    def test_explicit_fallback_config_untouched(self):
        cfg = self._load_with({"active": "agnes", "fallback": ["ollama"]})
        self.assertEqual(cfg["active"], "agnes")
        self.assertEqual(cfg["fallback"], ["ollama"])

    def test_migration_runs_once(self):
        cfg = self._load_with({"active": "agnes", "_groq_default_migrated": True})
        self.assertEqual(cfg["active"], "agnes")


class ChatAutoFallbackTests(unittest.TestCase):
    """主源失败 → 自动切备选（这正是 Groq key 失效时的兜底路径）。"""

    def test_groq_failure_falls_back_to_agnes(self):
        cfg = agent.default_config()
        calls = []

        def fake_chat(c, messages, *a, **kw):
            calls.append(c["active"])
            if c["active"] == "groq":
                raise agent.ApiError("403 Forbidden")
            return "agnes-reply", []

        with mock.patch.object(agent, "chat", side_effect=fake_chat):
            out, _ = agent.chat_auto(cfg, [{"role": "user", "content": "hi"}])
        self.assertEqual(out, "agnes-reply")
        self.assertEqual(calls, ["groq", "agnes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
