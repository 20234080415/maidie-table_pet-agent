from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from memory.memory import ConversationMemory


class MemorySystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "memories.db"
        self.memory = ConversationMemory(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_memory_save(self):
        self.memory.save("我叫小明", "很高兴认识你")
        recent = self.memory.get_recent()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["message"], "我叫小明")
        self.assertTrue(self.memory.save_memory("fact", "name", "小明", 0.8))

    def test_memory_load(self):
        self.memory.save_memory("fact", "project", "Maidie", 0.7)
        self.memory.save_memory("preference", "editor", "VS Code", 0.95)
        loaded = self.memory.load_memories()
        self.assertEqual(loaded[0]["key"], "editor")
        self.assertEqual(loaded[0]["type"], "preference")
        self.assertIn("VS Code", self.memory.prompt_context())

    def test_memory_update(self):
        self.memory.save_memory("preference", "drink", "咖啡", 0.8)
        self.memory.save_memory("preference", "drink", "红茶", 0.9)
        loaded = self.memory.load_memories()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["value"], "红茶")
        self.assertEqual(loaded[0]["importance"], 0.9)

    def test_memory_limit(self):
        for index in range(25):
            self.memory.save(f"message-{index}", f"response-{index}")
        recent = self.memory.get_recent()
        self.assertEqual(len(recent), 20)
        self.assertEqual(recent[0]["message"], "message-5")
        connection = sqlite3.connect(self.path)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM memories WHERE type='chat'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 20)

    def test_sensitive_memory_is_rejected(self):
        self.assertFalse(
            self.memory.save_memory("fact", "api_key", "sk-secret-value", 1.0)
        )
        self.memory.save("我的密码是 123456", "我不会保存它")
        self.assertEqual(self.memory.get_recent(), [])


if __name__ == "__main__":
    unittest.main()
