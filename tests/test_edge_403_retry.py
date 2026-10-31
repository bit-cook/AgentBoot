#!/usr/bin/env python3
"""回归测试：Groq CDN 边缘 403 抖动与重试。

背景（v1.5.2 实测）：Groq 前端是 Cloudflare，同一请求在 PDX/SEA 边缘间
抖动——时 200/404，时裸体 403。API 级拒绝（模型无权限、组织屏蔽）带
结构化 error（type/code），重试无意义；边缘拒绝只有裸 "Forbidden" 或
空体，换连接重试即可。

锁定内容：
1. _is_edge_rejection 的判别（裸 Forbidden/空体/非 JSON = 边缘；
   带 type/code = 真拒绝）
2. chat() 对边缘 403 重试后成功；对真 403 立即失败不重试
"""

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402


class EdgeRejectionTests(unittest.TestCase):
    def test_empty_body_is_edge(self):
        self.assertTrue(agent._is_edge_rejection(""))

    def test_bare_forbidden_is_edge(self):
        self.assertTrue(agent._is_edge_rejection('{"error":{"message":"Forbidden"}}'))

    def test_structured_denial_is_not_edge(self):
        body = json.dumps({"error": {"message": "no access",
                                     "type": "invalid_request_error",
                                     "code": "model_not_found"}})
        self.assertFalse(agent._is_edge_rejection(body))

    def test_permission_error_is_not_edge(self):
        body = json.dumps({"error": {"message": "blocked at org level",
                                     "type": "permissions_error",
                                     "code": "model_permission_blocked_org"}})
        self.assertFalse(agent._is_edge_rejection(body))

    def test_html_error_page_is_edge(self):
        self.assertTrue(agent._is_edge_rejection("<html>403 Forbidden</html>"))


class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body.encode() if isinstance(body, str) else body

    def read(self, *a):
        return self._body

    def getheader(self, name, default=None):
        return default

    def readline(self):
        return b""


class _FakeConnection:
    """按脚本返回响应：403 边缘拒绝 → 200 成功。"""

    def __init__(self, script):
        self._script = list(script)
        self.requests = 0

    def request(self, *a, **kw):
        self.requests += 1

    def getresponse(self):
        status, body = self._script.pop(0)
        return _FakeResponse(status, body)

    def close(self):
        pass


def _ok_body():
    return json.dumps({"choices": [{"message": {"content": "你好",
                                                "tool_calls": None},
                                    "finish_reason": "stop"}]})


class ChatEdgeRetryTests(unittest.TestCase):
    CFG = {"active": "groq", "providers": {},
           "fallback": []}

    def _patch(self, script):
        conn = _FakeConnection(script)
        patcher = mock.patch.object(agent, "_connect", return_value=conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        return conn

    def test_edge_403_is_retried_then_succeeds(self):
        conn = self._patch([(403, '{"error":{"message":"Forbidden"}}'),
                            (200, _ok_body())])
        with mock.patch.object(agent, "_drop_pool"), \
                mock.patch.object(agent.time, "sleep"):
            content, tcs = agent.chat(self.CFG,
                                      [{"role": "user", "content": "hi"}])
        self.assertEqual(content, "你好")
        self.assertEqual(conn.requests, 2)

    def test_structured_403_fails_immediately(self):
        conn = self._patch([(403, json.dumps({
            "error": {"message": "model blocked", "type": "permissions_error",
                      "code": "model_permission_blocked_org"}}))])
        with mock.patch.object(agent, "_drop_pool"), \
                mock.patch.object(agent.time, "sleep"):
            with self.assertRaises(agent.ApiError) as ctx:
                agent.chat(self.CFG, [{"role": "user", "content": "hi"}])
        self.assertIn("403", str(ctx.exception))
        self.assertEqual(conn.requests, 1)  # 不重试

    def test_edge_403_exhausts_retries_then_raises(self):
        conn = self._patch([(403, '{"error":{"message":"Forbidden"}}'),
                            (403, ""),
                            (403, "")])
        with mock.patch.object(agent, "_drop_pool"), \
                mock.patch.object(agent.time, "sleep"):
            with self.assertRaises(agent.ApiError):
                agent.chat(self.CFG, [{"role": "user", "content": "hi"}])
        self.assertEqual(conn.requests, 3)  # 1 + 2 次重试后放弃


if __name__ == "__main__":
    unittest.main(verbosity=2)
