from __future__ import annotations

from copy import deepcopy
import json
from hashlib import sha256
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_release as release_verifier  # noqa: E402
from verify_release import (  # noqa: E402
    PRODUCTION_REVIEW_POLICY,
    SEOUL_GIF_SHA256,
    SEOUL_HERO_SHA256,
    SEOUL_INTERMEDIATE_SHA256,
    SEOUL_PRODUCTION_VARIANTS,
    SEOUL_RUNTIME_SEED_DERIVATION,
    action_ready_contract,
    collider_contract,
    deterministic_variant_seed,
    load as load_release_json,
    repository_file,
    runtime_seed_from_variant_seed,
    verify_complete_latest_review_pipeline,
    verify_exact_artifact_outputs,
    verify_exact_artifact_sources,
    verify_no_absolute_evidence_paths,
    verify_performance_probe,
    verify_production_review_policy,
    verify_repository_relative_paths,
    verify_seoul_visual_acceptance,
)
from validate_sculpt_spec import load_spec, validate_spec  # noqa: E402


HERO = ROOT / "examples" / "seoul-palace-hero"
SPEC = ROOT / "examples" / "seoul-challenge" / "object-sculpt-spec.json"
VARIANTS = ROOT / "examples" / "showcase" / "variants" / "seoul-production"
PASS_ORDER = [
    "blockout",
    "structural-pass",
    "form-refinement",
    "material-pass",
    "surface-pass",
    "lighting-pass",
    "interaction-pass",
    "optimization-pass",
]
CANONICAL_SOURCE_FILES = [
    "../seoul-challenge/assessment.json",
    "../seoul-challenge/object-sculpt-spec.json",
    "../showcase/variants/seoul-production/sculpt-dna-manifest.json",
    "../showcase/variants/seoul-production/seoul-palace-hero-v001.json",
    "../showcase/variants/seoul-production/seoul-palace-hero-v002.json",
    "../showcase/variants/seoul-production/seoul-palace-hero-v003.json",
    "../../assets/seoul-challenge-reference.jpeg",
    "../../scripts/make_visual_comparison_sheet.py",
    "index.html",
    "main.js",
    "package-lock.json",
    "package.json",
    "scripts/capture-isolation.test.mjs",
    "scripts/capture.mjs",
    "scripts/factory-contract.test.mjs",
    "style.css",
    "vite.config.js",
    "seoul-output/createSeoulPalaceHero.d.ts",
    "seoul-output/createSeoulPalaceHero.js",
    "seoul-output/createProceduralMaterials.js",
    "seoul-output/seoul-palace-profile.json",
    "seoul-output/seoul-variant-config.json",
]
RUNTIME_SOURCE_FILES = [
    "index.html",
    "main.js",
    "package-lock.json",
    "package.json",
    "style.css",
    "vite.config.js",
    "seoul-output/createSeoulPalaceHero.js",
    "seoul-output/createProceduralMaterials.js",
    "seoul-output/seoul-variant-config.json",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class SeoulPalaceHeroTests(unittest.TestCase):
    def test_factory_is_code_native_action_ready_and_layered(self) -> None:
        source = (HERO / "seoul-output" / "createSeoulPalaceHero.js").read_text(
            encoding="utf-8"
        )
        for forbidden in ("GLTFLoader", "FBXLoader", "OBJLoader", ".glb", ".gltf"):
            self.assertNotIn(forbidden, source)
        for required in (
            "createRoofSurfaceGeometry",
            "createRoofRidgeGeometry",
            "createRidgeTerrainGeometry",
            "THREE.InstancedMesh",
            "root.userData.sculptRuntime",
            "root.userData.sculptDNA",
            "root.userData.variantProvenance",
            "ReferenceCamera",
            "MountainLookout",
            "setLayerLens",
            "setGateOpen",
            "protectedArchitecture: true",
            "importedMeshes: 0",
        ):
            self.assertIn(required, source)

    def test_render_stats_are_sampled_on_demand(self) -> None:
        source = (HERO / "main.js").read_text(encoding="utf-8")
        self.assertIn("function getRenderInfo()", source)
        self.assertNotIn("window.__SEOUL_RENDER_STATS__ = {", source)

    def test_manifest_and_runtime_profile_meet_budgets(self) -> None:
        manifest = load(HERO / "artifact-manifest.json")
        profile = load(HERO / "seoul-output" / "seoul-palace-profile.json")
        stats = manifest["runtimeStats"]
        budgets = profile["performance"]["budgets"]
        self.assertLessEqual(
            stats["triangles"], budgets["instanceWeightedTriangles"]
        )
        self.assertLessEqual(stats["sceneDrawables"], budgets["sceneDrawables"])
        self.assertLessEqual(stats["renderCalls"], budgets["fullFrameWebglCalls"])
        self.assertEqual(stats["importedMeshes"], 0)
        self.assertEqual(stats["sockets"], 14)
        self.assertEqual(stats["colliders"], 27)
        self.assertEqual(
            profile["actionReadiness"]["colliders"],
            stats["colliders"],
        )
        self.assertEqual(stats["generatedTextureCount"], 35)
        self.assertTrue(manifest["capture"]["deterministicRepeatedCapture"])
        self.assertEqual(
            {stats["variantId"] for stats in manifest["variantRuntimeStats"]},
            {
                "seoul-palace-hero-v001",
                "seoul-palace-hero-v002",
                "seoul-palace-hero-v003",
            },
        )
        self.assertEqual(
            manifest["capture"]["repeatedCanonicalSha256"],
            manifest["outputSha256"]["../../assets/seoul-palace-hero.png"],
        )
        self.assertEqual(
            manifest["capture"]["animation"]["reducedMotion"],
            "no-preference",
        )
        self.assertGreaterEqual(
            manifest["capture"]["animation"]["uniqueFrameCount"],
            2,
        )
        colliders = manifest["colliderSnapshot"]
        self.assertSetEqual(
            set(colliders),
            set(manifest["runtimeSnapshot"]["colliderIds"]),
        )
        self.assertNotIn("outer-gate-collider", colliders)
        self.assertNotIn("inner-gate-collider", colliders)
        for gate in ("outer-gate", "inner-gate"):
            for side in ("west", "east"):
                leaf_id = f"{gate}-{side}-leaf-collider"
                self.assertEqual(
                    colliders[leaf_id]["parentNodeId"],
                    f"{gate}-{side}-leaf-pivot",
                )
                self.assertIn(f"{gate}-{side}-pier-collider", colliders)
        self.assertEqual(
            colliders["foreground-collider"],
            {
                "parentId": "foreground-ground",
                "parentNodeId": "foreground",
                "center": [0, -0.18, -28],
                "size": [90, 0.35, 34],
            },
        )
        contract = action_ready_contract(load(SPEC))
        self.assertEqual(len(contract["components"]), 33)
        self.assertEqual(len(contract["sockets"]), 14)
        self.assertEqual(len(contract["colliders"]), 27)
        self.assertSetEqual(
            set(manifest["runtimeSnapshot"]["semanticNodeAliases"]),
            set(contract["components"]),
        )
        self.assertTrue(
            set(contract["components"]).issubset(
                manifest["runtimeSnapshot"]["nodeIds"]
            )
        )
        self.assertSetEqual(
            set(manifest["socketSnapshot"]),
            set(contract["sockets"]),
        )
        for socket_id, expected in contract["sockets"].items():
            actual = manifest["socketSnapshot"][socket_id]
            self.assertEqual(actual["parentNodeId"], expected["parentNodeId"])
            self.assertEqual(
                actual["declaredParentNodeId"],
                expected["parentNodeId"],
            )
            self.assertEqual(actual["position"], expected["localPosition"])
            self.assertEqual(actual["rotation"], expected["localRotation"])
        self.assertSetEqual(set(collider_contract(load(SPEC))), set(colliders))
        for variant_path in VARIANTS.glob("seoul-palace-hero-v*.json"):
            self.assertEqual(
                action_ready_contract(load(variant_path)),
                contract,
            )

    def test_curated_variant_controls_match_sculpt_dna_mutations(self) -> None:
        config = load(HERO / "seoul-output" / "seoul-variant-config.json")
        manifest = load(VARIANTS / "sculpt-dna-manifest.json")
        fields = {
            "roof-weathering": "roofRoughness",
            "roof-accent-palette": "roofAccent",
            "courtyard-roughness": "courtyardRoughness",
            "courtyard-tone": "courtyardTone",
            "tree-belt-density": "treeDensity",
            "city-belt-density": "cityDensity",
            "mountain-forest-balance": "mountainForestDensity",
            "mountain-rock-balance": "mountainRockDensity",
        }
        self.assertEqual(manifest["poolSize"], 24)
        self.assertEqual(manifest["count"], 3)
        self.assertEqual(len(manifest["variants"]), 3)
        self.assertEqual(len(config["variants"]), 3)
        expected_ids = {
            f"seoul-palace-hero-v00{index}" for index in range(1, 4)
        }
        self.assertSetEqual(
            {variant["variantId"] for variant in manifest["variants"]},
            expected_ids,
        )
        self.assertSetEqual(
            {variant["id"] for variant in config["variants"]},
            expected_ids,
        )
        self.assertSetEqual(
            {path.name for path in VARIANTS.glob("seoul-palace-hero-v*.json")},
            {f"{variant_id}.json" for variant_id in expected_ids},
        )
        for runtime, variant in zip(config["variants"], manifest["variants"]):
            pinned = SEOUL_PRODUCTION_VARIANTS[variant["variantId"]]
            self.assertEqual(runtime["id"], variant["variantId"])
            self.assertLessEqual(runtime["seed"], 0xFFFFFFFF)
            self.assertIsInstance(variant["variantSeed"], str)
            self.assertEqual(
                variant["variantSeed"],
                deterministic_variant_seed(
                    manifest["rootSeed"],
                    variant["candidateIndex"],
                    variant["attempt"] - 1,
                ),
            )
            self.assertEqual(
                runtime["provenance"]["sourceVariantSeed"],
                variant["variantSeed"],
            )
            self.assertEqual(
                runtime["seed"],
                runtime_seed_from_variant_seed(variant["variantSeed"]),
            )
            self.assertEqual(variant["candidateIndex"], pinned["candidateIndex"])
            self.assertEqual(variant["variantSeed"], pinned["sourceSeed"])
            self.assertEqual(runtime["seed"], pinned["runtimeSeed"])
            self.assertEqual(
                runtime["provenance"]["runtimeSeedDerivation"],
                SEOUL_RUNTIME_SEED_DERIVATION,
            )
            variant_spec = load(VARIANTS / variant["path"])
            self.assertEqual(
                variant_spec["variantProvenance"]["variantSeed"],
                variant["variantSeed"],
            )
            for mutation in variant["mutations"]:
                self.assertEqual(
                    runtime[fields[mutation["parameterId"]]], mutation["after"]
                )
            self.assertTrue(variant["invariants"]["ok"])

    def test_exact_runtime_seed_projection_rejects_ambiguous_values(self) -> None:
        self.assertEqual(
            runtime_seed_from_variant_seed("1996682606581385420"),
            1987840204,
        )
        for invalid in (
            1996682606581385420,
            "",
            "-1",
            "01996682606581385420",
            "１９９６６８２６０６５８１３８５４２０",
        ):
            with self.subTest(seed=invalid):
                with self.assertRaisesRegex(
                    ValueError,
                    "canonical unsigned decimal string",
                ):
                    runtime_seed_from_variant_seed(invalid)

    def test_action_contract_rejects_duplicate_or_stale_entries(self) -> None:
        spec = load(SPEC)
        duplicate_socket = deepcopy(spec)
        duplicate_socket["componentTree"][0]["actionProfile"]["sockets"].append(
            deepcopy(
                duplicate_socket["componentTree"][0]["actionProfile"][
                    "sockets"
                ][0]
            )
        )
        with self.assertRaisesRegex(ValueError, "socket contract is invalid"):
            action_ready_contract(duplicate_socket)

        stale_collider = deepcopy(spec)
        stale_collider["componentTree"][0]["actionProfile"]["collider"] = {
            "type": "box",
            "isTrigger": False,
            "offset": [0, 0, 0],
            "scale": [1, 1, 1],
        }
        with self.assertRaisesRegex(ValueError, "collider contract is stale"):
            action_ready_contract(stale_collider)

        cyclic = deepcopy(spec)
        components = {
            component["id"]: component
            for component in cyclic["componentTree"]
        }
        components["foreground-system"]["parent"] = "palace-axis-system"
        components["palace-axis-system"]["parent"] = "foreground-system"
        with self.assertRaisesRegex(ValueError, "contains a cycle"):
            action_ready_contract(cyclic)

    def test_validator_rejects_non_finite_or_boolean_vectors(self) -> None:
        spec = load(SPEC)
        invalid = deepcopy(spec)
        collider = next(
            component["actionProfile"]["collider"]
            for component in invalid["componentTree"]
            if component["actionProfile"]["collider"].get("parts")
        )
        collider["parts"][0]["offset"][0] = True
        collider["parts"][0]["scale"][0] = float("nan")
        errors, _ = validate_spec(invalid, SPEC)
        self.assertTrue(
            any("offset must be" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("scale must be" in error for error in errors),
            errors,
        )

        nonstandard_json = ROOT / "tests" / ".nonstandard-spec.json"
        try:
            nonstandard_json.write_text('{"value": Infinity}\n', encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                "non-standard JSON constant Infinity",
            ):
                load_spec(nonstandard_json)
        finally:
            nonstandard_json.unlink(missing_ok=True)

    def test_each_variant_has_fresh_sha_bound_acceptance(self) -> None:
        for spec_path in sorted(VARIANTS.glob("seoul-palace-hero-v*.json")):
            variant = load(spec_path)
            acceptance = variant["variantProvenance"]["visualAcceptance"]
            verify_seoul_visual_acceptance(variant, acceptance, spec_path.name)
            self.assertGreaterEqual(acceptance["aiVisionScore"], 0.86)
            self.assertIn("fresh-review", acceptance["reviewId"])
            for feature in acceptance["featureReviews"]:
                self.assertTrue(feature["visible"])
                self.assertGreaterEqual(feature["score"], 0.86)
            self.assertSetEqual(
                {feature["id"] for feature in acceptance["featureReviews"]},
                {
                    "palace-axial-hierarchy",
                    "korean-roof-system",
                    "ceremonial-negative-space",
                    "atmospheric-depth-layers",
                    "asymmetric-mountain-composition",
                },
            )
            for path_field, hash_field in (
                ("referenceScreenshot", "referenceSha256"),
                ("renderScreenshot", "renderSha256"),
                ("comparisonImage", "comparisonSha256"),
            ):
                evidence = ROOT / acceptance[path_field]
                self.assertEqual(digest(evidence), acceptance[hash_field])

    def test_seoul_visual_gate_rejects_score_downgrades(self) -> None:
        variant = load(VARIANTS / "seoul-palace-hero-v001.json")
        mutations = {
            "declared threshold": lambda item: item["selfCorrectLoop"][
                "visualAcceptance"
            ].update(threshold=0.85),
            "accepted threshold": lambda item: item["variantProvenance"][
                "visualAcceptance"
            ].update(visualAcceptanceThreshold=0.85),
            "overall score": lambda item: item["variantProvenance"][
                "visualAcceptance"
            ].update(aiVisionScore=0.85),
            "layer score": lambda item: item["variantProvenance"][
                "visualAcceptance"
            ]["layerScores"].update(materialSurface=0.85),
            "critical score": lambda item: item["variantProvenance"][
                "visualAcceptance"
            ]["featureReviews"][0].update(score=0.85),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                downgraded = deepcopy(variant)
                mutate(downgraded)
                with self.assertRaisesRegex(ValueError, "0.86"):
                    verify_seoul_visual_acceptance(
                        downgraded,
                        downgraded["variantProvenance"]["visualAcceptance"],
                        label,
                    )

    def test_seoul_base_visual_gate_rejects_score_downgrades(self) -> None:
        base = load(SPEC)

        def acceptance(item: dict) -> dict:
            return next(
                review
                for review in reversed(item["reviewHistory"])
                if review["passId"] == "optimization-pass"
            )

        mutations = {
            "declared threshold": lambda item: item["selfCorrectLoop"][
                "visualAcceptance"
            ].update(threshold=0.85),
            "accepted threshold": lambda item: acceptance(item).update(
                visualAcceptanceThreshold=0.85
            ),
            "overall score": lambda item: acceptance(item).update(
                aiVisionScore=0.85
            ),
            "layer score": lambda item: acceptance(item)[
                "layerScores"
            ].update(materialSurface=0.85),
            "critical score": lambda item: acceptance(item)[
                "featureReviews"
            ][0].update(score=0.85),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                downgraded = deepcopy(base)
                mutate(downgraded)
                with self.assertRaisesRegex(ValueError, "0.86"):
                    verify_seoul_visual_acceptance(
                        downgraded,
                        acceptance(downgraded),
                        label,
                    )

    def test_seoul_release_gate_applies_exact_base_threshold(self) -> None:
        def downgraded_load(path: Path) -> dict:
            value = load_release_json(path)
            if Path(path).resolve() == SPEC.resolve():
                value["selfCorrectLoop"]["visualAcceptance"]["threshold"] = 0.85
            return value

        with patch.object(
            release_verifier,
            "load",
            side_effect=downgraded_load,
        ):
            with self.assertRaisesRegex(ValueError, "0.86"):
                release_verifier.verify_seoul_variants()

    def test_seoul_showcase_rejects_layer_score_downgrade(self) -> None:
        review = load(
            ROOT / "examples" / "showcase" / "showcase-review.json"
        )
        seoul = next(
            family
            for family in review["families"]
            if family["id"] == "seoul-challenge"
        )
        seoul["scores"]["materialSurface"] = 0.85
        with patch.object(release_verifier, "load", return_value=review):
            with self.assertRaisesRegex(ValueError, "0.86"):
                release_verifier.verify_showcase_review()

    def test_each_variant_completes_every_evidence_backed_pass(self) -> None:
        runtime = {
            variant["id"]: variant
            for variant in load(
                HERO / "seoul-output" / "seoul-variant-config.json"
            )["variants"]
        }
        for spec_path in sorted(VARIANTS.glob("seoul-palace-hero-v*.json")):
            spec = load(spec_path)
            provenance = spec["variantProvenance"]
            pipeline = spec["sculptPipeline"]
            reviews = {
                review["passId"]: review for review in spec["reviewHistory"]
            }
            self.assertEqual(pipeline["currentPass"], "complete")
            self.assertEqual(pipeline["passOrder"], PASS_ORDER)
            self.assertEqual(pipeline["completedPasses"], PASS_ORDER)
            self.assertEqual(set(reviews), set(PASS_ORDER))
            self.assertTrue(
                all(review["action"] == "continue" for review in reviews.values())
            )
            self.assertTrue(
                all(review["visualEvidence"] for review in reviews.values())
            )
            self.assertEqual(
                provenance["passGateStatus"], "evidence-backed-production"
            )
            self.assertTrue(provenance["reviewEvidenceRenewed"])
            self.assertEqual(
                runtime[provenance["variantId"]]["provenance"]["passGateStatus"],
                "evidence-backed-production",
            )

    def test_production_variant_review_policy_cannot_downgrade(self) -> None:
        base = load(SPEC)
        self.assertEqual(base["reviewPolicy"], PRODUCTION_REVIEW_POLICY)
        downgraded_base = deepcopy(base)
        downgraded_base.pop("reviewPolicy")
        with self.assertRaisesRegex(ValueError, "reviewPolicy v2"):
            verify_production_review_policy(downgraded_base, SPEC)

        for spec_path in sorted(VARIANTS.glob("seoul-palace-hero-v*.json")):
            spec = load(spec_path)
            self.assertEqual(spec["reviewPolicy"], PRODUCTION_REVIEW_POLICY)
            downgraded = deepcopy(spec)
            downgraded.pop("reviewPolicy")
            with self.assertRaisesRegex(ValueError, "reviewPolicy v2"):
                verify_production_review_policy(downgraded, spec_path)
            revoked = deepcopy(spec)
            revoked["reviewHistory"].append(
                {
                    **deepcopy(revoked["reviewHistory"][0]),
                    "action": "refine-code",
                }
            )
            with self.assertRaisesRegex(
                ValueError,
                "latest evidence-backed pass",
            ):
                verify_complete_latest_review_pipeline(revoked, spec_path)

    def test_malformed_variant_query_normalizes_to_base(self) -> None:
        runtime = (HERO / "main.js").read_text(encoding="utf-8")
        self.assertIn("const parsedVariant = Number.parseInt", runtime)
        self.assertIn("parsedVariant <= variantConfig.variants.length", runtime)
        self.assertIn("? parsedVariant\n  : 0;", runtime)

    def test_variant_performance_evidence_is_current_and_sha_bound(self) -> None:
        metrics_path = HERO / "evidence" / "variant-runtime-metrics.json"
        metrics = load(metrics_path)
        self.assertEqual(metrics["schemaVersion"], "2.0")
        self.assertEqual(
            metrics["sourceBinding"]["mode"],
            "runtime-fingerprint-v1",
        )
        manifest = load(HERO / "artifact-manifest.json")
        self.assertEqual(
            metrics["runtimeFingerprint"],
            manifest["runtimeFingerprint"],
        )
        self.assertEqual(len(metrics["variants"]), 3)
        for item in metrics["variants"]:
            self.assertTrue(item["allRunsPass"])
            self.assertEqual(len(item["runs"]), 3)
            self.assertTrue(
                all(run["frameCount"] == 600 for run in item["runs"])
            )
            self.assertGreaterEqual(item["aggregate"]["meanFps"], 58.5)
            self.assertLessEqual(item["aggregate"]["p50FrameMs"], 16.9)
            self.assertLessEqual(item["aggregate"]["p95FrameMs"], 22)
            self.assertEqual(item["aggregate"]["droppedFrameCount"], 0)
            spec = load(VARIANTS / f'{item["variantId"]}.json')
            optimization = {
                review["passId"]: review for review in spec["reviewHistory"]
            }["optimization-pass"]
            supplemental = {
                evidence["path"]: evidence["sha256"]
                for evidence in optimization["visualEvidence"][
                    "supplementalEvidence"
                ]
            }
            self.assertEqual(
                supplemental[
                    "examples/seoul-palace-hero/evidence/"
                    "variant-runtime-metrics.json"
                ],
                digest(metrics_path),
            )

    def test_performance_reconciliation_meets_declared_gate(self) -> None:
        metrics = load(HERO / "evidence" / "optimization-metrics.json")
        probe = metrics["performanceProbe"]
        manifest = load(HERO / "artifact-manifest.json")
        self.assertEqual(len(probe["runs"]), 3)
        self.assertTrue(all(run["frameCount"] == 600 for run in probe["runs"]))
        self.assertEqual(probe["aggregate"]["frameCount"], 1800)
        self.assertEqual(
            probe["runtimeFingerprint"],
            manifest["runtimeFingerprint"],
        )
        self.assertEqual(metrics["runtime"]["hero"]["variantId"], "seoul-palace-hero-base")
        self.assertEqual(
            metrics["runtime"]["render"]["runtimeFingerprint"],
            manifest["runtimeFingerprint"],
        )
        self.assertEqual(metrics["runtime"]["runtime"], manifest["runtimeSnapshot"])
        self.assertIn(
            "frustum-culling-and-linear-texture-minification",
            metrics["runtime"]["runtime"]["optimization"]["strategies"],
        )
        self.assertRegex(probe["rawArtifactSummarySha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(probe["rawRuntimeSnapshotSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(probe["aggregate"]["droppedFrameCount"], 0)
        for run in probe["runs"]:
            self.assertGreaterEqual(run["meanFps"], 58.5)
            self.assertLessEqual(run["p50FrameMs"], 16.9)
            self.assertLessEqual(run["p95FrameMs"], 22)
            self.assertEqual(run["droppedFrameCount"], 0)
            self.assertEqual(run["longTaskCount"], 0)
        self.assertEqual(
            probe["stableRuntime"],
            {
                "fullFrameWebglCalls": 388,
                "renderedTriangles": 288944,
                "instanceWeightedTriangles": 144472,
                "sceneDrawables": 194,
                "instances": 2275,
                "colliders": 27,
                "geometries": 187,
                "textures": 29,
                "consoleErrors": 0,
                "networkErrors": 0,
            },
        )
        latest = {
            review["passId"]: review for review in load(SPEC)["reviewHistory"]
        }["optimization-pass"]
        self.assertEqual(latest["action"], "continue")
        self.assertIn(
            "optimization-pass-canonical-release-",
            latest["visualEvidence"]["reviewId"],
        )
        self.assertEqual(
            latest["visualEvidence"]["renderSha256"],
            SEOUL_HERO_SHA256,
        )
        runtime_fingerprint = load(HERO / "artifact-manifest.json")[
            "runtimeFingerprint"
        ]
        stale = deepcopy(probe)
        stale["runtimeFingerprint"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "stale or below gate"):
            verify_performance_probe(
                stale,
                runtime_fingerprint,
                "stale base",
                variant=False,
            )
        non_finite = deepcopy(probe)
        non_finite["aggregate"]["meanFps"] = float("nan")
        with self.assertRaisesRegex(ValueError, "non-finite metrics"):
            verify_performance_probe(
                non_finite,
                runtime_fingerprint,
                "non-finite base",
                variant=False,
            )
        boolean_count = deepcopy(probe)
        boolean_count["runs"][0]["droppedFrameCount"] = False
        with self.assertRaisesRegex(ValueError, "non-finite metrics"):
            verify_performance_probe(
                boolean_count,
                runtime_fingerprint,
                "boolean base",
                variant=False,
            )
        nonstandard_json = ROOT / "tests" / ".nonstandard-performance.json"
        try:
            nonstandard_json.write_text('{"meanFps": NaN}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-standard JSON constant"):
                load_release_json(nonstandard_json)
        finally:
            nonstandard_json.unlink(missing_ok=True)
        wrong_frame_count = deepcopy(probe)
        wrong_frame_count["conditions"]["measuredFramesPerRun"] = 599
        with self.assertRaisesRegex(ValueError, "stale or below gate"):
            verify_performance_probe(
                wrong_frame_count,
                runtime_fingerprint,
                "short base",
                variant=False,
            )

    def test_accessibility_and_lifecycle_controls_are_wired(self) -> None:
        markup = (HERO / "index.html").read_text(encoding="utf-8")
        runtime = (HERO / "main.js").read_text(encoding="utf-8")
        styles = (HERO / "style.css").read_text(encoding="utf-8")
        for expected in (
            'tabindex="0"',
            'role="region"',
            'aria-describedby="interaction-hint"',
            'aria-live="polite"',
        ):
            self.assertIn(expected, markup)
        for expected in (
            "function moveCameraFromKeyboard(key)",
            "sceneContainer.addEventListener('keydown'",
            "function disposeScene(event)",
            "window.addEventListener('pagehide'",
            "loadingStatus.hidden = true",
            "controls.addEventListener('change', requestRenderLoop)",
            "autoDrift || tourActive || controlsChanged",
        ):
            self.assertIn(expected, runtime)
        self.assertIn("#scene:focus-visible", styles)
        self.assertIn("background: #1e3228", styles)
        self.assertIn("color: #f2f4ed", styles)

    def test_three_route_pagers_and_pages_workflow_are_wired(self) -> None:
        expected = {
            ROOT / "examples" / "repolis-hero" / "index.html": "01/03",
            ROOT / "examples" / "brick-offroad-hero" / "index.html": "02/03",
            HERO / "index.html": "03/03",
        }
        for path, marker in expected.items():
            content = path.read_text(encoding="utf-8")
            self.assertIn(marker, content)
            self.assertIn('data-flagship="', content)
        workflow = (
            ROOT / ".github" / "workflows" / "deploy-repolis-hero.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("examples/seoul-palace-hero/package-lock.json", workflow)
        self.assertIn("${{ runner.temp }}/threejs-sculpt-dna-pages", workflow)
        self.assertIn('test ! -e "$PAGES_DIR"', workflow)
        self.assertIn("npm run test:capture", workflow)
        self.assertIn('- "assets/**"', workflow)

    def test_artifact_manifest_hashes_are_current(self) -> None:
        manifest = load(HERO / "artifact-manifest.json")
        self.assertEqual(
            list(manifest["sourceSha256"]),
            CANONICAL_SOURCE_FILES,
        )
        self.assertEqual(manifest["runtimeFiles"], RUNTIME_SOURCE_FILES)
        self.assertEqual(
            list(manifest["runtimeSha256"]),
            RUNTIME_SOURCE_FILES,
        )
        for section in ("sourceSha256", "outputSha256"):
            for relative, expected in manifest[section].items():
                self.assertEqual(digest((HERO / relative).resolve()), expected)
        self.assertEqual(
            manifest["outputSha256"]["../../assets/seoul-palace-hero.png"],
            SEOUL_HERO_SHA256,
        )
        self.assertEqual(
            manifest["outputSha256"]["../../assets/seoul-palace-hero.gif"],
            SEOUL_GIF_SHA256,
        )
        verify_exact_artifact_outputs(
            "seoul-palace-hero", manifest["outputSha256"]
        )
        unexpected = {**manifest["outputSha256"], "evidence/extra.png": "0" * 64}
        with self.assertRaisesRegex(ValueError, "exact canonical outputs"):
            verify_exact_artifact_outputs("seoul-palace-hero", unexpected)
        for hero_name in (
            "repolis-hero",
            "brick-offroad-hero",
            "seoul-palace-hero",
        ):
            source_hashes = load(
                ROOT / "examples" / hero_name / "artifact-manifest.json"
            )["sourceSha256"]
            verify_exact_artifact_sources(hero_name, source_hashes)
            missing = dict(list(source_hashes.items())[1:])
            with self.assertRaisesRegex(
                ValueError,
                "exact canonical source inputs",
            ):
                verify_exact_artifact_sources(hero_name, missing)

    def test_base_reviews_are_production_only_and_sha_bound(self) -> None:
        spec = load(SPEC)
        self.assertEqual(
            spec["sculptPipeline"]["passOrder"][:3],
            ["blockout", "structural-pass", "form-refinement"],
        )
        self.assertEqual(
            spec["sculptPipeline"]["completedPasses"][:2],
            ["blockout", "structural-pass"],
        )
        reviews = {
            review["passId"]: review for review in spec["reviewHistory"]
        }
        evidence_passes = {
            review["passId"] for review in spec["visualEvidence"]
        }
        self.assertSetEqual(evidence_passes, set(reviews))
        for pass_id in ("blockout", "structural-pass"):
            visual = reviews[pass_id]["visualEvidence"]
            self.assertNotIn("preview", visual["reviewId"])
            self.assertEqual(
                visual["referenceScreenshot"],
                "assets/seoul-challenge-reference.jpeg",
            )
            self.assertTrue(
                visual["renderScreenshot"].startswith(
                    "examples/seoul-palace-hero/evidence/"
                )
            )
            self.assertTrue(
                visual["comparisonImage"].startswith(
                    "examples/seoul-palace-hero/evidence/"
                )
            )
            for path_field, hash_field in (
                ("referenceScreenshot", "referenceSha256"),
                ("renderScreenshot", "renderSha256"),
                ("comparisonImage", "comparisonSha256"),
            ):
                self.assertEqual(
                    digest(ROOT / visual[path_field]),
                    visual[hash_field],
                )
        self.assertEqual(
            digest(ROOT / "assets" / "seoul-challenge-sculpt-dna-result.png"),
            "34ff48d78ee5f0db9a81eba4a172dfa96fe0e15275a2c45ac8e4fd06f8b92b76",
        )

    def test_base_pipeline_is_complete(self) -> None:
        spec = load(SPEC)
        self.assertEqual(
            spec["reviewPolicy"],
            {
                "version": 2,
                "authoritativeReview": "latest-per-pass",
                "evidenceBinding": "local-sha256-required",
            },
        )
        self.assertEqual(spec["sculptPipeline"]["currentPass"], "complete")
        self.assertEqual(len(spec["sculptPipeline"]["completedPasses"]), 8)
        self.assertTrue(spec["sculptDNA"]["enabled"])
        self.assertEqual(len(spec["sculptDNA"]["parameters"]), 8)
        structural = next(
            review
            for review in reversed(spec["reviewHistory"])
            if review["passId"] == "structural-pass"
        )
        supplemental = structural["visualEvidence"]["supplementalViews"]
        self.assertEqual(len(supplemental), 1)
        self.assertEqual(supplemental[0]["cameraView"], "palace-axis")
        self.assertEqual(
            digest(ROOT / supplemental[0]["renderScreenshot"]),
            supplemental[0]["renderSha256"],
        )
        latest_reviews = {
            review["passId"]: review for review in spec["reviewHistory"]
        }
        for review in latest_reviews.values():
            for item in review["visualEvidence"].get(
                "supplementalEvidence", []
            ):
                self.assertEqual(digest(ROOT / item["path"]), item["sha256"])
                self.assertEqual(item["binding"], "local-sha256")
        optimization = latest_reviews["optimization-pass"]["visualEvidence"]
        supplemental = {
            item["path"]: item["sha256"]
            for item in optimization["supplementalEvidence"]
        }
        self.assertEqual(optimization["renderSha256"], SEOUL_HERO_SHA256)
        self.assertEqual(
            supplemental["assets/seoul-palace-hero.gif"],
            SEOUL_GIF_SHA256,
        )
        self.assertEqual(
            supplemental["assets/seoul-challenge-sculpt-dna-result.png"],
            SEOUL_INTERMEDIATE_SHA256,
        )
        verify_no_absolute_evidence_paths()
        leaked = deepcopy(spec)
        leaked["reviewHistory"][-1]["visualEvidence"][
            "renderScreenshot"
        ] = "/tmp/private-render.png"
        with self.assertRaisesRegex(ValueError, "absolute path"):
            verify_repository_relative_paths(leaked, "leaked spec")
        with self.assertRaisesRegex(ValueError, "absolute path"):
            verify_repository_relative_paths(
                {"/etc/hosts": "0" * 64}, "leaked manifest key"
            )
        with self.assertRaisesRegex(ValueError, "absolute path"):
            repository_file(HERO, "/etc/hosts", "leaked manifest")
        with self.assertRaisesRegex(ValueError, "escapes repository root"):
            repository_file(HERO, "../../../etc/hosts", "leaked manifest")
        escaped_review = {
            "families": [
                {
                    "id": "brick-offroad",
                    "reviewStatus": "accepted",
                    "reference": "../../../../../../../../etc/hosts",
                    "referenceSha256": "0" * 64,
                }
            ]
        }
        with patch.object(release_verifier, "load", return_value=escaped_review):
            with self.assertRaisesRegex(ValueError, "escapes repository root"):
                release_verifier.verify_showcase_review()


if __name__ == "__main__":
    unittest.main()
