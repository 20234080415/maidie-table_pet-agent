from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def _seed_all_memory_types(self):
        self.memory.save("hello", "hi")
        self.memory.save_memory("fact", "name", "Ming", 0.8)
        self.memory.save_memory("preference", "style", "concise", 0.9)

    def test_delete_conversation_history_preserves_long_term_memory(self):
        self._seed_all_memory_types()

        self.assertTrue(self.memory.delete_conversation_history())

        self.assertEqual(self.memory.get_recent(), [])
        self.assertEqual(
            {(item["type"], item["key"]) for item in self.memory.load_memories()},
            {("fact", "name"), ("preference", "style")},
        )

    def test_delete_long_term_memory_preserves_conversation_history(self):
        self._seed_all_memory_types()

        self.assertTrue(self.memory.delete_long_term_memory())

        self.assertEqual(len(self.memory.get_recent()), 1)
        self.assertEqual(self.memory.load_memories(), [])

    def test_delete_all_memory_persists_after_reopening_database(self):
        self._seed_all_memory_types()

        self.assertTrue(self.memory.delete_all_memory())
        reopened = ConversationMemory(self.path)

        self.assertEqual(reopened.get_recent(), [])
        self.assertEqual(reopened.load_memories(), [])

    def test_clear_remains_a_full_delete_compatibility_alias(self):
        self._seed_all_memory_types()

        self.assertTrue(self.memory.clear())

        self.assertEqual(self.memory.get_recent(), [])
        self.assertEqual(self.memory.load_memories(), [])

    def test_each_scoped_delete_persists_after_reopening_database(self):
        self._seed_all_memory_types()
        self.assertTrue(self.memory.delete_conversation_history())
        reopened = ConversationMemory(self.path)
        self.assertEqual(reopened.get_recent(), [])
        self.assertEqual(len(reopened.load_memories()), 2)

        reopened.save("new", "reply")
        self.assertTrue(reopened.delete_long_term_memory())
        reopened_again = ConversationMemory(self.path)
        self.assertEqual(len(reopened_again.get_recent()), 1)
        self.assertEqual(reopened_again.load_memories(), [])

    def test_stale_generation_cannot_write_extracted_memory(self):
        generation = self.memory.generation_token()
        self.assertTrue(self.memory.delete_conversation_history())

        stored = self.memory.save_extracted({
            "facts": [{"key": "name", "value": "old"}],
            "preferences": [],
        }, generation=generation)

        self.assertFalse(stored)
        self.assertEqual(self.memory.load_memories(), [])

    def test_delete_failure_is_reported(self):
        self._seed_all_memory_types()
        with patch.object(
            self.memory, "_connect", side_effect=sqlite3.OperationalError("locked")
        ):
            self.assertFalse(self.memory.delete_all_memory())

        self.assertEqual(len(self.memory.get_recent()), 1)
        self.assertEqual(len(self.memory.load_memories()), 2)


if __name__ == "__main__":
    unittest.main()
