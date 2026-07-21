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
        self.assertTrue(
            readme.startswith("# threejs-sculpt-dna — A GitHub Copilot Plugin")
        )
        self.assertNotIn(
            "# Three.js Sculpt DNA for GitHub Copilot CLI",
            readme,
        )

    def test_readme_and_manual_document_marketplace_install(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
        install = "threejs-sculpt-dna@threejs-copilot-plugins"
        repository = (
            "hyeonsangjeon/threejs-sculpt-dna"
        )
        for document in (readme, guide):
            self.assertIn(install, document)
            self.assertIn(repository, document)
        self.assertIn(
            "assets/github-copilot-image-prompt-example.png",
            readme,
        )

    def test_overview_links_canonical_repo_skill_and_reproducible_check(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (
            ROOT / "skills" / "object-to-threejs-procedural" / "SKILL.md"
        ).read_text(encoding="utf-8")
        overview = "\n".join(readme.splitlines()[:100])

        for expected in (
            "**Canonical repository:**",
            "https://github.com/hyeonsangjeon/threejs-sculpt-dna",
            "skills/object-to-threejs-procedural/SKILL.md",
            "star the canonical repository",
            "### 5-minute reproducible check",
            "assets/brick-offroad-reference.jpeg",
            "examples/repolis-tree/object-sculpt-spec.json",
            '"technicalSuitability": "pass"',
            "currentPass: complete",
        ):
            self.assertIn(expected, overview)

        for expected in (
            "## Fast Path",
            "assessment.json",
            "object-sculpt-spec.json",
            "runtime node, mesh, socket, collider, and destruction maps",
            "python3 ../../scripts/probe_reference_image.py <image>",
            "Do not use an imported mesh.",
        ):
            self.assertIn(expected, skill)

    def test_release_changelog_matches_plugin_version(self) -> None:
        plugin = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"## [{plugin['version']}]", changelog)
        self.assertIn(
            "img.shields.io/github/v/release/hyeonsangjeon/threejs-sculpt-dna",
            readme,
        )

if __name__ == "__main__":
    unittest.main()
