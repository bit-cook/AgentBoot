#!/usr/bin/env python3
"""Regression tests for high-impact v1.0.0 defects found during uninstall review."""

from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402
import i18n  # noqa: E402
import menu  # noqa: E402


class PickAgentFeedbackTests(unittest.TestCase):
    """多选界面输入无法识别的编号/ID 时必须给出反馈，不能静默跳回主菜单。"""

    def setUp(self):
        # 断言的是中文提示文案：把全局语言钉回默认，屏蔽其他用例的语言泄漏
        i18n.set_lang("zh")

    def _agents(self):
        return [{"id": "codex", "name": "Codex", "method": "npm", "offline": True,
                 "desc": "x"},
                {"id": "coco", "name": "CoCo", "method": "npm", "offline": True,
                 "desc": "y"}]

    def test_out_of_range_number_gives_feedback(self):
        import io
        import contextlib
        buf = io.StringIO()
        with mock.patch("builtins.input", return_value="99"):
            with contextlib.redirect_stdout(buf):
                result = menu.pick_agents(self._agents(), "t")
        self.assertEqual(result, [])
        self.assertIn("未识别", buf.getvalue())

    def test_garbage_token_gives_feedback(self):
        import io
        import contextlib
        buf = io.StringIO()
        with mock.patch("builtins.input", return_value="hello world"):
            with contextlib.redirect_stdout(buf):
                result = menu.pick_agents(self._agents(), "t")
        self.assertEqual(result, [])
        self.assertIn("未识别", buf.getvalue())

    def test_valid_mixed_input_still_works(self):
        with mock.patch("builtins.input", return_value="2 codex"):
            self.assertEqual(menu.pick_agents(self._agents(), "t"), ["codex", "coco"])

    def test_blank_and_zero_stay_silent(self):
        import io
        import contextlib
        for answer in ("", "0"):
            buf = io.StringIO()
            with mock.patch("builtins.input", return_value=answer):
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(menu.pick_agents(self._agents(), "t"), [])
            self.assertNotIn("未识别", buf.getvalue())


class HomePathGuardTests(unittest.TestCase):
    """AGENTBOOT_HOME 指向已存在的文件时必须给明确错误，而不是裸 traceback。"""

    def test_file_as_home_exits_cleanly(self):
        import tempfile
        with tempfile.NamedTemporaryFile() as fh:
            with mock.patch.object(agent, "AB_HOME", fh.name):
                with self.assertRaises(SystemExit) as ctx:
                    agent.ensure_home()
        self.assertIn("AGENTBOOT_HOME", str(ctx.exception))
        self.assertIn("文件", str(ctx.exception))

    def test_missing_home_is_created(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "sub", "home")
            with mock.patch.object(agent, "AB_HOME", target):
                agent.ensure_home()
            self.assertTrue(os.path.isdir(target))


class ReplExitCommandTests(unittest.TestCase):
    """REPL 退出命令：斜杠形式之外，裸 exit/quit/q/退出 也必须退出。

    否则用户本能输入的 exit 会被当成任务发给模型（费 token 且困惑）。
    """

    def _drive(self, typed):
        calls = []

        def fake_loop(cfg, text, history=None, **kw):
            calls.append(text)
            return "", history or []

        cfg = {"active": "mock", "providers": {"mock": {
            "base_url": "http://127.0.0.1:1/v1", "api_key": "", "model": "m"}},
            "lang": "zh"}
        with mock.patch("builtins.input", side_effect=list(typed) + [EOFError]):
            with mock.patch.object(agent, "agent_loop", fake_loop):
                agent.repl(cfg)  # 正常返回即退出成功
        self.assertEqual(calls, [], "这些命令不应发给模型: %s" % calls)

    def test_slash_forms_exit(self):
        for word in ("/exit", "/quit", "/退出", "/q"):
            self._drive([word])

    def test_bare_words_exit(self):
        for word in ("exit", "quit", "q", "退出"):
            self._drive([word])

    def test_eof_exits(self):
        self._drive([])


class HighImpactRegressionTests(unittest.TestCase):
    def test_model_request_uses_compact_json(self):
        source = (ROOT / "core" / "agent.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count('separators=(",", ":")'), 2)

    def test_installed_ab_wrappers_forward_subcommands(self):
        files = ("install.sh", "scripts/install-offline.sh", "scripts/install.ps1",
                 "scripts/install-offline.ps1")
        for relative in files:
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertNotRegex(text, r"agent\.py['\"]?\s+chat\s")
            self.assertIn("launch.py", text, relative)

    def test_cached_dispatcher_forwards_targets_and_arguments(self):
        source = (ROOT / "core" / "launch.py").read_text(encoding="utf-8")
        self.assertIn('sys.argv = [sys.argv[0]] + sys.argv[2:]', source)
        self.assertIn('if target == "agent"', source)
        self.assertIn('elif target == "menu"', source)

    def test_windows_platform_id_matches_payload_layout(self):
        with mock.patch.object(menu.platform, "system", return_value="Windows"), \
                mock.patch.object(menu.platform, "machine", return_value="AMD64"):
            self.assertEqual(menu.plat_id(), "win-x64")

    def test_linux_kb_indexes_every_markdown_section(self):
        expected = 0
        for path in Path(agent.KB_DIR).glob("*.md"):
            expected += sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                            if line.startswith("## "))
        with tempfile.TemporaryDirectory() as tmp:
            original = agent._KB_CACHE
            try:
                agent._KB_CACHE = None
                with mock.patch.object(agent, "AB_HOME", tmp), \
                        mock.patch.object(agent, "KB_DIR", agent._KB_SHIPPED_DIR):
                    sections = agent._kb_sections()
            finally:
                agent._KB_CACHE = original
        self.assertGreaterEqual(expected, 60)
        self.assertEqual(len(sections), expected)

    def test_npm_install_is_scoped_to_agentboot_prefix(self):
        completed = mock.Mock(returncode=0)
        completed.wait.return_value = 0
        completed.pid = 4242
        with mock.patch.object(menu, "npm_cmd", return_value="npm"), \
                mock.patch.object(menu.shutil, "which", return_value="npm"), \
                mock.patch.object(menu, "cn_mode", return_value=False), \
                mock.patch.object(menu, "NPM_PREFIX", "/managed/agentboot/npm-prefix"), \
                mock.patch.object(menu.os, "makedirs"), \
                mock.patch.object(menu.subprocess, "Popen", return_value=completed) as run:
            self.assertTrue(menu.npm_install("@openai/codex@0.90.0"))
        command = run.call_args.args[0]
        self.assertIn("--prefix", command)
        self.assertEqual(command[command.index("--prefix") + 1], "/managed/agentboot/npm-prefix")
        for option in ("--no-audit", "--no-fund", "--prefer-offline", "--progress=false", "--loglevel=error"):
            self.assertIn(option, command)
        for flag in ("--fetch-timeout=120000", "--fetch-retries=4"):
            self.assertIn(flag, command)
        self.assertEqual(run.call_count, 1)  # 成功时不重试

    def test_ttfb_does_not_wait_for_remaining_response_body(self):
        class Response:
            def __init__(self):
                self.lines = iter([b"data: {\"choices\":[]}\n"])
                self.drained = False

            def readline(self):
                return next(self.lines, b"")

            def read(self):
                self.drained = True
                return b""

        connection = mock.Mock()
        response = Response()
        connection.getresponse.return_value = response
        cfg = {"active": "agnes", "providers": {}}
        with mock.patch.object(agent, "_connect", return_value=connection), \
                mock.patch.object(agent, "_drop_pool") as drop:
            latency = agent._ttfb(cfg)
        self.assertIsInstance(latency, float)
        self.assertTrue(response.drained)
        drop.assert_not_called()

    def test_ab_run_prints_final_answer_in_interactive_mode(self):
        with mock.patch.object(agent, "load_config", return_value=agent.default_config()), \
                mock.patch.object(agent, "_is_interactive", return_value=True), \
                mock.patch.object(agent, "agent_loop", return_value=("answer", [])), \
                mock.patch.object(sys, "argv", ["agent.py", "run", "task"]), \
                mock.patch("builtins.print") as printed:
            agent.main()
        self.assertTrue(any(call.args == ("answer",) for call in printed.call_args_list))

    def test_provider_name_selects_requested_provider(self):
        cfg = {"active": "first", "providers": {"first": {}, "second": {}}}
        with mock.patch.object(agent, "chat", return_value=("ok", [])) as chat:
            ok, _message = agent.test_provider(cfg, name="second")
        self.assertTrue(ok)
        self.assertEqual(chat.call_args.args[0]["active"], "second")


if __name__ == "__main__":
    unittest.main(verbosity=2)
