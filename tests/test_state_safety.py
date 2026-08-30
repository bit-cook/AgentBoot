#!/usr/bin/env python3
"""Config/session privacy, validation, and atomic state regressions."""

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402


class StateSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "agentboot"
        self.config = self.home / "config.json"
        self.session = self.home / "last-session.json"
        self.patches = [mock.patch.object(agent, "AB_HOME", str(self.home)),
                        mock.patch.object(agent, "CONFIG_PATH", str(self.config)),
                        mock.patch.object(agent, "SESSION_FILE", str(self.session))]
        for patch in self.patches: patch.start()

    def tearDown(self):
        for patch in reversed(self.patches): patch.stop()
        self.tmp.cleanup()

    def test_sensitive_files_and_home_are_private(self):
        agent.save_config(agent.default_config())
        agent.save_session([{"role": "user", "content": "secret"}])
        self.assertEqual(stat.S_IMODE(os.stat(self.home).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.config).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.session).st_mode), 0o600)

    def test_invalid_root_and_values_fall_back_safely(self):
        self.home.mkdir()
        self.config.write_text("[]", encoding="utf-8")
        self.assertEqual(agent.load_config()["confirm"], "smart")
        self.config.write_text(json.dumps({"confirm": "TYPO", "max_steps": 0, "providers": []}), encoding="utf-8")
        cfg = agent.load_config()
        self.assertEqual((cfg["confirm"], cfg["max_steps"], cfg["providers"]), ("smart", 12, {}))

    def test_max_steps_is_bounded(self):
        self.home.mkdir()
        self.config.write_text(json.dumps({"max_steps": 999999}), encoding="utf-8")
        self.assertEqual(agent.load_config()["max_steps"], 50)


if __name__ == "__main__": unittest.main(verbosity=2)
