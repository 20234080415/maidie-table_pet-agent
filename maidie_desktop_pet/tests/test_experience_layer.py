from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QElapsedTimer
from PyQt6.QtWidgets import QApplication

from core.experience.attention import AttentionManager, AttentionState
from core.experience.emotion import EmotionState
from core.experience.orchestrator import BehaviorOrchestrator
from core.experience.speech_player import SpeechPlayer, SpeechSegment


class SpeechPlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_complete_reply_splits_chinese_english_and_ellipsis(self):
        segments = SpeechPlayer.split_reply(
            "嗯……让我看看。Oh, here it is!", emotion="thinking", action="talk"
        )
        self.assertEqual([item.text for item in segments],
                         ["嗯……", "让我看看。", "Oh,", " here it is!"])
        self.assertTrue(all(item.emotion == "thinking" for item in segments))
        self.assertTrue(all(item.action == "talk" for item in segments))

    def test_segment_queue_is_non_blocking_and_preserves_metadata(self):
        player = SpeechPlayer(initial_pause=(0, 0), character_pause=(0, 0),
                              sentence_pause=(0, 0), characters_per_tick=20)
        visible, started, done = [], [], []
        player.text_ready.connect(visible.append)
        player.segment_started.connect(started.append)
        player.finished.connect(lambda: done.append(True))
        player.start()
        player.push_segments([SpeechSegment("嗯……", 0, "shy", "talking", "shy")])
        player.finish()
        elapsed = QElapsedTimer(); elapsed.start()
        while not done and elapsed.elapsed() < 500:
            self.app.processEvents()
        self.assertTrue(done)
        self.assertEqual("".join(visible), "嗯……")
        self.assertEqual(started[0].emotion, "shy")


class EmotionStateTests(unittest.TestCase):
    def test_events_change_emotion_and_values_decay(self):
        now = [0.0]
        emotion = EmotionState(half_life_seconds=10, clock=lambda: now[0])
        emotion.apply_event("headpat")
        self.assertEqual(emotion.get_dominant_emotion(), "happy")
        before = emotion.snapshot()["happy"]
        now[0] = 10.0
        self.assertAlmostEqual(emotion.snapshot()["happy"], before / 2, places=5)

    def test_failure_becomes_dominant(self):
        emotion = EmotionState()
        emotion.apply_event("tool_failure")
        self.assertEqual(emotion.get_dominant_emotion(), "failed")


class AttentionManagerTests(unittest.TestCase):
    def test_updates_state_and_only_injects_for_view_references(self):
        manager = AttentionManager(now=lambda: datetime(2026, 7, 2, tzinfo=timezone.utc))
        state = manager.update({
            "active_app": "Code", "app_type": "coding", "window_title": "router.py",
            "screen": {"screen_text": "Traceback: ValueError", "confidence": .8},
            "clipboard_changed": True,
        })
        self.assertEqual(state.app_name, "Code")
        self.assertEqual(state.activity_type, "coding")
        self.assertEqual(state.screen_summary, "Traceback: ValueError")
        self.assertTrue(manager.clipboard_changed)
        self.assertIsNotNone(manager.context_for("帮我看看这个报错"))
        self.assertIsNone(manager.context_for("讲个笑话"))


class BehaviorOrchestratorTests(unittest.TestCase):
    def test_error_notice_and_global_cooldown(self):
        now = [1000.0]
        orchestrator = BehaviorOrchestrator(cooldown_seconds=60, clock=lambda: now[0])
        attention = AttentionState("Code", "main.py - error", "coding", "Traceback", .9, "now")
        first = orchestrator.decide(attention, "concern", 0)
        self.assertEqual(first.kind, "error_notice")
        self.assertIsNone(orchestrator.decide(attention, "concern", 0))
        now[0] += 61
        self.assertEqual(orchestrator.decide(attention, "concern", 0).kind, "error_notice")

    def test_supported_idle_and_game_behaviors(self):
        orchestrator = BehaviorOrchestrator(clock=lambda: 1000)
        game = AttentionState(activity_type="gaming", confidence=.6)
        self.assertEqual(orchestrator.decide(game, "happy", 0).kind, "game_tease")
        idle = BehaviorOrchestrator(clock=lambda: 1000)
        self.assertEqual(idle.decide(AttentionState(), "idle", 90).kind, "idle_glance")


if __name__ == "__main__":
    unittest.main()
