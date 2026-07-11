from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CommunityFilesTests(unittest.TestCase):
    def test_roadmap_and_contributing_are_linked_to_current_project(self) -> None:
        roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("Coverage Curator 2", roadmap)
        self.assertIn("hyeonsangjeon/threejs-sculpt-dna", contributing)
        self.assertIn("visual evidence", contributing.lower())
        self.assertIn("Reference image policy", contributing)

    def test_issue_and_pull_request_templates_cover_public_workflows(self) -> None:
        templates = ROOT / ".github" / "ISSUE_TEMPLATE"
        for filename in (
            "bug_report.yml",
            "feature_request.yml",
            "reconstruction_request.yml",
            "config.yml",
        ):
            with self.subTest(filename=filename):
                self.assertTrue((templates / filename).exists())
        pull_request = (
            ROOT / ".github" / "pull_request_template.md"
        ).read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest discover -s tests -v", pull_request)
        self.assertIn("Preview variants are not described as production-ready", pull_request)


if __name__ == "__main__":
    unittest.main()
