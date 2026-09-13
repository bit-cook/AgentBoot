#!/usr/bin/env python3
"""Reasoning display, wait indicator, think-tag routing, fast tar extraction, script mirrors."""

import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402
import menu  # noqa: E402


class FakeResp:
    """Minimal SSE response: yields lines then EOF."""

    def __init__(self, lines):
        self._lines = [line.encode("utf-8") if isinstance(line, str) else line
                       for line in lines]

    def readline(self):
        return self._lines.pop(0) if self._lines else b""

    def read(self):
        return b""

    def getheader(self, name):
        return None


def sse(obj):
    import json
    return "data: %s" % json.dumps(obj, ensure_ascii=False)


def stream_response(deltas, done=True):
    lines = [sse({"choices": [d]}) for d in deltas]
    if done:
        lines.append("data: [DONE]")
    return FakeResp(lines)


class ThinkRouterTests(unittest.TestCase):
    def test_plain_content_passes_through(self):
        r = agent._ThinkRouter()
        text, reason = r.feed("你好 世界")
        self.assertEqual(text, "你好 世界")
        self.assertEqual(reason, "")
        self.assertEqual(r.flush(), ("", ""))

    def test_inline_think_block_routed(self):
        r = agent._ThinkRouter()
        text, reason = r.feed("before<think>hidden</think>after")
        self.assertEqual(text, "beforeafter")
        self.assertEqual(reason, "hidden")

    def test_think_tag_split_across_chunks(self):
        r = agent._ThinkRouter()
        a = r.feed("ok<th")
        b = r.feed("ink>abc</th")
        c, d = r.feed("ink>done")
        e, f = r.flush()
        self.assertEqual("".join([a[0], b[0], c, e]), "okdone")
        self.assertEqual("".join([a[1], b[1], d, f]), "abc")

    def test_unclosed_think_treated_as_reasoning(self):
        r = agent._ThinkRouter()
        text, reason = r.feed("answer<think>leaking")
        self.assertEqual(text, "answer")
        self.assertEqual(reason, "leaking")
        self.assertEqual(r.flush(), ("", ""))

    def test_trailing_partial_tag_flushed_as_content(self):
        r = agent._ThinkRouter()
        text, reason = r.feed("value <th")
        self.assertEqual(text, "value ")
        tail_text, tail_reason = r.flush()
        self.assertEqual(tail_text, "<th")
        self.assertEqual(tail_reason, "")

    def test_reasoning_accumulated(self):
        r = agent._ThinkRouter()
        r.feed("<think>part1 ")
        r.feed("part2</think>done")
        self.assertTrue(r.has_reasoning)
        self.assertEqual(r.reasoning_text, "part1 part2")


class ReadStreamReasoningTests(unittest.TestCase):
    def _run(self, resp, stream=True):
        content_out, reason_out = [], []
        result = agent._read_stream(
            resp,
            (lambda piece: content_out.append(piece)) if stream else None,
            None, "https", "example.test", 443,
            reasoning_cb=lambda piece: reason_out.append(piece))
        return result, "".join(content_out), "".join(reason_out)

    def test_reasoning_content_channel_forwarded(self):
        resp = stream_response([
            {"delta": {"reasoning_content": "思考 A"}},
            {"delta": {"reasoning_content": "思考 B"}},
            {"delta": {"content": "正文"}},
            {"delta": {}, "finish_reason": "stop"},
        ])
        (content, tcs), shown, reason = self._run(resp)
        self.assertEqual(content, "正文")
        self.assertEqual(tcs, [])
        self.assertEqual(shown, "正文")
        self.assertEqual(reason, "思考 A思考 B")

    def test_reasoning_alias_key_supported(self):
        resp = stream_response([
            {"delta": {"reasoning": "alt"}},
            {"delta": {"content": "ok"}},
            {"delta": {}, "finish_reason": "stop"},
        ])
        _, shown, reason = self._run(resp)
        self.assertEqual(shown, "ok")
        self.assertEqual(reason, "alt")

    def test_inline_think_content_routed_to_reasoning(self):
        resp = stream_response([
            {"delta": {"content": "before<think>secret</think>after"}},
            {"delta": {}, "finish_reason": "stop"},
        ])
        (content, _), shown, reason = self._run(resp)
        self.assertEqual(content, "beforeafter")
        self.assertEqual(shown, "beforeafter")
        self.assertEqual(reason, "secret")

    def test_reasoning_only_answer_falls_back_to_content(self):
        resp = stream_response([
            {"delta": {"reasoning_content": "完整答案"}},
            {"delta": {}, "finish_reason": "stop"},
        ])
        (content, tcs), _, reason = self._run(resp)
        self.assertEqual(content, "完整答案")
        self.assertEqual(tcs, [])
        self.assertEqual(reason, "完整答案")

    def test_tool_calls_unaffected_by_routing(self):
        resp = stream_response([
            {"delta": {"reasoning_content": "调用工具"}},
            {"delta": {"tool_calls": [
                {"index": 0, "id": "c1", "function": {"name": "run_cmd", "arguments": "{\"command\":"}}]}},
            {"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": "\"ls\"}"}}]}},
            {"delta": {}, "finish_reason": "tool_calls"},
        ])
        (content, tcs), _, reason = self._run(resp)
        self.assertEqual(content, "")
        self.assertEqual(len(tcs), 1)
        self.assertEqual(tcs[0]["function"]["name"], "run_cmd")
        self.assertEqual(tcs[0]["function"]["arguments"], '{"command":"ls"}')
        self.assertEqual(reason, "调用工具")

    def test_split_think_tag_stream(self):
        resp = stream_response([
            {"delta": {"content": "ok<th"}},
            {"delta": {"content": "ink>mid</th"}},
            {"delta": {"content": "ink>end"}},
            {"delta": {}, "finish_reason": "stop"},
        ])
        (content, _), shown, reason = self._run(resp)
        self.assertEqual(content, "okend")
        self.assertEqual(shown, "okend")
        self.assertEqual(reason, "mid")


class WaitIndicatorTests(unittest.TestCase):
    def test_stop_without_start_is_noop(self):
        ind = agent._WaitIndicator("thinking")
        ind.stop()   # 不应抛异常

    def test_start_stop_roundtrip(self):
        agent._enable_ansi()
        ind = agent._WaitIndicator("thinking")
        ind.start()
        ind.stop()
        ind.stop()   # 幂等

    def test_thread_does_not_leak(self):
        import threading
        before = threading.active_count()
        ind = agent._WaitIndicator("thinking")
        ind.start()
        ind.stop()
        self.assertLessEqual(threading.active_count(), before + 1)


class ExtractTgzFastTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("tar"):
            self.skipTest("system tar unavailable")

    def _make_tgz(self, tmp, members):
        archive = tmp / "pkg.tar.gz"
        with tarfile.open(archive, "w:gz") as t:
            for name, data in members:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                import io
                t.addfile(info, io.BytesIO(data))
        return archive

    def test_extracts_regular_files(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            archive = self._make_tgz(tmp, [("pkg/a.txt", b"hello"),
                                           ("pkg/sub/b.txt", b"world")])
            dest = tmp / "out"
            self.assertTrue(menu._extract_tgz_fast(str(archive), str(dest)))
            self.assertEqual((dest / "pkg" / "a.txt").read_bytes(), b"hello")
            self.assertEqual((dest / "pkg" / "sub" / "b.txt").read_bytes(), b"world")

    def test_rejects_traversal_members(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            archive = self._make_tgz(tmp, [("../evil.txt", b"nope")])
            dest = tmp / "out"
            self.assertFalse(menu._extract_tgz_fast(str(archive), str(dest)))
            self.assertFalse((tmp / "evil.txt").exists())

    def test_rejects_absolute_members(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            archive = self._make_tgz(tmp, [("/etc/passwd", b"nope")])
            self.assertFalse(menu._extract_tgz_fast(str(archive), str(tmp / "out")))


class ScriptFallbackUrlTests(unittest.TestCase):
    def test_project_pages_maps_to_gh_pages(self):
        # 项目页（如 AgentBoot / coco）由各项目仓库的 gh-pages 分支服务
        self.assertEqual(
            menu._script_fallback_urls("https://bit-cook.github.io/AgentBoot/install.sh"),
            ["https://cdn.jsdelivr.net/gh/bit-cook/AgentBoot@gh-pages/install.sh"])
        self.assertEqual(
            menu._script_fallback_urls("https://bit-cook.github.io/coco/install.sh"),
            ["https://cdn.jsdelivr.net/gh/bit-cook/coco@gh-pages/install.sh"])

    def test_non_pages_url_has_no_fallback(self):
        self.assertEqual(menu._script_fallback_urls("https://boot.ide.pub/install.sh"), [])
        self.assertEqual(menu._script_fallback_urls("https://github.com/x/y/install.sh"), [])
        self.assertEqual(menu._script_fallback_urls("https://bit-cook.github.io/"), [])

    def test_windows_ps1_script_also_maps(self):
        self.assertEqual(
            menu._script_fallback_urls("https://bit-cook.github.io/coco/install.ps1"),
            ["https://cdn.jsdelivr.net/gh/bit-cook/coco@gh-pages/install.ps1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
