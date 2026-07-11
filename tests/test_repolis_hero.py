from __future__ import annotations

import json
from hashlib import sha256
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from probe_reference_image import probe  # noqa: E402


class RepolisHeroTests(unittest.TestCase):
    def test_factory_is_code_native_and_action_ready(self) -> None:
        factory_path = (
            ROOT
            / "examples"
            / "repolis-hero"
            / "repolis-output"
            / "createRepolisHero.js"
        )
        source = factory_path.read_text(encoding="utf-8")
        for forbidden in ("GLTFLoader", "FBXLoader", "OBJLoader", ".glb", ".gltf"):
            self.assertNotIn(forbidden, source)
        for required in (
            "createBranchGeometry",
            "createBarkTextures",
            "THREE.InstancedMesh",
            "sculptRuntime",
            "sockets",
            "colliders",
            "destructionGroups",
            "importedMeshes: 0",
            "repolis-living-system",
        ):
            self.assertIn(required, source)
        self.assertNotIn("root.userData.sculptRuntime = runtime", source)

    def test_runtime_profile_declares_zero_imported_meshes(self) -> None:
        profile_path = (
            ROOT
            / "examples"
            / "repolis-hero"
            / "repolis-output"
            / "repolis-hero-profile.json"
        )
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual(profile["generation"]["importedMeshes"], 0)
        self.assertTrue(profile["actionReadiness"]["nodes"])
        self.assertTrue(profile["actionReadiness"]["sockets"])
        self.assertTrue(profile["actionReadiness"]["colliders"])

    def test_sculpt_spec_has_complete_evidence_backed_pipeline(self) -> None:
        spec_path = ROOT / "examples" / "repolis-tree" / "object-sculpt-spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        self.assertEqual(spec["sculptPipeline"]["currentPass"], "complete")
        self.assertEqual(len(spec["sculptPipeline"]["completedPasses"]), 8)
        self.assertEqual(len(spec["reviewHistory"]), 8)
        self.assertEqual(len(spec["visualEvidence"]), 7)
        for entry in spec["visualEvidence"]:
            self.assertTrue((ROOT / entry["renderScreenshot"]).exists())
            self.assertTrue((ROOT / entry["comparisonImage"]).exists())

    def test_hero_media_and_evidence_fit_repository_budget(self) -> None:
        png = ROOT / "assets" / "repolis-tree-hero.png"
        gif = ROOT / "assets" / "repolis-tree-hero.gif"
        png_probe = probe(png)
        gif_probe = probe(gif)
        self.assertGreaterEqual(png_probe["width"], 1200)
        self.assertGreaterEqual(gif_probe["width"], 900)
        self.assertLess(png.stat().st_size, 1_500_000)
        self.assertLess(gif.stat().st_size, 5_000_000)
        evidence = list((ROOT / "examples" / "repolis-hero" / "evidence").glob("*.webp"))
        self.assertEqual(len(evidence), 12)
        self.assertLess(sum(path.stat().st_size for path in evidence), 2_000_000)

    def test_pages_workflow_builds_the_exact_demo(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "deploy-repolis-hero.yml"
        ).read_text(encoding="utf-8")
        package = json.loads(
            (ROOT / "examples" / "repolis-hero" / "package.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("examples/repolis-hero", workflow)
        self.assertIn("npm run build", workflow)
        self.assertIn("vite build", package["scripts"]["build"])
        self.assertEqual(package["scripts"]["capture"], "node scripts/capture.mjs")

    def test_motion_control_is_synchronized_from_query_state(self) -> None:
        source = (
            ROOT / "examples" / "repolis-hero" / "main.js"
        ).read_text(encoding="utf-8")
        self.assertIn("function syncMotionButton()", source)
        self.assertIn("syncMotionButton();", source)
        self.assertIn("aria-pressed", source)

    def test_artifact_manifest_matches_current_sources_and_outputs(self) -> None:
        hero_dir = ROOT / "examples" / "repolis-hero"
        manifest = json.loads(
            (hero_dir / "artifact-manifest.json").read_text(encoding="utf-8")
        )

        def digest(path: Path) -> str:
            return sha256(path.read_bytes()).hexdigest()

        for relative, expected in manifest["sourceSha256"].items():
            with self.subTest(source=relative):
                self.assertEqual(digest((hero_dir / relative).resolve()), expected)
        for relative, expected in manifest["outputSha256"].items():
            with self.subTest(output=relative):
                self.assertEqual(digest((hero_dir / relative).resolve()), expected)
        self.assertEqual(manifest["capture"]["seed"], 20260711)
        self.assertEqual(manifest["runtimeStats"]["importedMeshes"], 0)

    def test_readme_distinguishes_reference_variants_and_flagship(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        reference = readme.index("### 1. Reference")
        variants = readme.index("### 2. Sculpt DNA Variants — Intermediate Exploration")
        flagship = readme.index("### 3. Flagship: Repolis Living Archive")
        self.assertLess(reference, variants)
        self.assertLess(variants, flagship)
        self.assertIn(
            "They are **not** presented as the final visual-quality output.",
            readme,
        )


if __name__ == "__main__":
    unittest.main()
