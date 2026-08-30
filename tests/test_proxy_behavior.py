#!/usr/bin/env python3
"""Saved proxy settings apply to Python downloads and model connections."""

from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
import agent  # noqa: E402
import menu  # noqa: E402


class ProxyBehaviorTests(unittest.TestCase):
    def test_invalid_proxy_is_rejected(self):
        with mock.patch.object(menu, "load_env_json", return_value={}), \
                mock.patch.object(menu, "save_env_json") as save:
            self.assertFalse(menu.set_proxy("socks5://localhost:1080"))
        save.assert_not_called()

    def test_saved_proxy_updates_python_environment(self):
        with mock.patch.object(menu, "load_env_json", return_value={}), \
                mock.patch.object(menu, "save_env_json"), \
                mock.patch.object(menu, "npm_cmd", return_value=None), \
                mock.patch.object(menu, "write_env_scripts"):
            self.assertTrue(menu.set_proxy("http://127.0.0.1:7890"))
        self.assertEqual(os.environ.get("HTTPS_PROXY"), "http://127.0.0.1:7890")
        os.environ.pop("HTTP_PROXY", None); os.environ.pop("HTTPS_PROXY", None)

    def test_https_model_connection_tunnels_through_proxy(self):
        fake = mock.Mock()
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy.example:8080"}, clear=False), \
                mock.patch("http.client.HTTPSConnection", return_value=fake) as connection:
            agent._POOL.clear()
            self.assertIs(agent._connect("https", "api.example", 443), fake)
        connection.assert_called_once()
        fake.set_tunnel.assert_called_once_with("api.example", 443, headers={})


if __name__ == "__main__": unittest.main(verbosity=2)
