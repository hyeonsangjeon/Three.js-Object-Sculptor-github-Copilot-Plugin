from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from new_sculpt_spec import make_spec  # noqa: E402
from sculpt_dna_core import (  # noqa: E402
    constraint_failures,
    generate_variant,
    make_default_sculpt_dna,
    validate_sculpt_dna_block,
)
from generate_threejs_factory import generate  # noqa: E402


class SculptDNATests(unittest.TestCase):
    def make_dna_spec(self) -> dict:
        spec = make_spec("Test Artifact", "reference.png")
        spec["sculptDNA"] = make_default_sculpt_dna(spec)
        return spec

    def test_default_dna_is_valid_and_semantic(self) -> None:
        spec = self.make_dna_spec()
        errors, warnings = validate_sculpt_dna_block(spec)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        parameter_ids = {item["id"] for item in spec["sculptDNA"]["parameters"]}
        self.assertIn("base-roughness", parameter_ids)
        self.assertFalse(any(item.startswith("root-") for item in parameter_ids))

    def test_geometry_controls_require_empty_action_dependencies(self) -> None:
        spec = make_spec("Dependency Test", "reference.png")
        root = spec["componentTree"][0]
        root["actionProfile"]["pivot"] = {"localPosition": [0, 1, 0]}
        root["actionProfile"]["collider"] = {}
        dna = make_default_sculpt_dna(spec)
        self.assertFalse(any(item["id"].startswith("root-") for item in dna["parameters"]))

        root["actionProfile"]["pivot"] = {
            "mode": "center",
            "localPosition": [0, 0, 0],
        }
        root["actionProfile"]["collider"] = {"offset": [0, 0, 0]}
        dna = make_default_sculpt_dna(spec)
        self.assertFalse(any(item["id"].startswith("root-") for item in dna["parameters"]))

    def test_generation_is_deterministic_and_resets_evidence(self) -> None:
        spec = self.make_dna_spec()
        spec["reviewHistory"] = [{"passId": "blockout", "action": "continue"}]
        spec["visualEvidence"] = [{"passId": "blockout"}]
        spec["sculptPipeline"]["completedPasses"] = ["blockout"]
        first, first_provenance = generate_variant(spec, 42, 1)
        second, second_provenance = generate_variant(spec, 42, 1)
        self.assertEqual(first, second)
        self.assertEqual(first_provenance, second_provenance)
        self.assertEqual(first["reviewHistory"], [])
        self.assertEqual(first["visualEvidence"], [])
        self.assertEqual(first["sculptPipeline"]["currentPass"], "blockout")
        self.assertEqual(first["sculptPipeline"]["completedPasses"], [])
        self.assertTrue(first["variantProvenance"]["invariants"]["ok"])

    def test_immutable_semantic_target_is_rejected(self) -> None:
        spec = self.make_dna_spec()
        broken = copy.deepcopy(spec["sculptDNA"])
        broken["parameters"][0]["target"]["path"] = "id"
        errors, _ = validate_sculpt_dna_block(spec, broken)
        self.assertTrue(any("not mutable" in error for error in errors))

    def test_malformed_enum_values_return_errors(self) -> None:
        spec = self.make_dna_spec()
        broken = copy.deepcopy(spec["sculptDNA"])
        broken["parameters"][0]["target"]["kind"] = []
        broken["parameters"][0]["operation"] = {}
        broken["parameters"][0]["distribution"] = []
        broken["constraints"] = [{"id": "bad-constraint", "type": []}]
        errors, _ = validate_sculpt_dna_block(spec, broken)
        self.assertGreaterEqual(len(errors), 4)

    def test_generation_resamples_base_constraint_violation(self) -> None:
        spec = self.make_dna_spec()
        roughness_parameter = next(
            item
            for item in spec["sculptDNA"]["parameters"]
            if item["id"] == "base-roughness"
        )
        roughness_parameter["range"] = {"min": 0.6, "max": 0.7}
        spec["sculptDNA"]["constraints"] = [
            {
                "id": "base-roughness-window",
                "type": "range",
                "target": {
                    "kind": "material",
                    "id": "base",
                    "path": "roughness.base",
                },
                "min": 0.6,
                "max": 0.7,
            }
        ]
        _, warnings = validate_sculpt_dna_block(spec)
        self.assertTrue(any("violates Sculpt DNA constraint" in warning for warning in warnings))
        variant, _ = generate_variant(spec, 1, 1)
        self.assertEqual(
            constraint_failures(variant, spec["sculptDNA"]["constraints"]),
            [],
        )

    def test_impossible_numeric_constraints_are_rejected(self) -> None:
        spec = self.make_dna_spec()
        spec["sculptDNA"]["constraints"] = [
            {
                "id": "color-is-not-numeric",
                "type": "range",
                "target": {
                    "kind": "material",
                    "id": "base",
                    "path": "baseColor",
                },
                "min": 0,
                "max": 1,
            }
        ]
        errors, _ = validate_sculpt_dna_block(spec)
        self.assertTrue(any("must resolve to a number" in error for error in errors))

    def test_immutable_violated_constraint_is_rejected(self) -> None:
        spec = self.make_dna_spec()
        spec["sculptDNA"]["constraints"] = [
            {
                "id": "unreachable-width",
                "type": "range",
                "target": {
                    "kind": "component",
                    "id": "root",
                    "path": "dimensions.width",
                },
                "min": 2.0,
                "max": 3.0,
            }
        ]
        errors, _ = validate_sculpt_dna_block(spec)
        self.assertTrue(any("immutable Sculpt DNA constraint" in error for error in errors))

    def test_immutable_zero_ratio_denominator_is_rejected(self) -> None:
        spec = self.make_dna_spec()
        spec["sculptDNA"]["constraints"] = [
            {
                "id": "zero-metalness-ratio",
                "type": "ratio",
                "left": {
                    "kind": "material",
                    "id": "base",
                    "path": "roughness.base",
                },
                "right": {
                    "kind": "material",
                    "id": "base",
                    "path": "metalness.base",
                },
                "min": 1.0,
                "max": 2.0,
            }
        ]
        errors, _ = validate_sculpt_dna_block(spec)
        self.assertTrue(any("immutable zero denominator" in error for error in errors))

    def test_default_variant_count_matches_cli_limit(self) -> None:
        spec = self.make_dna_spec()
        spec["sculptDNA"]["variantPolicy"]["defaultCount"] = 101
        errors, _ = validate_sculpt_dna_block(spec)
        self.assertTrue(any("defaultCount must be <= 100" in error for error in errors))

    def test_non_sweep_attachment_preserves_declared_geometry(self) -> None:
        spec = make_spec("Attached Crown", "reference.png")
        spec["componentTree"].append(
            {
                "id": "crown",
                "name": "Crown",
                "level": "macro",
                "role": "crown",
                "primitive": "ellipsoid",
                "parent": "root",
                "attachment": {
                    "parentId": "root",
                    "parentSocket": "crown",
                    "localStart": [0, 0.5, 0],
                    "localEnd": [0, 2.5, 0],
                    "contactType": "overlap",
                    "overlap": 0.2,
                    "gapTolerance": 0.01,
                },
                "dimensions": {"width": 8.5, "height": 4.8, "depth": 3.2},
                "transform": {
                    "position": [0, 2.5, 0],
                    "rotation": [0, 0, 0],
                    "scale": [2, 2, 2],
                },
                "material": "base",
                "materialLayers": ["base"],
                "localFeatures": [],
                "evidenceRefs": ["full-object"],
                "fidelityTier": "blockout",
            }
        )
        factory = generate(spec, "blockout")
        self.assertIn("new THREE.SphereGeometry(0.5, 64, 40)", factory)
        self.assertIn("node_crown_1.scale.set(1, 1, 1)", factory)
        self.assertIn("mesh_crown_1.scale.set(17.0, 9.6, 6.4)", factory)

    def test_review_reset_cannot_be_disabled(self) -> None:
        spec = self.make_dna_spec()
        spec["sculptDNA"]["variantPolicy"]["resetReviewEvidence"] = False
        errors, _ = validate_sculpt_dna_block(spec)
        self.assertTrue(any("resetReviewEvidence=true" in error for error in errors))
        with self.assertRaises(ValueError):
            generate_variant(spec, 3, 1)

    def test_variant_id_is_path_safe(self) -> None:
        spec = self.make_dna_spec()
        spec["targetId"] = "../../outside"
        variant, provenance = generate_variant(spec, 7, 1)
        self.assertRegex(provenance["variantId"], r"^[a-z0-9-]+$")
        self.assertNotIn("..", provenance["variantId"])
        self.assertEqual(variant["targetId"], provenance["variantId"])

    def test_cli_round_trip_generates_manifest_and_factory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(make_spec("CLI Artifact", "reference.png"), indent=2) + "\n",
                encoding="utf-8",
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "sculpt_dna.py"), "init", str(spec_path), "--in-place"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "sculpt_dna.py"), "validate", str(spec_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_sculpt_spec.py"), str(spec_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            variants_dir = root / "variants"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "sculpt_dna.py"),
                    "generate",
                    str(spec_path),
                    "--out-dir",
                    str(variants_dir),
                    "--count",
                    "2",
                    "--seed",
                    "17",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            manifest = json.loads(
                (variants_dir / "sculpt-dna-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["count"], 2)
            self.assertEqual(manifest["sourceSpec"], "spec.json")
            self.assertEqual(len(manifest["sourceSpecSha256"]), 64)
            variant_path = variants_dir / manifest["variants"][0]["path"]
            factory_path = root / "createCliArtifactModel.ts"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "generate_threejs_factory.py"),
                    str(variant_path),
                    "--out",
                    str(factory_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            factory = factory_path.read_text(encoding="utf-8")
            self.assertIn("root.userData.sculptDNA", factory)
            self.assertIn("root.userData.variantProvenance", factory)
            self.assertIn("emissiveIntensity:", factory)
            self.assertIn(".scale.set(1.0, 1.0, 1.0)", factory)


if __name__ == "__main__":
    unittest.main()
