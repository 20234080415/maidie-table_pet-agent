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

    def test_queue_can_be_drained_and_shutdown_is_explicit(self):
        self.backend.play_motion("Idle")
        self.backend.enable_mouse_follow(True)
        self.assertEqual(len(self.backend.drain_commands()), 2)
        shutdown = self.backend.shutdown()
        self.assertEqual(shutdown["command"], "shutdown")
        rejected = self.backend.reset()
        self.assertFalse(rejected["ok"])
        self.assertFalse(rejected["queued"])


if __name__ == "__main__":
    unittest.main()
