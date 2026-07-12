from __future__ import annotations

import copy
import json
import shutil
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
    curate_variants,
    generate_variant,
    make_default_sculpt_dna,
    validate_sculpt_dna_block,
)
from generate_threejs_factory import generate  # noqa: E402
from migrate_review_policy import migrate_spec  # noqa: E402
from sculpt_dna import build_parser, variant_gate  # noqa: E402
from append_sculpt_review import load_json_argument  # noqa: E402
from sculpt_pass_orchestrator import (  # noqa: E402
    completed_passes,
    pass_order,
    sync_pipeline,
)
from validate_sculpt_spec import validate_spec, validate_visual_evidence_history  # noqa: E402
from visual_evidence_hashes import bind_visual_evidence_hashes, file_sha256  # noqa: E402


class SculptDNATests(unittest.TestCase):
    def make_dna_spec(self) -> dict:
        spec = make_spec("Test Artifact", "reference.png")
        spec["sculptDNA"] = make_default_sculpt_dna(spec)
        return spec

    def test_long_inline_review_json_is_not_treated_as_a_path(self) -> None:
        payload = [
            {
                "id": f"feature-{index}",
                "score": 0.8,
                "visible": True,
                "notes": "long inline review payload",
            }
            for index in range(12)
        ]
        encoded = json.dumps(payload)
        self.assertGreater(len(encoded), 255)
        self.assertEqual(
            load_json_argument(encoded, "--feature-reviews-json"),
            payload,
        )

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

    def test_production_gate_derives_completion_from_review_evidence(self) -> None:
        spec = self.make_dna_spec()
        spec["sculptPipeline"]["completedPasses"] = [
            "blockout",
            "structural-pass",
            "form-refinement",
            "material-pass",
            "surface-pass",
        ]
        with self.assertRaisesRegex(ValueError, "out of sync"):
            variant_gate(spec, False)
        completed, missing = variant_gate(spec, True)
        self.assertEqual(completed, [])
        self.assertEqual(
            missing,
            [
                "blockout",
                "structural-pass",
                "form-refinement",
                "material-pass",
                "surface-pass",
            ],
        )

    def test_production_gate_requires_existing_evidence_files(self) -> None:
        spec_path = ROOT / "examples" / "repolis-tree" / "object-sculpt-spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        completed, missing = variant_gate(spec, False, spec_path)
        self.assertEqual(missing, [])
        self.assertIn("surface-pass", completed)
        spec["reviewHistory"][0]["visualEvidence"]["renderScreenshot"] = (
            "examples/repolis-hero/evidence/does-not-exist.webp"
        )
        with self.assertRaisesRegex(
            ValueError,
            "out of sync|matching local visual evidence hashes",
        ):
            variant_gate(spec, False, spec_path)

    @staticmethod
    def remove_review_bindings(spec: dict) -> None:
        spec.pop("reviewPolicy", None)
        binding_fields = {
            "reviewId",
            "reviewedAt",
            "referenceSha256",
            "renderSha256",
            "comparisonSha256",
            "referenceBinding",
            "renderBinding",
            "comparisonBinding",
        }
        for item in spec.get("reviewHistory", []):
            visual = item.get("visualEvidence", {})
            for field in binding_fields:
                visual.pop(field, None)
        for visual in spec.get("visualEvidence", []):
            for field in binding_fields:
                visual.pop(field, None)

    def test_legacy_repolis_remains_valid_with_path_checks(self) -> None:
        spec_path = ROOT / "examples" / "repolis-tree" / "object-sculpt-spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        self.remove_review_bindings(spec)
        errors, warnings = validate_spec(spec, spec_path)
        self.assertEqual(errors, [])
        self.assertTrue(any("legacy path-existence" in item for item in warnings))
        self.assertEqual(
            completed_passes(spec, pass_order(spec), spec_path),
            pass_order(spec),
        )
        completed, missing = variant_gate(spec, False, spec_path)
        self.assertEqual(completed, pass_order(spec))
        self.assertEqual(missing, [])

    def test_older_stale_review_is_superseded_by_latest_bound_review(self) -> None:
        spec_path = ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        stale = copy.deepcopy(spec["reviewHistory"][0])
        stale["visualEvidence"]["renderSha256"] = "0" * 64
        spec["reviewHistory"].insert(0, stale)
        errors, _warnings = validate_spec(spec, spec_path)
        self.assertFalse(any("visual evidence binding failed" in item for item in errors))
        self.assertEqual(
            completed_passes(spec, pass_order(spec), spec_path),
            pass_order(spec),
        )
        variant_gate(spec, False, spec_path)

    def test_latest_stale_review_invalidates_every_production_gate(self) -> None:
        spec_path = ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        stale = copy.deepcopy(spec["reviewHistory"][0])
        stale["visualEvidence"]["renderSha256"] = "0" * 64
        spec["reviewHistory"].append(stale)
        errors, _warnings = validate_spec(spec, spec_path)
        self.assertTrue(any("visual evidence binding failed" in item for item in errors))
        self.assertEqual(completed_passes(spec, pass_order(spec), spec_path), [])
        sync_pipeline(spec, spec_path)
        self.assertEqual(spec["sculptPipeline"]["currentPass"], "blockout")
        with self.assertRaisesRegex(ValueError, "complete through surface-pass"):
            variant_gate(spec, False, spec_path)

    def test_hash_required_latest_review_rejects_missing_hashes(self) -> None:
        spec_path = ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        visual = spec["reviewHistory"][0]["visualEvidence"]
        visual.pop("renderSha256")
        errors, _warnings = validate_spec(spec, spec_path)
        self.assertTrue(any("renderSha256 is required" in item for item in errors))
        self.assertEqual(completed_passes(spec, pass_order(spec), spec_path), [])

    def test_review_policy_migration_backfills_legacy_repolis(self) -> None:
        spec_path = ROOT / "examples" / "repolis-tree" / "object-sculpt-spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        self.remove_review_bindings(spec)
        migrate_spec(spec, spec_path)
        self.assertEqual(spec["reviewPolicy"]["version"], 2)
        for review in spec["reviewHistory"]:
            visual = review.get("visualEvidence")
            if visual:
                self.assertEqual(len(visual["renderSha256"]), 64)
                self.assertEqual(len(visual["comparisonSha256"]), 64)
        errors, _warnings = validate_spec(spec, spec_path)
        self.assertEqual(errors, [])

    def test_append_review_hashes_all_local_visual_evidence(self) -> None:
        probe_dir = ROOT / "tests" / ".visual-evidence-hash-probe"
        try:
            probe_dir.mkdir(exist_ok=True)
            evidence_path = probe_dir / "evidence.bin"
            evidence_path.write_bytes(b"reviewed pixels")
            spec_path = probe_dir / "spec.json"
            spec_path.write_text(
                json.dumps(make_spec("Hash Probe", str(evidence_path)), indent=2)
                + "\n",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "append_sculpt_review.py"),
                    str(spec_path),
                    "--pass-id",
                    "blockout",
                    "--fidelity",
                    "0.5",
                    "--action",
                    "refine-code",
                    "--summary",
                    "Hash binding probe",
                    "--reference-screenshot",
                    str(evidence_path),
                    "--render-screenshot",
                    str(evidence_path),
                    "--comparison-image",
                    str(evidence_path),
                    "--in-place",
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            visual = json.loads(spec_path.read_text(encoding="utf-8"))[
                "reviewHistory"
            ][0]["visualEvidence"]
            expected = file_sha256(evidence_path)
            self.assertEqual(visual["referenceSha256"], expected)
            self.assertEqual(visual["renderSha256"], expected)
            self.assertEqual(visual["comparisonSha256"], expected)
            self.assertTrue(visual["reviewId"].startswith("blockout-review-"))
            self.assertEqual(
                visual["reviewedAt"],
                json.loads(spec_path.read_text(encoding="utf-8"))[
                    "reviewHistory"
                ][0]["timestamp"],
            )
        finally:
            shutil.rmtree(probe_dir, ignore_errors=True)

    def test_overwritten_evidence_invalidates_completion_and_production(self) -> None:
        source_path = ROOT / "examples" / "repolis-tree" / "object-sculpt-spec.json"
        spec = json.loads(source_path.read_text(encoding="utf-8"))
        probe_dir = ROOT / "tests" / ".visual-evidence-overwrite-probe"
        try:
            probe_dir.mkdir(exist_ok=True)
            evidence_path = probe_dir / "render.webp"
            original = (
                ROOT / spec["reviewHistory"][0]["visualEvidence"]["renderScreenshot"]
            )
            shutil.copyfile(original, evidence_path)
            visual = spec["reviewHistory"][0]["visualEvidence"]
            visual["renderScreenshot"] = str(evidence_path)
            bind_visual_evidence_hashes(visual, source_path)
            self.assertEqual(
                completed_passes(spec, pass_order(spec), source_path),
                pass_order(spec),
            )
            variant_gate(spec, False, source_path)

            evidence_path.write_bytes(evidence_path.read_bytes() + b"changed")
            self.assertEqual(
                completed_passes(spec, pass_order(spec), source_path),
                [],
            )
            sync_pipeline(spec, source_path)
            self.assertEqual(spec["sculptPipeline"]["completedPasses"], [])
            self.assertEqual(spec["sculptPipeline"]["currentPass"], "blockout")
            with self.assertRaisesRegex(
                ValueError,
                "complete through surface-pass",
            ):
                variant_gate(spec, False, source_path)
        finally:
            shutil.rmtree(probe_dir, ignore_errors=True)

    def test_remote_record_only_evidence_does_not_require_local_hashes(self) -> None:
        errors: list[str] = []
        validate_visual_evidence_history(
            {
                "visualEvidence": [
                    {
                        "passId": "blockout",
                        "referenceScreenshot": "https://example.com/reference.png",
                        "renderScreenshot": "session-artifact://render",
                        "comparisonImage": "https://example.com/comparison.png",
                        "referenceBinding": "remote-unverified",
                        "renderBinding": "remote-unverified",
                        "comparisonBinding": "remote-unverified",
                    }
                ]
            },
            errors,
        )
        self.assertEqual(errors, [])

    def test_notes_only_record_does_not_require_production_image_pair(self) -> None:
        errors: list[str] = []
        validate_visual_evidence_history(
            {
                "visualEvidence": [
                    {
                        "passId": "blockout",
                        "cameraView": "three-quarter",
                        "notes": "Capture pending; record-only observation.",
                    }
                ]
            },
            errors,
        )
        self.assertEqual(errors, [])

    def test_coverage_curator_is_deterministic_and_diverse(self) -> None:
        spec = self.make_dna_spec()
        first, first_report = curate_variants(spec, 42, 3, 16)
        second, second_report = curate_variants(spec, 42, 3, 16)
        self.assertEqual(first, second)
        self.assertEqual(first_report, second_report)
        self.assertEqual(len(first), 3)
        self.assertEqual(first_report["samplingMode"], "coverage-curated")
        self.assertEqual(len(set(first_report["selectedCandidateIndexes"])), 3)
        self.assertGreater(first_report["coverageScore"], 0)
        self.assertEqual(
            [item[1]["variantId"] for item in first],
            ["test-artifact-v001", "test-artifact-v002", "test-artifact-v003"],
        )
        self.assertTrue(
            all(item[1]["samplingMode"] == "coverage-curated" for item in first)
        )

    def test_curator_cli_defers_default_count_to_variant_policy(self) -> None:
        args = build_parser().parse_args(
            ["curate", "spec.json", "--out-dir", "variants"]
        )
        self.assertIsNone(args.count)

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
            blocked = subprocess.run(
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
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("complete through surface-pass", blocked.stderr)
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
                    "--preview",
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
            self.assertTrue(manifest["previewMode"])
            self.assertEqual(
                manifest["passGateStatus"],
                "pending-per-variant-visual-review",
            )
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

            curated_dir = root / "curated"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "sculpt_dna.py"),
                    "curate",
                    str(spec_path),
                    "--out-dir",
                    str(curated_dir),
                    "--count",
                    "3",
                    "--pool-size",
                    "12",
                    "--seed",
                    "17",
                    "--preview",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            curated_manifest = json.loads(
                (curated_dir / "sculpt-dna-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(curated_manifest["samplingMode"], "coverage-curated")
            self.assertEqual(curated_manifest["poolSize"], 12)
            self.assertEqual(curated_manifest["count"], 3)
            self.assertGreater(curated_manifest["coverageScore"], 0)
            self.assertTrue(curated_manifest["previewMode"])


if __name__ == "__main__":
    unittest.main()
