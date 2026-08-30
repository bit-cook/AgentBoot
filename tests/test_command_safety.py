#!/usr/bin/env python3
"""Security regressions for command chains and confirmation policies."""

from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402


class CommandClassificationTests(unittest.TestCase):
    def test_all_read_only_chain_is_safe(self):
        self.assertEqual(agent.classify_cmd("pwd && ls -la | head -n 5"), "safe")

    def test_mutating_command_after_safe_prefix_is_not_safe(self):
        self.assertEqual(agent.classify_cmd("echo ok; touch /tmp/agentboot-test"), "normal")

    def test_dangerous_command_anywhere_in_chain_wins(self):
        self.assertEqual(agent.classify_cmd("pwd && rm -rf /"), "danger")

    def test_output_redirection_is_not_read_only(self):
        self.assertEqual(agent.classify_cmd("echo changed > config.txt"), "normal")

    def test_command_substitution_is_not_read_only(self):
        self.assertEqual(agent.classify_cmd("echo $(touch /tmp/agentboot-test)"), "normal")

    def test_systemctl_only_allows_read_only_subcommands(self):
        self.assertEqual(agent.classify_cmd("systemctl status ssh"), "safe")
        self.assertEqual(agent.classify_cmd("systemctl stop ssh"), "normal")

    def test_ip_mutation_is_not_safe(self):
        self.assertEqual(agent.classify_cmd("ip addr show"), "safe")
        self.assertEqual(agent.classify_cmd("ip link set eth0 down"), "normal")

    def test_case_insensitive_powershell_danger_detection(self):
        command = "Remove-Item -Recurse -Force -Path C:\\Users"
        self.assertEqual(agent.classify_cmd(command), "danger")


class ConfirmationPolicyTests(unittest.TestCase):
    def test_safe_mode_runs_read_only_command(self):
        with mock.patch.object(agent, "run_cmd", return_value="ok") as run:
            result, danger = agent.execute_tool(
                {"confirm": "safe"}, "run_cmd", {"command": "pwd"}, set())
        self.assertEqual(result, "ok")
        self.assertFalse(danger)
        run.assert_called_once()

    def test_safe_mode_blocks_mutating_command(self):
        with mock.patch.object(agent, "run_cmd") as run:
            result, _danger = agent.execute_tool(
                {"confirm": "safe"}, "run_cmd", {"command": "touch x"}, set())
        self.assertIn("safe", result.lower())
        run.assert_not_called()

    def test_safe_mode_blocks_file_write(self):
        with mock.patch.object(agent, "write_file") as write:
            result, _danger = agent.execute_tool(
                {"confirm": "safe"}, "write_file", {"path": "x", "content": "y"}, set())
        self.assertIn("safe", result.lower())
        write.assert_not_called()

    def test_smart_noninteractive_blocks_unconfirmed_mutation(self):
        with mock.patch.object(agent, "_is_interactive", return_value=False), \
                mock.patch.object(agent, "run_cmd") as run:
            result, _danger = agent.execute_tool(
                {"confirm": "smart"}, "run_cmd", {"command": "touch x"}, set())
        self.assertIn("非交互", result)
        run.assert_not_called()

    def test_smart_interactive_requires_file_write_confirmation(self):
        with mock.patch.object(agent, "_is_interactive", return_value=True), \
                mock.patch("builtins.input", return_value="n"), \
                mock.patch.object(agent, "write_file") as write:
            result, _danger = agent.execute_tool(
                {"confirm": "smart"}, "write_file", {"path": "x", "content": "y"}, set())
        self.assertIn("拒绝", result)
        write.assert_not_called()

    def test_always_mode_allows_normal_command(self):
        with mock.patch.object(agent, "run_cmd", return_value="ok") as run:
            result, _danger = agent.execute_tool(
                {"confirm": "always"}, "run_cmd", {"command": "touch x"}, set())
        self.assertEqual(result, "ok")
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
