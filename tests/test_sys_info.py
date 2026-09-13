#!/usr/bin/env python3
"""Built-in agent host-spec query: sys_info tool, CLI command, registration."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import agent  # noqa: E402


class SysInfoTests(unittest.TestCase):
    def test_returns_core_fields(self):
        text = agent.sys_info()
        self.assertIn("OS:", text)
        self.assertIn("CPU cores:", text)
        self.assertIn("Python:", text)
        self.assertIn("AgentBoot: v", text)
        self.assertNotIn("None", text)

    def test_memory_present_with_sane_unit(self):
        text = agent.sys_info()
        if "Memory:" in text:
            line = next(l for l in text.splitlines() if l.startswith("Memory:"))
            self.assertTrue(any(u in line for u in ("KB", "MB", "GB", "TB")))

    def test_disk_report_includes_root(self):
        disks = agent._disk_report()
        self.assertTrue(disks, "至少报告一个挂载点")
        if agent.os.name == "nt":
            self.assertTrue(any(m.upper().startswith("C:") for m, _, _ in disks))
        else:
            self.assertEqual(disks[0][0], agent.os.path.abspath("/"))

    def test_fmt_bytes_units(self):
        self.assertEqual(agent._fmt_bytes(0), "0 B")
        self.assertEqual(agent._fmt_bytes(512), "512 B")
        self.assertTrue(agent._fmt_bytes(5 * 1024 ** 3).endswith("GB"))

    def test_mem_bytes_sane(self):
        total, avail = agent._mem_bytes()
        if total:
            self.assertGreater(total, 0)
            self.assertLessEqual(avail or 0, total)


class ToolRegistrationTests(unittest.TestCase):
    def test_sys_info_registered_as_tool(self):
        names = [t["function"]["name"] for t in agent.TOOLS]
        self.assertIn("sys_info", names)
        tool = next(t for t in agent.TOOLS if t["function"]["name"] == "sys_info")
        self.assertEqual(tool["function"]["parameters"]["properties"], {})

    def test_execute_tool_dispatches_sys_info(self):
        result, danger = agent.execute_tool({"confirm": "smart"}, "sys_info", {}, set())
        self.assertFalse(danger)
        self.assertIn("OS:", result)

    def test_system_prompt_mentions_tool(self):
        self.assertIn("sys_info", agent.system_prompt())


class CliSysCommandTests(unittest.TestCase):
    def test_ab_sys_prints_specs_without_model_config(self):
        proc = subprocess.run([sys.executable, str(ROOT / "core" / "agent.py"), "sys"],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr[:300])
        self.assertIn("OS:", proc.stdout)
        self.assertIn("CPU cores:", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
