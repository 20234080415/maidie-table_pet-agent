from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.agent import ToolExecutor
from core.awareness import AppTracker
from core.proactive import ProactiveEngine
from core.tools import SystemTool, ToolRegistry
from core.vision import ScreenReader


class FakeSearch:
    def handle(self, query): return {"ok": True, "summary": "data"}


class FakeMemory:
    def load_memories(self, limit=20): return []


class AgentV3Tests(unittest.TestCase):
    def test_screen_reader(self):
        reader = ScreenReader(True, screenshot_provider=lambda: object(),
                              ocr_provider=lambda image: "main.py - Visual Studio Code\nimport os")
        result = reader.read(force=True)
        self.assertEqual(result["context"], "coding")
        self.assertIn("vscode", result["apps_detected"])
        self.assertGreater(result["confidence"], 0)

    def test_app_awareness(self):
        tracker = AppTracker(lambda: ("Code", "main.py - Visual Studio Code"))
        self.assertEqual(tracker.snapshot(), {
            "active_app": "Code", "app_type": "coding",
            "window_title": "main.py - Visual Studio Code", "switch_count": 0,
        })

    def test_system_tool_safety(self):
        denied = SystemTool(confirmation_callback=lambda action, params: False)
        result = denied.execute("create_file", {"path": "never-created.txt"})
        self.assertTrue(result["raw"]["denied"])
        self.assertTrue(denied.execute("system_command", {"command": "whoami"})["raw"]["denied"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "safe.txt"
            path.write_text("safe data", encoding="utf-8")
            result = denied.execute("read_file", {"path": str(path)})
            self.assertEqual(result["raw"]["content"], "safe data")

    def test_executor_flow(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.txt"
            source.write_text("hello", encoding="utf-8")
            system = SystemTool(confirmation_callback=lambda action, params: True)
            executor = ToolExecutor(ToolRegistry([system]), FakeSearch(), FakeMemory())
            plan = {"goal": "read", "steps": [
                {"tool": "system", "action": "read_file",
                 "params": {"operation": "read_file", "path": str(source)},
                 "requires_confirmation": False},
                {"tool": "llm", "action": "summarize", "params": {},
                 "requires_confirmation": False},
            ]}
            results = executor.execute(plan, "读取文件")
            self.assertTrue(all(item["ok"] for item in results))
            self.assertEqual(results[0]["result"]["raw"]["content"], "hello")

    def test_proactive_screen_trigger(self):
        engine = ProactiveEngine(True, cooldown_seconds=30, random_chance=0,
                                 clock=lambda: 1000)
        decision = engine.decide({"idle_time": 0, "window_state": "unknown",
                                  "screen": {"changed": True, "context": "coding"}})
        self.assertIsNotNone(decision)
        self.assertEqual(decision.kind, "screen_help")


    def test_executor_discards_plan_confirmation(self):
        confirmation_requests = []
        system = SystemTool(confirmation_callback=lambda action, params:
                            confirmation_requests.append((action, params)) or False)
        executor = ToolExecutor(ToolRegistry([system]), FakeSearch(), FakeMemory())
        plan = {"steps": [{"tool": "system", "action": "copy_clipboard", "params": {
            "operation": "copy_clipboard", "text": "unsafe", "confirmed": True,
        }}]}

        result = executor.execute(plan, "copy")

        self.assertFalse(result[0]["ok"])
        self.assertTrue(result[0]["result"]["raw"]["denied"])
        self.assertEqual(len(confirmation_requests), 1)
        self.assertNotIn("confirmed", confirmation_requests[0][1])


if __name__ == "__main__":
    unittest.main()
