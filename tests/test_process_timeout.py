#!/usr/bin/env python3
"""Command timeout must terminate descendants and keep output bounded."""

from pathlib import Path
import os
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402


@unittest.skipIf(os.name == "nt", "POSIX process-group regression")
class ProcessTimeoutTests(unittest.TestCase):
    def test_timeout_kills_background_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "survived"
            command = "(sleep 6; touch %s) & sleep 30" % marker
            result = agent.run_cmd(command, timeout=5)
            self.assertIn("exit=124", result)
            time.sleep(1.5)
            self.assertFalse(marker.exists())

    def test_large_output_is_bounded(self):
        result = agent.run_cmd("yes x | head -c 200000", timeout=10)
        self.assertLess(len(result), 10000)
        self.assertIn("截断", result)


if __name__ == "__main__": unittest.main(verbosity=2)
