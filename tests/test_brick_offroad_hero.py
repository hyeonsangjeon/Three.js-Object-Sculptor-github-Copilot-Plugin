from __future__ import annotations

import json
from hashlib import sha256
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HERO = ROOT / "examples" / "brick-offroad-hero"
FACTORY = HERO / "brick-output" / "createBrickOffroad.js"


class BrickOffroadHeroTests(unittest.TestCase):
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
            "left-door-pivot",
            "right-door-pivot",
            "hood-pivot",
            "tailgate-pivot",
            "roof-cargo-socket",
            "destructionGroups",
            "THREE.MeshPhysicalMaterial",
            "resources.instancedMeshes.forEach((mesh) => mesh.dispose())",
            "tailgate.position.set(3.02, 1.64, 0)",
            "socket('tailgate-hinge', tailgate, [0, 0, 0])",
            "object.isInstancedMesh ? object.count : 1",
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

    def test_runtime_variant_config_matches_every_production_mutation(self) -> None:
        config = json.loads(
            (
                HERO / "brick-output" / "brick-variant-config.json"
            ).read_text(encoding="utf-8")
        )
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
        for index, runtime_variant in enumerate(config, start=1):
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
                repetition = {
                    item["id"]: item["count"] for item in spec["repetitionSystems"]
                }
                for repetition_id, field in repetition_fields.items():
                    self.assertEqual(
                        runtime_variant[field], repetition[repetition_id]
                    )
                self.assertEqual(runtime_variant["treadCount"] % 4, 0)

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

        variant_dir = ROOT / "examples" / "showcase" / "variants" / "brick"
        manifest = json.loads(
            (variant_dir / "sculpt-dna-manifest.json").read_text(encoding="utf-8")
        )
        self.assertFalse(manifest["previewMode"])
        self.assertEqual(manifest["passGateStatus"], "evidence-backed-production")
        self.assertEqual(manifest["missingBasePasses"], [])
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
        self.assertEqual(manifest["capture"]["frames"], 24)
        self.assertEqual(manifest["capture"]["fps"], 6)
        self.assertEqual(manifest["capture"]["rotationSeconds"], 4)
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
        }
        for item in manifest["variantStats"]:
            stats = item["stats"]
            self.assertEqual(
                (
                    stats["treadInstances"],
                    stats["studInstances"],
                    stats["roofLampInstances"],
                ),
                expected_counts[item["id"]],
            )
            self.assertEqual(stats["treadsPerWheel"] * 4, stats["treadInstances"])
        for relative in (
            "../showcase/variants/brick/brick-offroad-v001.json",
            "../showcase/variants/brick/brick-offroad-v002.json",
            "../showcase/variants/brick/brick-offroad-v003.json",
            "../showcase/variants/brick/sculpt-dna-manifest.json",
            "brick-output/brick-variant-config.json",
            "scripts/capture.mjs",
            "../../scripts/make_visual_comparison_sheet.py",
        ):
            self.assertIn(relative, manifest["sourceSha256"])
        self.assertEqual(
            manifest["referenceSha256"]["source"],
            manifest["referenceSha256"]["heroCopy"],
        )
        self.assertLess((ROOT / "assets" / "brick-offroad-hero.png").stat().st_size, 1_500_000)
        self.assertLess((ROOT / "assets" / "brick-offroad-hero.gif").stat().st_size, 5_000_000)
        evidence = list((HERO / "evidence").glob("*.webp"))
        self.assertEqual(len(evidence), 18)
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

    def test_pages_workflow_keeps_repolis_root_and_brick_subroute(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "deploy-repolis-hero.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("examples/repolis-hero/dist/. pages/", workflow)
        self.assertIn("examples/brick-offroad-hero/dist/. pages/brick/", workflow)
        self.assertIn("path: pages", workflow)

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
