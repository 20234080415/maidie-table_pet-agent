from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from animation.atlas import AtlasAnimationEngine
from ui.sprite import HatchPetSprite


class SpriteDirectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.atlas_path = Path(__file__).parents[1] / "assets" / "spritesheet.webp"

    def test_walk_and_run_use_the_right_facing_source_row(self):
        self.assertEqual(AtlasAnimationEngine.ANIMATIONS["walk"][0], 1)
        self.assertEqual(AtlasAnimationEngine.ANIMATIONS["run"][0], 1)
        self.assertNotIn("walk-left", AtlasAnimationEngine.ANIMATIONS)
        self.assertNotIn("run-left", AtlasAnimationEngine.ANIMATIONS)

    def test_renderer_mirrors_the_final_frame_exactly_once(self):
        sprite = HatchPetSprite(self.atlas_path)
        sprite.resize(320, 380)
        sprite.set_animation("walk")
        sprite.set_facing_right(True)
        right = sprite.pixmap().toImage()

        sprite.set_facing_right(False)
        left = sprite.pixmap().toImage()
        # Smooth painter sampling can differ at transparent edges, so compare
        # mirrored pixels rather than QImage metadata/format identity.
        matching = 0
        total = left.width() * left.height()
        for y in range(left.height()):
            for x in range(left.width()):
                matching += left.pixel(x, y) == right.pixel(right.width() - 1 - x, y)
        self.assertGreater(matching / total, 0.95)
        sprite.engine.stop()


if __name__ == "__main__":
    unittest.main()
