from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from probe_reference_image import probe  # noqa: E402


class AssetTests(unittest.TestCase):
    def test_release_images_are_optimized_and_metadata_free(self) -> None:
        expected = {
            "brick-offroad-reference.jpeg": (1600, 1394),
            "repolis-tree-reference.jpeg": (1024, 559),
            "seoul-challenge-reference.jpeg": (1350, 1800),
        }
        for filename, dimensions in expected.items():
            with self.subTest(filename=filename):
                path = ROOT / "assets" / filename
                result = probe(path)
                self.assertEqual((result["width"], result["height"]), dimensions)
                self.assertEqual(result["technicalSuitability"], "pass")
                self.assertLess(path.stat().st_size, 750_000)
                self.assertNotIn(b"Exif\x00\x00", path.read_bytes())

    def test_inherited_demo_images_are_not_released(self) -> None:
        for filename in (
            "ancient-autumn-tree-demo.png",
            "codex-prompt-example.png",
            "tower-ship-demo.png",
        ):
            with self.subTest(filename=filename):
                self.assertFalse((ROOT / "assets" / filename).exists())


if __name__ == "__main__":
    unittest.main()
