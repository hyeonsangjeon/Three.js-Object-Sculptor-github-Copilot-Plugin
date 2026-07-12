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
            "brick-offroad-reference.jpeg": (1600, 1394, "pass"),
            "repolis-tree-reference.jpeg": (1024, 559, "pass"),
            "seoul-challenge-reference.jpeg": (842, 476, "conditional"),
        }
        for filename, (width, height, suitability) in expected.items():
            with self.subTest(filename=filename):
                path = ROOT / "assets" / filename
                result = probe(path)
                self.assertEqual((result["width"], result["height"]), (width, height))
                self.assertEqual(result["technicalSuitability"], suitability)
                self.assertLess(path.stat().st_size, 750_000)
                self.assertNotIn(b"Exif\x00\x00", path.read_bytes())

    def test_showcase_renders_have_readme_dimensions(self) -> None:
        for filename in (
            "brick-offroad-sculpt-dna-intermediate.png",
            "brick-offroad-sculpt-dna-result.png",
            "repolis-tree-sculpt-dna-result.png",
            "seoul-challenge-sculpt-dna-result.png",
        ):
            with self.subTest(filename=filename):
                path = ROOT / "assets" / filename
                result = probe(path)
                self.assertEqual((result["width"], result["height"]), (1200, 675))
                self.assertEqual(result["technicalSuitability"], "pass")
                self.assertLess(path.stat().st_size, 500_000)

    def test_copilot_prompt_example_is_readme_ready(self) -> None:
        path = ROOT / "assets" / "github-copilot-image-prompt-example.png"
        result = probe(path)
        self.assertEqual((result["width"], result["height"]), (1200, 760))
        self.assertEqual(result["technicalSuitability"], "pass")
        self.assertLess(path.stat().st_size, 500_000)

    def test_social_preview_matches_github_recommendation(self) -> None:
        path = ROOT / "assets" / "social-preview.png"
        result = probe(path)
        self.assertEqual((result["width"], result["height"]), (1280, 640))
        self.assertEqual(result["technicalSuitability"], "pass")
        self.assertLess(path.stat().st_size, 1_000_000)

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
