from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PluginManifestTests(unittest.TestCase):
    def test_marketplace_registers_root_plugin(self) -> None:
        plugin = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads(
            (
                ROOT / ".github" / "plugin" / "marketplace.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(marketplace["name"], "threejs-copilot-plugins")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], plugin["name"])
        self.assertEqual(entry["version"], plugin["version"])
        self.assertEqual(entry["source"], ".")
        self.assertEqual(entry["license"], "MIT")

    def test_public_brand_name_does_not_include_cli(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith("# Three.js Sculpt DNA for GitHub Copilot"))
        self.assertNotIn(
            "# Three.js Sculpt DNA for GitHub Copilot CLI",
            readme,
        )


if __name__ == "__main__":
    unittest.main()
