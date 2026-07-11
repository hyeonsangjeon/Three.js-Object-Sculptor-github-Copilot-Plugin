from __future__ import annotations

import json
from hashlib import sha256
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class ShowcaseTests(unittest.TestCase):
    def test_base_specs_and_variants_pass_strict_quality(self) -> None:
        base_specs = [
            ROOT / "examples" / "repolis-tree" / "object-sculpt-spec.json",
            ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json",
            ROOT / "examples" / "seoul-challenge" / "object-sculpt-spec.json",
        ]
        variant_specs = sorted((ROOT / "examples" / "showcase" / "variants").glob("*/*-v*.json"))
        self.assertEqual(len(variant_specs), 9)
        for path in [*base_specs, *variant_specs]:
            with self.subTest(path=path.relative_to(ROOT)):
                subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "validate_sculpt_spec.py"),
                        str(path),
                        "--strict-quality",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )

    def test_manifests_are_deterministic_three_variant_families(self) -> None:
        manifests = sorted(
            (ROOT / "examples" / "showcase" / "variants").glob("*/sculpt-dna-manifest.json")
        )
        self.assertEqual(len(manifests), 3)
        for path in manifests:
            with self.subTest(path=path.relative_to(ROOT)):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["rootSeed"], 20260711)
                self.assertEqual(manifest["count"], 3)
                self.assertEqual(len(manifest["variants"]), 3)
                self.assertEqual(manifest["samplingMode"], "coverage-curated")
                self.assertEqual(manifest["poolSize"], 24)
                self.assertGreater(manifest["coverageScore"], 0)
                self.assertEqual(len(set(manifest["selectedCandidateIndexes"])), 3)
                family = path.parent.name
                base_spec = {
                    "tree": ROOT / "examples" / "repolis-tree" / "object-sculpt-spec.json",
                    "brick": ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json",
                    "seoul": ROOT / "examples" / "seoul-challenge" / "object-sculpt-spec.json",
                }[family]
                self.assertEqual(
                    manifest["sourceSpecSha256"],
                    sha256(base_spec.read_bytes()).hexdigest(),
                )
                if family in {"tree", "brick"}:
                    self.assertFalse(manifest["previewMode"])
                    expected_status = (
                        "evidence-backed-production"
                        if family == "brick"
                        else "base-sculpt-gate-complete"
                    )
                    self.assertEqual(manifest["passGateStatus"], expected_status)
                    self.assertEqual(manifest["missingBasePasses"], [])
                else:
                    self.assertTrue(manifest["previewMode"])
                    self.assertEqual(
                        manifest["passGateStatus"],
                        "pending-per-variant-visual-review",
                    )
                self.assertTrue(
                    all(item["invariants"]["ok"] for item in manifest["variants"])
                )

    def test_showcase_review_covers_every_family(self) -> None:
        review_path = ROOT / "examples" / "showcase" / "showcase-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertEqual(
            {item["id"] for item in review["families"]},
            {"repolis-tree", "brick-offroad", "seoul-challenge"},
        )
        for family in review["families"]:
            self.assertTrue((ROOT / family["reference"]).exists())
            self.assertTrue((ROOT / family["render"]).exists())
            expected_status = (
                "evidence-backed-production"
                if family["id"] == "brick-offroad"
                else "pending-per-variant-visual-review"
            )
            self.assertEqual(family["passGateStatus"], expected_status)
            manifest_dir = {
                "repolis-tree": "tree",
                "brick-offroad": "brick",
                "seoul-challenge": "seoul",
            }[family["id"]]
            manifest = json.loads(
                (
                    ROOT
                    / "examples"
                    / "showcase"
                    / "variants"
                    / manifest_dir
                    / "sculpt-dna-manifest.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                family["coverageCurator"]["coverageScore"],
                manifest["coverageScore"],
            )

    def test_local_server_is_loopback_and_showcase_scoped(self) -> None:
        package = json.loads(
            (ROOT / "examples" / "showcase" / "package.json").read_text(encoding="utf-8")
        )
        command = package["scripts"]["serve"]
        self.assertIn("--bind 127.0.0.1", command)
        self.assertIn("--directory .", command)
        self.assertNotIn("../..", command)

    def test_renderer_randomness_uses_stable_variant_identity(self) -> None:
        source = (
            ROOT / "examples" / "showcase" / "showcase.js"
        ).read_text(encoding="utf-8")
        self.assertIn("stableVariantSeed(spec", source)
        self.assertNotIn("8100 + index * 97", source)
        self.assertNotIn("4420 + index * 211", source)


if __name__ == "__main__":
    unittest.main()
