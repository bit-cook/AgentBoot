#!/usr/bin/env python3
"""Hardening regressions: parallel probes, KB index cache, model retry, search."""

import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402


class ProbeHostsTests(unittest.TestCase):
    def test_probe_hosts_reports_each_host(self):
        calls = []

        def fake_connect(address, timeout=None):
            calls.append(address[0])
            return mock.MagicMock()

        with mock.patch("socket.create_connection", side_effect=fake_connect):
            result = agent.probe_hosts(("a.example", "b.example", "a.example"))
        self.assertEqual(calls, ["a.example", "b.example"])  # 去重
        self.assertEqual(result, {"a.example": True, "b.example": True})

    def test_probe_hosts_runs_concurrently(self):
        barrier = threading.Barrier(3, timeout=5)

        def fake_connect(address, timeout=None):
            barrier.wait()  # 串行执行会在此超时
            return mock.MagicMock()

        with mock.patch("socket.create_connection", side_effect=fake_connect):
            result = agent.probe_hosts(("a.example", "b.example", "c.example"))
        self.assertTrue(all(result.values()))

    def test_probe_hosts_failure_is_false(self):
        with mock.patch("socket.create_connection",
                        side_effect=OSError("refused")):
            result = agent.probe_hosts(("down.example",))
        self.assertEqual(result, {"down.example": False})


class KnowledgeBaseCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.kb = Path(self.tmp.name) / "kb"
        self.kb.mkdir()
        (self.kb / "basics.md").write_text("## 查看端口\nss -tlnp 说明", encoding="utf-8")
        self.patches = [
            mock.patch.object(agent, "AB_HOME", str(self.home)),
            mock.patch.object(agent, "KB_DIR", str(self.kb)),
            mock.patch.object(agent, "_KB_CACHE", None),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    def test_cache_not_written_for_non_shipped_kb_dir(self):
        agent.linux_help("端口")
        self.assertFalse((self.home / "kb-index.cache").exists())

    def test_shipped_kb_cache_roundtrip_and_invalidation(self):
        with mock.patch.object(agent, "KB_DIR", agent._KB_SHIPPED_DIR), \
                mock.patch.object(agent, "_KB_CACHE", None), \
                mock.patch.object(agent, "_kb_manifest",
                                  return_value=[["basics.md", 24, 111]]), \
                mock.patch.object(agent, "_kb_build",
                                  return_value=[{"file": "basics.md", "title": "t",
                                                 "body": "b", "title_l": "t",
                                                 "body_l": "t\nb"}]):
            first = agent._kb_sections()
        self.assertTrue((self.home / "kb-index.cache").is_file())
        self.assertEqual(first[0]["title"], "t")

        # 指纹不变 → 命中缓存，不再重建
        with mock.patch.object(agent, "KB_DIR", agent._KB_SHIPPED_DIR), \
                mock.patch.object(agent, "_KB_CACHE", None), \
                mock.patch.object(agent, "_kb_manifest",
                                  return_value=[["basics.md", 24, 111]]), \
                mock.patch.object(agent, "_kb_build") as build:
            second = agent._kb_sections()
        build.assert_not_called()
        self.assertEqual(second, first)

        # 指纹变化 → 缓存失效并重建
        with mock.patch.object(agent, "KB_DIR", agent._KB_SHIPPED_DIR), \
                mock.patch.object(agent, "_KB_CACHE", None), \
                mock.patch.object(agent, "_kb_manifest",
                                  return_value=[["basics.md", 99, 222]]), \
                mock.patch.object(agent, "_kb_build",
                                  return_value=[{"file": "x.md", "title": "n",
                                                 "body": "", "title_l": "n",
                                                 "body_l": "n"}]) as build:
            third = agent._kb_sections()
        build.assert_called_once()
        self.assertEqual(third[0]["title"], "n")


class ChatRetryTests(unittest.TestCase):
    class FakeResponse:
        def __init__(self, status, body=b'{"choices":[{"message":{"content":"ok"}}]}',
                     retry_after=None):
            self.status = status
            self._body = body
            self._retry_after = retry_after

        def read(self, *args):
            return self._body

        def getheader(self, name):
            return self._retry_after if name == "Retry-After" else None

    class FakeConn:
        def __init__(self, responses):
            self.responses = list(responses)
            self.closed = False

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return self.responses.pop(0)

        def close(self):
            self.closed = True

    def setUp(self):
        self.cfg = {"active": "agnes", "providers": {}, "fallback": []}
        agent._POOL.clear()

    def tearDown(self):
        agent._POOL.clear()

    def _run_chat(self, responses, sleeps):
        conn = self.FakeConn(responses)
        with mock.patch.object(agent, "_connect", return_value=conn), \
                mock.patch.object(agent.time, "sleep", side_effect=sleeps.append):
            return agent.chat(self.cfg, [{"role": "user", "content": "hi"}])

    def test_429_is_retried_and_honors_retry_after(self):
        sleeps = []
        content, _ = self._run_chat(
            [self.FakeResponse(429, b'{"error":{"message":"slow down"}}', retry_after="2"),
             self.FakeResponse(200)], sleeps)
        self.assertEqual(content, "ok")
        self.assertEqual(sleeps, [2.0])

    def test_429_exhausts_retries_then_raises(self):
        sleeps = []
        with self.assertRaisesRegex(agent.ApiError, "HTTP 429"):
            self._run_chat([self.FakeResponse(429), self.FakeResponse(429),
                            self.FakeResponse(429)], sleeps)
        self.assertEqual(len(sleeps), 2)

    def test_client_error_400_is_not_retried(self):
        sleeps = []
        with self.assertRaisesRegex(agent.ApiError, "HTTP 400"):
            self._run_chat([self.FakeResponse(400)], sleeps)
        self.assertEqual(sleeps, [])

    def test_server_error_500_is_retried(self):
        content, _ = self._run_chat(
            [self.FakeResponse(500), self.FakeResponse(200)], [])
        self.assertEqual(content, "ok")


class SearchFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "plain.txt").write_text("hello world\n", encoding="utf-8")
        (self.root / "marker.md").write_text("nothing relevant\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_search_matches_filenames_not_only_content(self):
        result = agent.search_files("marker", str(self.root))
        self.assertIn("[文件名]", result)
        self.assertIn("marker.md", result)

    def test_content_search_still_works(self):
        result = agent.search_files("hello", str(self.root))
        self.assertIn("plain.txt", result)

    def test_regex_filename_search(self):
        result = agent.search_files(r"m.*r\.md", str(self.root), regex=True)
        self.assertIn("marker.md", result)


class LinuxHelpTests(unittest.TestCase):
    def test_no_match_lists_available_topics_without_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp) / "kb"
            kb.mkdir()
            (kb / "topic.md").write_text("## 标题\n内容", encoding="utf-8")
            with mock.patch.object(agent, "KB_DIR", str(kb)), \
                    mock.patch.object(agent, "_KB_CACHE", None):
                result = agent.linux_help("完全无关的查询词组xyz")
        self.assertIn("可用主题", result)
        self.assertIn("topic", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
