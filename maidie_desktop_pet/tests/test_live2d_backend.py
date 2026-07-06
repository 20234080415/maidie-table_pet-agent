from __future__ import annotations

import unittest

from animation.live2d_backend import Live2DBackend


class Live2DBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = Live2DBackend()

    def test_backend_can_be_created_with_empty_queue(self):
        self.assertEqual(self.backend.pending_commands, ())

    def test_supported_semantic_states_queue_viewer_commands(self):
        for state in ("speaking", "confused", "headpat"):
            result = self.backend.apply_state(state)
            self.assertTrue(result["ok"])
            self.assertEqual(result["command"], "applySemanticState")
            self.assertEqual(result["args"], [state])
            self.assertFalse(result["delivered"])

    def test_parameter_command_is_structured(self):
        result = self.backend.set_parameter("ParamAngleX", 10)
        self.assertEqual(result["command"], "setParameter")
        self.assertEqual(result["args"], ["ParamAngleX", 10.0])

    def test_apply_state_accepts_optional_intensity(self):
        result = self.backend.apply_state("confused", intensity=1.2)
        self.assertTrue(result["ok"])
        self.assertEqual(result["command"], "applySemanticState")
        self.assertEqual(result["args"], ["confused", 1.2])

    def test_invalid_intensity_is_not_queued(self):
        result = self.backend.apply_state("success", intensity=0)
        self.assertFalse(result["ok"])
        self.assertFalse(result["queued"])

    def test_load_model_and_reset_match_viewer_api(self):
        self.assertEqual(self.backend.load_model({"model3_json": "model.model3.json"})["command"],
                         "loadModel")
        self.assertEqual(self.backend.reset()["command"], "reset")

    def test_mouth_commands_match_viewer_api(self):
        self.assertEqual(self.backend.start_mouth()["command"], "startMouthTest")
        self.assertEqual(self.backend.stop_mouth()["command"], "stopMouthTest")

    def test_unknown_state_falls_back_without_crashing(self):
        result = self.backend.apply_state("surprised")
        self.assertTrue(result["ok"])
        self.assertTrue(result["fallback"])
        self.assertEqual(result["args"], ["idle"])
        self.assertIn("Unsupported semantic state", result["error"])

    def test_application_states_map_to_live2d_states(self):
        expected = {
            "idle": "idle", "talking": "speaking", "streaming": "speaking",
            "thinking": "thinking", "headpat": "headpat", "dragged": "dragged",
            "success": "success", "error": "error", "confused": "confused",
            "sleepy": "sleepy",
        }
        for source, target in expected.items():
            with self.subTest(source=source):
                result = self.backend.apply_state(source)
                self.assertTrue(result["ok"])
                self.assertEqual(result["args"], [target])

    def test_queue_can_be_drained_and_shutdown_is_explicit(self):
        self.backend.play_motion("Idle")
        self.backend.enable_mouse_follow(True)
        self.assertEqual(len(self.backend.drain_commands()), 2)
        shutdown = self.backend.shutdown()
        self.assertEqual(shutdown["command"], "shutdown")
        rejected = self.backend.reset()
        self.assertFalse(rejected["ok"])
        self.assertFalse(rejected["queued"])

    def test_without_sink_delivered_is_false(self):
        result = self.backend.apply_state("confused")
        self.assertTrue(result["ok"])
        self.assertTrue(result["queued"])
        self.assertFalse(result["delivered"])

    def test_with_sink_commands_are_submitted_and_delivered(self):
        captured = []
        backend = Live2DBackend(command_sink=lambda cmd: captured.append(cmd) or True)
        result = backend.apply_state("speaking")
        self.assertTrue(result["ok"])
        self.assertTrue(result["queued"])
        self.assertTrue(result["delivered"])
        self.assertTrue(result["submitted"])
        self.assertTrue(result["accepted_by_sink"])
        self.assertEqual(backend.pending_commands, ())
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["command"], "applySemanticState")
        self.assertEqual(captured[0]["args"], ["speaking"])

    def test_sink_exception_is_caught_and_delivered_is_false(self):
        def failing_sink(cmd):
            raise RuntimeError("sink error")
        backend = Live2DBackend(command_sink=failing_sink)
        result = backend.apply_state("idle")
        self.assertTrue(result["ok"])
        self.assertTrue(result["queued"])
        self.assertFalse(result["delivered"])
        self.assertFalse(result["submitted"])
        self.assertEqual(len(backend.pending_commands), 1)
        self.assertIn("command_sink 提交失败", result["error"])

    def test_successful_sink_does_not_retain_local_commands(self):
        backend = Live2DBackend(command_sink=lambda cmd: True)
        for _ in range(backend.LOCAL_QUEUE_MAXLEN + 50):
            backend.apply_state("confused")
        self.assertEqual(backend.pending_commands, ())
        self.assertEqual(backend.drain_commands(), [])

    def test_local_queue_is_bounded_and_can_be_drained(self):
        for index in range(self.backend.LOCAL_QUEUE_MAXLEN + 25):
            self.backend.set_parameter("ParamAngleX", index)
        self.assertEqual(len(self.backend.pending_commands), self.backend.LOCAL_QUEUE_MAXLEN)
        commands = self.backend.drain_commands()
        self.assertEqual(len(commands), self.backend.LOCAL_QUEUE_MAXLEN)
        self.assertEqual(commands[0]["args"], ["ParamAngleX", 25.0])
        self.assertEqual(self.backend.pending_commands, ())


if __name__ == "__main__":
    unittest.main()
