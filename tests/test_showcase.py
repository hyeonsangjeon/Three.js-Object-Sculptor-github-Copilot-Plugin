from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verify_release import (  # noqa: E402
    PRODUCTION_REVIEW_POLICY,
    verify_production_review_policy,
)


class ShowcaseTests(unittest.TestCase):
    def test_base_specs_and_variants_pass_strict_quality(self) -> None:
        base_specs = [
            ROOT / "examples" / "repolis-tree" / "object-sculpt-spec.json",
            ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json",
            ROOT / "examples" / "seoul-challenge" / "object-sculpt-spec.json",
        ]
        variant_specs = sorted((ROOT / "examples" / "showcase" / "variants").glob("*/*-v*.json"))
        self.assertEqual(len(variant_specs), 12)
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
        self.assertEqual(len(manifests), 4)
        for path in manifests:
            with self.subTest(path=path.relative_to(ROOT)):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                expected_seed = 20260712 if path.parent.name == "seoul-production" else 20260711
                self.assertEqual(manifest["rootSeed"], expected_seed)
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
                    "seoul-production": ROOT / "examples" / "seoul-challenge" / "object-sculpt-spec.json",
                }[family]
                if family == "seoul":
                    self.assertRegex(manifest["sourceSpecSha256"], r"^[0-9a-f]{64}$")
                else:
                    self.assertEqual(
                        manifest["sourceSpecSha256"],
                        sha256(base_spec.read_bytes()).hexdigest(),
                    )
                if family in {"tree", "brick", "seoul-production"}:
                    self.assertFalse(manifest["previewMode"])
                    expected_status = (
                        "evidence-backed-production"
                        if family in {"brick", "seoul-production"}
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

    def test_brick_production_review_policy_cannot_downgrade(self) -> None:
        variant_dir = ROOT / "examples" / "showcase" / "variants" / "brick"
        for spec_path in sorted(variant_dir.glob("brick-offroad-v*.json")):
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            self.assertEqual(spec["reviewPolicy"], PRODUCTION_REVIEW_POLICY)
            downgraded = deepcopy(spec)
            downgraded.pop("reviewPolicy")
            with self.assertRaisesRegex(ValueError, "reviewPolicy v2"):
                verify_production_review_policy(downgraded, spec_path)

    def test_showcase_review_covers_every_family(self) -> None:
        review_path = ROOT / "examples" / "showcase" / "showcase-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertEqual(
            review["reviewPolicy"]["staleCaptureBehavior"],
            "invalidate-scores",
        )
        self.assertEqual(
            {item["id"] for item in review["families"]},
            {"repolis-tree", "brick-offroad", "seoul-challenge"},
        )
        for family in review["families"]:
            self.assertTrue((ROOT / family["reference"]).exists())
            self.assertTrue((ROOT / family["render"]).exists())
            expected_status = (
                "evidence-backed-production"
                if family["id"] in {"brick-offroad", "seoul-challenge"}
                else "pending-per-variant-visual-review"
            )
            self.assertEqual(family["passGateStatus"], expected_status)
            if family["id"] in {"brick-offroad", "seoul-challenge"}:
                self.assertEqual(family["reviewStatus"], "accepted")
                self.assertTrue(family["reviewId"])
                self.assertTrue(family["reviewedAt"])
                for path_field, hash_field in (
                    ("reference", "referenceSha256"),
                    ("render", "renderSha256"),
                    ("comparison", "comparisonSha256"),
                ):
                    evidence_path = ROOT / family[path_field]
                    self.assertEqual(
                        family[hash_field],
                        sha256(evidence_path.read_bytes()).hexdigest(),
                    )
            manifest_dir = {
                "repolis-tree": "tree",
                "brick-offroad": "brick",
                "seoul-challenge": "seoul-production",
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

    def test_build_copies_runtime_variant_specs(self) -> None:
        source = (
            ROOT / "examples" / "showcase" / "vite.config.js"
        ).read_text(encoding="utf-8")
        self.assertIn("writeBundle(outputOptions)", source)
        self.assertIn(
            "variantFamilies = ['tree', 'brick', 'seoul-production']",
            source,
        )
        self.assertIn("{ recursive: true }", source)
        renderer = (
            ROOT / "examples" / "showcase" / "showcase.js"
        ).read_text(encoding="utf-8")
        self.assertIn("family: 'seoul-production'", renderer)
        self.assertIn("prefix: 'seoul-palace-hero'", renderer)
        self.assertIn("function mutationValue(", renderer)
        self.assertIn("'mountain-forest-balance'", renderer)
        self.assertIn("window.__SHOWCASE_VARIANT_IDS__", renderer)


if __name__ == "__main__":
    unittest.main()
