from __future__ import annotations

from copy import deepcopy
import json
from hashlib import sha256
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERO = ROOT / "examples" / "brick-offroad-hero"
FACTORY = HERO / "brick-output" / "createBrickOffroad.js"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from append_sculpt_review import (  # noqa: E402
    pass_specific_evidence as append_evidence,
    sync_pipeline as append_sync_pipeline,
)
from sculpt_pass_orchestrator import (  # noqa: E402
    next_required_evidence,
    pass_specific_evidence as orchestrator_evidence,
)
from verify_release import (  # noqa: E402
    verify_brick_capture_fingerprint,
    verify_complete_latest_review_pipeline,
    verify_production_review_policy,
)


class BrickOffroadHeroTests(unittest.TestCase):
    def run_factory_probe(self, source: str) -> dict:
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", source],
            cwd=HERO,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_factory_is_vehicle_specific_code_native_and_action_ready(self) -> None:
        source = FACTORY.read_text(encoding="utf-8")
        for forbidden in ("GLTFLoader", "FBXLoader", "OBJLoader", ".glb", ".gltf"):
            self.assertNotIn(forbidden, source)
        for required in (
            "createSurfaceTextures",
            "THREE.InstancedMesh",
            "['front-left', -2.22, 1]",
            "['front-right', -2.22, -1]",
            "['rear-left', 2.12, 1]",
            "['rear-right', 2.12, -1]",
            "`${id}-wheel-pivot`",
            "`${sideName}-door-pivot`",
            "`${sideName}-rear-door-pivot`",
            "hood-pivot",
            "tailgate-pivot",
            "roof-cargo-socket",
            "destructionGroups",
            "THREE.MeshPhysicalMaterial",
            "resources.instancedMeshes.forEach((mesh) => mesh.dispose())",
            "tailgate.position.set(3.02, 1.64, 0)",
            "socket('tailgate-hinge', tailgate, [0, 0, 0])",
            "object.isInstancedMesh ? object.count : 1",
            "variant.wear",
            "importedMeshes: 0",
        ):
            self.assertIn(required, source)
        self.assertNotIn("root.userData.sculptRuntime = runtime", source)

    def test_runtime_profile_and_manifest_lock_four_wheel_topology(self) -> None:
        profile = json.loads(
            (HERO / "brick-output" / "brick-offroad-profile.json").read_text(
                encoding="utf-8"
            )
        )
        manifest = json.loads(
            (HERO / "artifact-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(profile["generation"]["importedMeshes"], 0)
        self.assertEqual(profile["actionReadiness"]["wheelPivots"], 4)
        self.assertEqual(profile["actionReadiness"]["steeringPivots"], 2)
        self.assertEqual(profile["actionReadiness"]["suspensionAnchors"], 4)
        self.assertIn(
            "transientHeightFieldForNormalGeneration",
            profile["generation"],
        )
        self.assertNotIn(", height,", profile["generation"]["materials"])
        self.assertNotIn("height", profile["generation"]["retainedTextureChannels"])
        self.assertEqual(manifest["runtimeStats"]["wheels"], 4)
        self.assertEqual(manifest["runtimeStats"]["importedMeshes"], 0)
        self.assertFalse(manifest["capture"]["localGitMetadataExposed"])
        budget = json.loads(
            (
                ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json"
            ).read_text(encoding="utf-8")
        )["performanceBudget"]
        self.assertLessEqual(
            manifest["runtimeStats"]["triangles"], budget["targetTriangles"]
        )
        self.assertLessEqual(
            manifest["runtimeStats"]["renderCalls"], budget["maxDrawCalls"]
        )
        self.assertEqual(manifest["runtimeStats"]["generatedTextureResolution"], 512)

    def test_release_enforces_latest_reviews_policy_and_capture_source(self) -> None:
        base_path = ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json"
        base = json.loads(base_path.read_text(encoding="utf-8"))
        downgraded = deepcopy(base)
        downgraded.pop("reviewPolicy")
        with self.assertRaisesRegex(ValueError, "reviewPolicy v2"):
            verify_production_review_policy(downgraded, base_path)

        variant_path = (
            ROOT
            / "examples"
            / "showcase"
            / "variants"
            / "brick"
            / "brick-offroad-v001.json"
        )
        variant = json.loads(variant_path.read_text(encoding="utf-8"))
        revoked = deepcopy(variant)
        revoked["reviewHistory"].append(
            {
                **deepcopy(revoked["reviewHistory"][0]),
                "action": "refine-code",
            }
        )
        with self.assertRaisesRegex(ValueError, "latest evidence-backed pass"):
            verify_complete_latest_review_pipeline(revoked, variant_path)

        manifest = json.loads(
            (HERO / "artifact-manifest.json").read_text(encoding="utf-8")
        )
        stale = deepcopy(manifest)
        stale["capture"]["sourceFingerprint"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source fingerprint is stale"):
            verify_brick_capture_fingerprint(HERO, stale)

    def test_runtime_variant_config_matches_every_production_mutation(self) -> None:
        config = json.loads(
            (
                HERO / "brick-output" / "brick-variant-config.json"
            ).read_text(encoding="utf-8")
        )
        base_config, *variant_config = config
        self.assertTrue(all("bodyDark" not in item for item in config))
        variant_dir = ROOT / "examples" / "showcase" / "variants" / "brick"
        material_fields = {
            "body-shell": ("body", "bodyRoughness"),
            "roof-shell": ("roof", "roofRoughness"),
            "dark-trim": ("trim", "trimRoughness"),
            "accent": ("accent", "accentRoughness"),
            "rubber": ("rubber", "rubberRoughness"),
            "glass": ("glass", "glassRoughness"),
            "lamp": ("lamp", "lampRoughness"),
        }
        repetition_fields = {
            "wheel-treads": "treadCount",
            "body-studs": "studCount",
            "roof-lamps": "roofLampCount",
        }
        base_spec = json.loads(
            (
                ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json"
            ).read_text(encoding="utf-8")
        )
        base_materials = {item["id"]: item for item in base_spec["materials"]}
        self.assertEqual(base_config["id"], "brick-offroad-base")
        for material_id, (color_field, roughness_field) in material_fields.items():
            self.assertEqual(
                base_config[color_field],
                base_materials[material_id]["colorVariation"]["palette"][0],
            )
            self.assertEqual(
                base_config[roughness_field],
                base_materials[material_id]["roughness"]["base"],
            )
        self.assertEqual(
            base_config["lampEmissive"],
            base_materials["lamp"]["emissive"]["color"],
        )
        self.assertEqual(
            base_config["lampEmissiveIntensity"],
            base_materials["lamp"]["emissive"]["intensity"],
        )
        self.assertEqual(
            base_config["wear"],
            base_materials["body-shell"]["wear"]["edgeWear"],
        )
        self.assertEqual(
            base_config["dust"],
            base_materials["body-shell"]["dirt"]["color"],
        )
        self.assertEqual(
            base_config["dirtAmount"],
            base_materials["body-shell"]["dirt"]["amount"],
        )
        base_repetition = {
            item["id"]: item["count"] for item in base_spec["repetitionSystems"]
        }
        for repetition_id, field in repetition_fields.items():
            self.assertEqual(base_config[field], base_repetition[repetition_id])

        for index, runtime_variant in enumerate(variant_config, start=1):
            spec_path = variant_dir / f"brick-offroad-v{index:03d}.json"
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            with self.subTest(variant=runtime_variant["id"]):
                self.assertEqual(runtime_variant["id"], spec["targetId"])
                materials = {item["id"]: item for item in spec["materials"]}
                for material_id, (color_field, roughness_field) in material_fields.items():
                    self.assertEqual(
                        runtime_variant[color_field],
                        materials[material_id]["colorVariation"]["palette"][0],
                    )
                    self.assertEqual(
                        runtime_variant[roughness_field],
                        materials[material_id]["roughness"]["base"],
                    )
                self.assertEqual(
                    runtime_variant["lampEmissive"],
                    materials["lamp"]["emissive"]["color"],
                )
                self.assertEqual(
                    runtime_variant["lampEmissiveIntensity"],
                    materials["lamp"]["emissive"]["intensity"],
                )
                repetition = {
                    item["id"]: item["count"] for item in spec["repetitionSystems"]
                }
                for repetition_id, field in repetition_fields.items():
                    self.assertEqual(
                        runtime_variant[field], repetition[repetition_id]
                    )
                self.assertEqual(runtime_variant["treadCount"] % 4, 0)
                self.assertEqual(
                    runtime_variant["wear"],
                    materials["body-shell"]["wear"]["edgeWear"],
                )
                self.assertEqual(
                    runtime_variant["dirtAmount"],
                    materials["body-shell"]["dirt"]["amount"],
                )
                self.assertEqual(
                    runtime_variant["dust"],
                    materials["body-shell"]["dirt"]["color"],
                )

    def test_albedo_encoding_preserves_srgb_hex_intent(self) -> None:
        probe = self.run_factory_probe(
            """
            import * as THREE from 'three';
            import { encodeLinearRGBToSRGBBytes } from './brick-output/createBrickOffroad.js';
            const color = new THREE.Color('#65704A');
            console.log(JSON.stringify({
              encoded: encodeLinearRGBToSRGBBytes(color),
              linearBytes: [color.r, color.g, color.b].map((value) => Math.round(value * 255)),
            }));
            """
        )
        self.assertEqual(probe["encoded"], [101, 112, 74])
        self.assertEqual(probe["linearBytes"], [33, 41, 17])

    def test_configs_are_frozen_and_factory_results_are_isolated(self) -> None:
        probe = self.run_factory_probe(
            """
            import {
              BRICK_BASE_CONFIG,
              BRICK_VARIANTS,
              createBrickOffroad,
            } from './brick-output/createBrickOffroad.js';
            const first = createBrickOffroad({ variant: 'base', stage: 'blockout' });
            const originalBody = first.variant.body;
            first.variant.body = '#000000';
            const second = createBrickOffroad({ variant: 'base', stage: 'blockout' });
            console.log(JSON.stringify({
              baseFrozen: Object.isFrozen(BRICK_BASE_CONFIG),
              variantsFrozen: Object.isFrozen(BRICK_VARIANTS),
              variantFrozen: Object.isFrozen(BRICK_VARIANTS[0]),
              distinctSnapshots: first.variant !== second.variant,
              firstMutated: first.variant.body === '#000000',
              secondBody: second.variant.body,
              canonicalBody: BRICK_BASE_CONFIG.body,
              originalBody,
            }));
            first.dispose();
            second.dispose();
            """
        )
        self.assertTrue(probe["baseFrozen"])
        self.assertTrue(probe["variantsFrozen"])
        self.assertTrue(probe["variantFrozen"])
        self.assertTrue(probe["distinctSnapshots"])
        self.assertTrue(probe["firstMutated"])
        self.assertEqual(probe["secondBody"], probe["originalBody"])
        self.assertEqual(probe["canonicalBody"], probe["originalBody"])

    def test_front_recovery_hardware_follows_bumper_articulation(self) -> None:
        probe = self.run_factory_probe(
            """
            import * as THREE from 'three';
            import { createBrickOffroad } from './brick-output/createBrickOffroad.js';
            const result = createBrickOffroad({ variant: 'base', stage: 'full' });
            const pivot = result.runtime.nodes['front-bumper-pivot'];
            const ids = ['front-winch', 'winch-drum', 'recovery-hook--1', 'recovery-hook-1'];
            result.root.updateMatrixWorld(true);
            const before = Object.fromEntries(ids.map((id) => [
              id,
              result.runtime.meshes[id].getWorldPosition(new THREE.Vector3()).toArray(),
            ]));
            pivot.rotation.z = 0.35;
            result.root.updateMatrixWorld(true);
            const after = Object.fromEntries(ids.map((id) => [
              id,
              result.runtime.meshes[id].getWorldPosition(new THREE.Vector3()).toArray(),
            ]));
            console.log(JSON.stringify({
              allParented: ids.every((id) => result.runtime.meshes[id].parent === pivot),
              allMoved: ids.every((id) => before[id].some(
                (value, index) => Math.abs(value - after[id][index]) > 1e-4,
              )),
            }));
            result.dispose();
            """
        )
        self.assertTrue(probe["allParented"])
        self.assertTrue(probe["allMoved"])

    def test_spec_and_curated_variants_are_evidence_backed_production(self) -> None:
        base = json.loads(
            (
                ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(base["sculptPipeline"]["currentPass"], "complete")
        self.assertEqual(len(base["sculptPipeline"]["completedPasses"]), 8)
        self.assertEqual(len(base["reviewHistory"]), 8)
        self.assertGreaterEqual(len(base["visualEvidence"]), 7)
        self.assertEqual(
            base["lookDevTargets"]["materialPass"]["minimumTextureResolution"],
            512,
        )
        self.assertTrue(
            all(item["textureResolution"] == 512 for item in base["materials"])
        )
        material_probe = deepcopy(base)
        material_probe["reviewHistory"] = material_probe["reviewHistory"][:3]
        append_sync_pipeline(material_probe)
        self.assertEqual(
            material_probe["sculptPipeline"]["currentPass"],
            "material-pass",
        )
        self.assertEqual(
            material_probe["sculptPipeline"]["nextRequiredEvidence"],
            next_required_evidence(material_probe, "material-pass"),
        )
        self.assertEqual(
            append_evidence(base, "material-pass"),
            orchestrator_evidence(base, "material-pass"),
        )
        self.assertTrue(
            any(
                "512px" in item
                for item in append_evidence(base, "material-pass")
            )
        )

        variant_dir = ROOT / "examples" / "showcase" / "variants" / "brick"
        manifest = json.loads(
            (variant_dir / "sculpt-dna-manifest.json").read_text(encoding="utf-8")
        )
        artifact_manifest = json.loads(
            (HERO / "artifact-manifest.json").read_text(encoding="utf-8")
        )
        expected_scores = {
            "brick-offroad-v001": 0.78,
            "brick-offroad-v002": 0.77,
            "brick-offroad-v003": 0.78,
        }
        self.assertFalse(manifest["previewMode"])
        self.assertEqual(manifest["passGateStatus"], "evidence-backed-production")
        self.assertEqual(manifest["missingBasePasses"], [])
        self.assertEqual(
            manifest["visualReviewSet"]["variantReviewIds"],
            [
                item["visualEvidence"]["reviewId"]
                for item in manifest["variants"]
            ],
        )
        self.assertEqual(
            {manifest["visualReviewSet"]["reviewedAt"]},
            {
                item["visualEvidence"]["reviewedAt"]
                for item in manifest["variants"]
            },
        )
        for index, item in enumerate(manifest["variants"], start=1):
            with self.subTest(variant=index):
                self.assertEqual(
                    item["passGateStatus"], "evidence-backed-production"
                )
                self.assertGreaterEqual(item["visualEvidence"]["aiVisionScore"], 0.74)
                variant = json.loads(
                    (variant_dir / item["path"]).read_text(encoding="utf-8")
                )
                self.assertEqual(
                    variant["sculptPipeline"]["currentPass"], "complete"
                )
                self.assertEqual(len(variant["reviewHistory"]), 8)
                acceptance = variant["variantProvenance"]["visualAcceptance"]
                self.assertEqual(
                    acceptance["aiVisionScore"],
                    expected_scores[variant["targetId"]],
                )
                render_path = ROOT / acceptance["renderScreenshot"]
                comparison_path = ROOT / acceptance["comparisonImage"]
                self.assertEqual(
                    acceptance["renderSha256"],
                    sha256(render_path.read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    acceptance["comparisonSha256"],
                    sha256(comparison_path.read_bytes()).hexdigest(),
                )
                render_key = str(render_path.relative_to(HERO))
                comparison_key = str(comparison_path.relative_to(HERO))
                self.assertEqual(
                    acceptance["renderSha256"],
                    artifact_manifest["outputSha256"][render_key],
                )
                self.assertEqual(
                    acceptance["comparisonSha256"],
                    artifact_manifest["outputSha256"][comparison_key],
                )
                for review in variant["reviewHistory"]:
                    visual = review["visualEvidence"]
                    self.assertEqual(
                        visual["reviewedAt"],
                        acceptance["reviewedAt"],
                    )
                    self.assertEqual(
                        visual["renderSha256"],
                        acceptance["renderSha256"],
                    )
                    self.assertEqual(
                        visual["comparisonSha256"],
                        acceptance["comparisonSha256"],
                    )
                manifest_visual = item["visualEvidence"]
                self.assertEqual(
                    manifest_visual["renderSha256"],
                    acceptance["renderSha256"],
                )
                self.assertEqual(
                    manifest_visual["comparisonSha256"],
                    acceptance["comparisonSha256"],
                )

    def test_capture_artifacts_match_hash_manifest_and_media_budget(self) -> None:
        manifest = json.loads(
            (HERO / "artifact-manifest.json").read_text(encoding="utf-8")
        )

        def digest(path: Path) -> str:
            return sha256(path.read_bytes()).hexdigest()

        for relative, expected in manifest["sourceSha256"].items():
            with self.subTest(source=relative):
                self.assertEqual(digest((HERO / relative).resolve()), expected)
        for relative, expected in manifest["outputSha256"].items():
            with self.subTest(output=relative):
                self.assertEqual(digest((HERO / relative).resolve()), expected)
        self.assertIn(
            "../../assets/brick-offroad-sculpt-dna-result.png",
            manifest["outputSha256"],
        )
        self.assertEqual(manifest["capture"]["frames"], 24)
        self.assertEqual(manifest["capture"]["fps"], 6)
        self.assertEqual(manifest["capture"]["rotationSeconds"], 4)
        self.assertEqual(manifest["capture"]["variant"], "brick-offroad-base")
        self.assertTrue(manifest["capture"]["deterministic"])
        self.assertEqual(manifest["capture"]["portAllocation"], "ephemeral-os-assigned")
        self.assertEqual(len(manifest["capture"]["sourceFingerprint"]), 64)
        self.assertEqual(manifest["capture"]["canonicalElapsed"], 1.25)
        self.assertEqual(
            manifest["baseConfiguration"]["id"], "brick-offroad-base"
        )
        self.assertEqual(
            manifest["runtimeStats"]["configurationId"], "brick-offroad-base"
        )
        self.assertEqual(manifest["runtimeStats"]["generatedTextureCount"], 48)
        self.assertEqual(manifest["runtimeStats"]["wear"], 0.08)
        self.assertTrue(manifest["lifecycleCheck"]["complete"])
        self.assertTrue(manifest["lifecycleCheck"]["removedFromScene"])
        self.assertTrue(
            manifest["lifecycleCheck"]["rendererMemoryDidNotRebound"]
        )
        self.assertTrue(manifest["recoveryArticulation"]["allParented"])
        self.assertTrue(manifest["recoveryArticulation"]["allMoved"])
        self.assertTrue(
            manifest["lifecycleCheck"]["webglAllocationsDidNotRebound"]
        )
        self.assertGreaterEqual(
            manifest["lifecycleCheck"]["postDisposeFrames"],
            5,
        )
        self.assertLessEqual(
            manifest["lifecycleCheck"]["memoryPostRender"]["geometries"],
            manifest["lifecycleCheck"]["memoryDisposed"]["geometries"],
        )
        self.assertLessEqual(
            manifest["lifecycleCheck"]["memoryPostRender"]["textures"],
            manifest["lifecycleCheck"]["memoryDisposed"]["textures"],
        )
        self.assertEqual(
            manifest["lifecycleCheck"]["allocationsDisposed"],
            manifest["lifecycleCheck"]["allocationsPostRender"],
        )
        self.assertEqual(
            manifest["lifecycleCheck"]["counts"],
            manifest["lifecycleCheck"]["disposed"],
        )
        self.assertEqual(manifest["lifecycleCheck"]["counts"]["textures"], 48)
        self.assertTrue(
            all(item["allParented"] for item in manifest["doorArticulation"])
        )
        self.assertTrue(
            all(item["childMoved"] for item in manifest["doorArticulation"])
        )
        self.assertTrue(
            all(
                item["fastenerParentedDirectly"]
                and item["fastenerInstancesMoved"]
                and item["fixedFastenersStayed"]
                for item in manifest["doorArticulation"]
            )
        )
        self.assertTrue(
            all(
                item["fastenerWorldBefore"] != item["fastenerWorldAfter"]
                for item in manifest["doorArticulation"]
            )
        )
        self.assertTrue(
            all(
                len([child for child in item["childIds"] if "hinge" in child]) >= 3
                for item in manifest["doorArticulation"]
            )
        )
        self.assertTrue(
            all(
                any("fasteners" in child for child in item["childIds"])
                for item in manifest["doorArticulation"]
            )
        )
        self.assertEqual(
            {item["id"] for item in manifest["variantStats"]},
            {
                "brick-offroad-v001",
                "brick-offroad-v002",
                "brick-offroad-v003",
            },
        )
        expected_counts = {
            item["id"]: (
                item["treadCount"],
                item["studCount"],
                item["roofLampCount"],
            )
            for item in json.loads(
                (
                    HERO / "brick-output" / "brick-variant-config.json"
                ).read_text(encoding="utf-8")
            )
            if item["id"] != "brick-offroad-base"
        }
        expected_wear = {
            item["id"]: item["wear"]
            for item in json.loads(
                (
                    HERO / "brick-output" / "brick-variant-config.json"
                ).read_text(encoding="utf-8")
            )
            if item["id"] != "brick-offroad-base"
        }
        expected_dirt = {
            item["id"]: item["dirtAmount"]
            for item in json.loads(
                (
                    HERO / "brick-output" / "brick-variant-config.json"
                ).read_text(encoding="utf-8")
            )
            if item["id"] != "brick-offroad-base"
        }
        for item in manifest["variantStats"]:
            stats = item["stats"]
            runtime_config = next(
                value
                for value in json.loads(
                    (
                        HERO / "brick-output" / "brick-variant-config.json"
                    ).read_text(encoding="utf-8")
                )
                if value["id"] == item["id"]
            )
            expected_controls = {
                key: value
                for key, value in runtime_config.items()
                if key not in {"id", "label"}
            }
            actual_controls = dict(item["controls"])
            derived = actual_controls.pop("derivedBodyDark")
            self.assertEqual(actual_controls, expected_controls)
            self.assertEqual(
                derived,
                {"source": "body", "multiplier": 0.72},
            )
            self.assertEqual(
                (
                    stats["treadInstances"],
                    stats["studInstances"],
                    stats["roofLampInstances"],
                ),
                expected_counts[item["id"]],
            )
            self.assertEqual(stats["treadsPerWheel"] * 4, stats["treadInstances"])
            self.assertEqual(stats["wear"], expected_wear[item["id"]])
            self.assertEqual(stats["dirtAmount"], expected_dirt[item["id"]])
        for relative in (
            "../showcase/variants/brick/brick-offroad-v001.json",
            "../showcase/variants/brick/brick-offroad-v002.json",
            "../showcase/variants/brick/brick-offroad-v003.json",
            "../showcase/variants/brick/sculpt-dna-manifest.json",
            "brick-output/brick-variant-config.json",
            "scripts/capture.mjs",
            "../../scripts/append_sculpt_review.py",
            "../../scripts/make_visual_comparison_sheet.py",
            "../../scripts/sculpt_pass_orchestrator.py",
            "../../scripts/sculpt_dna.py",
            "../../scripts/validate_sculpt_spec.py",
            "../../scripts/visual_evidence_hashes.py",
        ):
            self.assertIn(relative, manifest["sourceSha256"])
        self.assertEqual(
            manifest["referenceSha256"]["source"],
            manifest["referenceSha256"]["heroCopy"],
        )
        self.assertLess((ROOT / "assets" / "brick-offroad-hero.png").stat().st_size, 1_500_000)
        self.assertLess((ROOT / "assets" / "brick-offroad-hero.gif").stat().st_size, 5_000_000)
        evidence = list((HERO / "evidence").glob("*.webp"))
        self.assertEqual(len(evidence), 20)
        self.assertTrue((HERO / "evidence" / "door-articulation.webp").exists())
        self.assertTrue((HERO / "evidence" / "showcase-comparison.webp").exists())
        self.assertLess(sum(path.stat().st_size for path in evidence), 3_000_000)

    def test_capture_is_portable_and_preflights_before_overwrite(self) -> None:
        capture = (HERO / "scripts" / "capture.mjs").read_text(encoding="utf-8")
        comparison = (
            ROOT / "scripts" / "make_visual_comparison_sheet.py"
        ).read_text(encoding="utf-8")
        self.assertIn("run(ffmpeg, ['-version']", capture)
        self.assertLess(
            capture.index("run(ffmpeg, ['-version']"),
            capture.index("await rm(framesDir"),
        )
        self.assertIn('shutil.which("ffmpeg")', comparison)
        self.assertIn('"-frames:v"', comparison)
        self.assertIn("capture=1", capture)
        self.assertIn("deterministicFrameSha256", capture)
        self.assertIn("allocateEphemeralPort", capture)
        self.assertIn("verifySourceFingerprint", capture)
        self.assertNotIn("const baseUrl = 'http://127.0.0.1:4176'", capture)
        factory = FACTORY.read_text(encoding="utf-8")
        self.assertNotIn("height: createDataTexture", factory)
        self.assertNotIn("write(height", factory)
        readme = (HERO / "README.md").read_text(encoding="utf-8")
        for dependency in ("Python 3", "ffmpeg", "cwebp", "Chrome"):
            self.assertIn(dependency, readme)

    def test_pages_workflow_builds_clean_isolated_routes(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "deploy-repolis-hero.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "PAGES_DIR: ${{ runner.temp }}/threejs-sculpt-dna-pages",
            workflow,
        )
        self.assertIn('test ! -e "$PAGES_DIR"', workflow)
        self.assertIn('examples/repolis-hero/dist/. "$PAGES_DIR/"', workflow)
        self.assertIn(
            'examples/brick-offroad-hero/dist/. "$PAGES_DIR/brick/"',
            workflow,
        )
        self.assertIn(
            'examples/showcase/dist/. "$PAGES_DIR/showcase/"',
            workflow,
        )
        self.assertIn('- "examples/showcase/**"', workflow)
        self.assertIn('- "scripts/**"', workflow)
        self.assertIn('- "tests/**"', workflow)
        self.assertIn("python3 scripts/verify_release.py", workflow)
        self.assertIn("python3 -m unittest discover -s tests -q", workflow)
        self.assertIn("npm run test:capture", workflow)
        self.assertIn(
            'diff -qr examples/brick-offroad-hero/dist "$PAGES_DIR/brick"',
            workflow,
        )
        self.assertIn(
            'diff -qr examples/showcase/dist "$PAGES_DIR/showcase"',
            workflow,
        )
        self.assertIn(
            "path: ${{ runner.temp }}/threejs-sculpt-dna-pages",
            workflow,
        )

    def test_readme_preserves_repolis_primary_and_adds_brick_flow(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        repolis = readme.index("## 03 · Flagship: Repolis Living Archive")
        brick = readme.index("### Brick Off-Road Explorer")
        self.assertLess(repolis, brick)
        self.assertIn("threejs-sculpt-dna/brick/", readme)
        self.assertIn(
            "**Reference** → **Sculpt DNA variants** → **Flagship**",
            readme,
        )
        self.assertIn(
            'alt="Final Brick Off-Road Explorer flagship render"',
            readme,
        )


if __name__ == "__main__":
    unittest.main()
