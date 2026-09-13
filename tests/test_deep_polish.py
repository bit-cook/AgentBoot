#!/usr/bin/env python3
"""Deep-polish regressions: mirror-mode persistence, env.json cache, npm ticker, doctor."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402
import menu  # noqa: E402


class MirrorModePersistenceTests(unittest.TestCase):
    def setUp(self):
        import threading
        self._lock = threading.Lock()
        menu._ENV_JSON_CACHE.update(data=None, mtime=None)

    def tearDown(self):
        menu._ENV_JSON_CACHE.update(data=None, mtime=None)

    def test_set_mirror_mode_persists_and_clears(self):
        with tempfile.TemporaryDirectory() as td:
            old_home = menu.AB_HOME
            menu.AB_HOME = td
            try:
                menu.set_mirror_mode("cn")
                self.assertEqual(menu.load_env_json().get("mirror_mode"), "cn")
                menu.set_mirror_mode("off")
                self.assertEqual(menu.load_env_json().get("mirror_mode"), "off")
                menu.set_mirror_mode("auto")
                self.assertNotIn("mirror_mode", menu.load_env_json())
            finally:
                menu.AB_HOME = old_home

    def test_cn_mode_reads_persisted_preference(self):
        with tempfile.TemporaryDirectory() as td:
            old_home = menu.AB_HOME
            menu.AB_HOME = td
            try:
                menu.set_mirror_mode("cn")
                with mock.patch.object(menu, "can_tcp", return_value=True):
                    self.assertTrue(menu.cn_mode())   # 探测可达也尊重固定 cn
                menu.set_mirror_mode("off")
                with mock.patch.object(menu, "can_tcp", return_value=False):
                    self.assertFalse(menu.cn_mode())  # 探测不通也尊重固定 off
            finally:
                menu.AB_HOME = old_home

    def test_env_var_still_beats_persisted(self):
        with tempfile.TemporaryDirectory() as td:
            old_home = menu.AB_HOME
            menu.AB_HOME = td
            try:
                menu.set_mirror_mode("cn")
                with mock.patch.dict("os.environ", {"AGENTBOOT_MIRROR": "off"}), \
                        mock.patch.object(menu, "can_tcp", return_value=True):
                    self.assertFalse(menu.cn_mode())
            finally:
                menu.AB_HOME = old_home


class EnvJsonCacheTests(unittest.TestCase):
    def setUp(self):
        menu._ENV_JSON_CACHE.update(data=None, mtime=None)

    def tearDown(self):
        menu._ENV_JSON_CACHE.update(data=None, mtime=None)

    def test_cache_returns_copy_not_alias(self):
        with tempfile.TemporaryDirectory() as td:
            old_home = menu.AB_HOME
            menu.AB_HOME = td
            try:
                menu.set_proxy("http://127.0.0.1:7890")
                first = menu.load_env_json()
                first["npm_registry"] = "https://mutated.example/"   # 改返回值
                second = menu.load_env_json()
                self.assertNotIn("npm_registry", second, "返回必须是拷贝，避免脏写回")
                self.assertEqual(second.get("proxy"), "http://127.0.0.1:7890")
            finally:
                menu.AB_HOME = old_home

    def test_cache_invalidates_on_file_change(self):
        with tempfile.TemporaryDirectory() as td:
            old_home = menu.AB_HOME
            menu.AB_HOME = td
            try:
                menu.set_gh_proxy("off")
                self.assertEqual(menu.load_env_json().get("gh_proxy"), "off")
                data = menu.load_env_json()
                data.pop("gh_proxy")
                menu.save_env_json(data)
                self.assertNotIn("gh_proxy", menu.load_env_json())
            finally:
                menu.AB_HOME = old_home


class NpmTickerTests(unittest.TestCase):
    def test_ticker_does_not_break_result(self):
        process = mock.Mock()
        process.wait.return_value = 0
        process.pid = 99
        with mock.patch.object(menu.sys, "stdin", new=mock.Mock(isatty=lambda: False)), \
                mock.patch.object(menu.subprocess, "Popen", return_value=process):
            code, tail = menu._run_npm_process(["npm", "install", "-g", "x"], {})
        self.assertEqual(code, 0)
        self.assertEqual(tail, "")

    def test_timeout_path_still_reports(self):
        process = mock.Mock()
        process.pid = 100
        process.wait.side_effect = menu.subprocess.TimeoutExpired(cmd="npm", timeout=1)
        with mock.patch.object(menu.sys, "stdin", new=mock.Mock(isatty=lambda: False)), \
                mock.patch.object(menu.subprocess, "Popen", return_value=process), \
                mock.patch.object(menu.subprocess, "run"):
            code, _tail = menu._run_npm_process(["npm", "install", "-g", "x"], {})
        self.assertIsNone(code)


class DoctorPolishTests(unittest.TestCase):
    def test_agent_doctor_mentions_machine(self):
        captured = []

        def fake_print(*a, **kw):
            captured.append(" ".join(str(x) for x in a))

        cfg = {"providers": {"agnes": {"base_url": "https://apihub.agnes-ai.com/v1",
                                       "api_key": "k", "model": "agnes-2.5-flash", "name": "agnes"}},
               "active": "agnes"}
        with mock.patch.object(agent, "print", fake_print), \
                mock.patch.object(agent, "test_provider", return_value=(True, "")), \
                mock.patch.object(agent, "_kb_sections", return_value=[]), \
                mock.patch.object(agent, "probe_hosts", return_value={}):
            agent.doctor(cfg)
        out = "\n".join(captured)
        self.assertIn("本机", out)
        self.assertIn("核", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
