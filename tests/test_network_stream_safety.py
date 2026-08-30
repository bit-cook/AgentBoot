#!/usr/bin/env python3
"""Model transport, SSE completeness, and HTTP SSRF security regressions."""

from pathlib import Path
import socket
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402


class FakeStream:
    def __init__(self, lines):
        self.lines = iter(lines)

    def readline(self):
        return next(self.lines, b"")

    def read(self, *_args):
        return b""


class StreamSafetyTests(unittest.TestCase):
    def test_clean_eof_without_terminal_frame_is_rejected(self):
        response = FakeStream([b'data: {"choices":[{"delta":{"content":"partial"}}]}\n'])
        with self.assertRaisesRegex(agent.ApiError, "中断"):
            agent._read_stream(response, lambda _piece: None, None, "https", "example.com", 443)

    def test_partial_tool_call_is_never_returned(self):
        response = FakeStream([b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"x","function":{"name":"run_cmd","arguments":"{\\\"command\\\":"}}]}}]}\n'])
        with self.assertRaises(agent.StreamInterrupted):
            agent._read_stream(response, lambda _piece: None, None, "https", "example.com", 443)

    def test_malformed_sse_is_rejected(self):
        response = FakeStream([b"data: {not-json}\n", b"data: [DONE]\n"])
        with self.assertRaisesRegex(agent.ApiError, "JSON"):
            agent._read_stream(response, lambda _piece: None, None, "https", "example.com", 443)

    def test_complete_tool_arguments_must_be_valid_object_json(self):
        response = FakeStream([
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"x","function":{"name":"run_cmd","arguments":"[]"}}]}}]}\n',
            b"data: [DONE]\n",
        ])
        with self.assertRaisesRegex(agent.ApiError, "工具参数"):
            agent._read_stream(response, lambda _piece: None, None, "https", "example.com", 443)


class NetworkBoundaryTests(unittest.TestCase):
    def test_invalid_model_scheme_is_rejected(self):
        with self.assertRaises(agent.ApiError):
            agent._validate_model_transport("htps", "127.0.0.1", "secret")

    def test_http_model_with_key_is_rejected_even_on_loopback(self):
        with self.assertRaises(agent.ApiError):
            agent._validate_model_transport("http", "127.0.0.1", "secret")

    def test_keyless_loopback_http_model_is_allowed(self):
        agent._validate_model_transport("http", "localhost", "")

    def test_http_get_rejects_loopback_without_opening(self):
        with mock.patch("urllib.request.OpenerDirector.open") as opened:
            result = agent.http_get("http://127.0.0.1:12345/internal")
        self.assertIn("拒绝", result)
        opened.assert_not_called()

    def test_public_url_validation_rejects_private_dns_resolution(self):
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 0))]
        with mock.patch.object(agent.socket, "getaddrinfo", return_value=private), \
                self.assertRaisesRegex(ValueError, "非公网"):
            agent._validate_public_http_url("https://internal.example/path")


if __name__ == "__main__":
    unittest.main(verbosity=2)
