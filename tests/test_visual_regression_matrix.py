from __future__ import annotations

import copy
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from new_sculpt_spec import make_spec  # noqa: E402
from visual_evidence_hashes import (  # noqa: E402
    LATEST_REVIEW_SELECTION,
    REVIEW_POLICY_VERSION,
    SHA_REQUIRED_BINDING,
    bind_visual_evidence_hashes,
    file_sha256,
)
from visual_regression_matrix import build_report, main  # noqa: E402


REQUIRED_LAYERS = (
    "silhouetteProportion",
    "componentStructure",
    "formDetail",
    "materialSurface",
    "lightingCamera",
)
VIEW_FEATURES = {
    "front": ("blockout", "overall-silhouette"),
    "detail": ("surface-pass", "reference-material-system"),
}


class VisualRegressionMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(
            prefix=".visual-matrix-",
            dir=ROOT / "tests",
        )
        self.root = Path(self._temporary.name)
        self.base_path = self.root / "base.json"
        self.manifest_path = self.root / "sculpt-dna-manifest.json"
        self.variant_paths = {
            variant_id: self.root / f"{variant_id}.json"
            for variant_id in (
                "matrix-v001",
                "matrix-v002",
                "matrix-v003",
            )
        }
        self._write_fixture()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _repo_path(self, path: Path) -> str:
        return path.relative_to(ROOT).as_posix()

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def _review(
        self,
        spec_path: Path,
        asset_id: str,
        viewpoint_id: str,
        pass_id: str,
        feature_id: str,
    ) -> dict:
        evidence_dir = self.root / "evidence" / asset_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        render_path = evidence_dir / f"{viewpoint_id}-render.bin"
        comparison_path = evidence_dir / f"{viewpoint_id}-comparison.bin"
        render_path.write_bytes(f"{asset_id}:{viewpoint_id}:render".encode())
        comparison_path.write_bytes(f"{asset_id}:{viewpoint_id}:comparison".encode())
        visual = {
            "reviewId": f"{asset_id}-{pass_id}-review",
            "reviewedAt": "2026-07-15T00:00:00Z",
            "renderScreenshot": self._repo_path(render_path),
            "comparisonImage": self._repo_path(comparison_path),
            "cameraView": viewpoint_id,
        }
        bind_visual_evidence_hashes(visual, spec_path)
        return {
            "timestamp": "2026-07-15T00:00:00Z",
            "passId": pass_id,
            "action": "continue",
            "aiVisionScore": 0.9,
            "visualAcceptanceThreshold": 0.7,
            "layerScores": {layer: 0.9 for layer in REQUIRED_LAYERS},
            "featureReviews": [
                {
                    "id": feature_id,
                    "visible": True,
                    "score": 0.9,
                    "notes": "AI vision reviewed the exact current image pair.",
                }
            ],
            "visualEvidence": visual,
        }

    def _spec(self, path: Path, asset_id: str, variant: bool) -> dict:
        spec = make_spec("Matrix Fixture", "reference.png")
        spec["reviewPolicy"] = {
            "version": REVIEW_POLICY_VERSION,
            "authoritativeReview": LATEST_REVIEW_SELECTION,
            "evidenceBinding": SHA_REQUIRED_BINDING,
        }
        spec["reviewHistory"] = [
            self._review(path, asset_id, viewpoint, pass_id, feature_id)
            for viewpoint, (pass_id, feature_id) in VIEW_FEATURES.items()
        ]
        spec["visualEvidence"] = []
        if variant:
            spec["variantProvenance"] = {
                "variantId": asset_id,
                "passGateStatus": "evidence-backed-production",
            }
        return spec

    def _write_fixture(self) -> None:
        self._write_json(
            self.base_path,
            self._spec(self.base_path, "base", variant=False),
        )
        for variant_id, path in self.variant_paths.items():
            self._write_json(path, self._spec(path, variant_id, variant=True))

        prefix = self.root.relative_to(ROOT).as_posix()
        manifest = {
            "schemaVersion": "1.0",
            "sourceSpec": self.base_path.name,
            "sourceSpecSha256": file_sha256(self.base_path),
            "count": 3,
            "samplingMode": "coverage-curated",
            "previewMode": False,
            "passGateStatus": "evidence-backed-production",
            "variants": [
                {
                    "variantId": "matrix-v003",
                    "path": self.variant_paths["matrix-v003"].name,
                    "curatedIndex": 3,
                    "previewMode": False,
                    "passGateStatus": "evidence-backed-production",
                },
                {
                    "variantId": "matrix-v001",
                    "path": self.variant_paths["matrix-v001"].name,
                    "curatedIndex": 1,
                    "previewMode": False,
                    "passGateStatus": "evidence-backed-production",
                },
                {
                    "variantId": "matrix-v002",
                    "path": self.variant_paths["matrix-v002"].name,
                    "curatedIndex": 2,
                    "previewMode": False,
                    "passGateStatus": "evidence-backed-production",
                },
            ],
            "visualRegressionMatrix": {
                "schemaVersion": "1.0",
                "viewpoints": [
                    {
                        "id": "front",
                        "passId": "blockout",
                        "cameraView": "front",
                        "renderPathTemplate": (
                            f"{prefix}/evidence/{{assetId}}/"
                            "{viewpointId}-render.bin"
                        ),
                        "comparisonPathTemplate": (
                            f"{prefix}/evidence/{{assetId}}/"
                            "{viewpointId}-comparison.bin"
                        ),
                        "featureIds": ["overall-silhouette"],
                    },
                    {
                        "id": "detail",
                        "passId": "surface-pass",
                        "cameraView": "detail",
                        "renderPathTemplate": (
                            f"{prefix}/evidence/{{assetId}}/"
                            "{viewpointId}-render.bin"
                        ),
                        "comparisonPathTemplate": (
                            f"{prefix}/evidence/{{assetId}}/"
                            "{viewpointId}-comparison.bin"
                        ),
                        "featureIds": ["reference-material-system"],
                    },
                ],
            },
        }
        self._write_json(self.manifest_path, manifest)

    def _load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _rewrite_spec(self, path: Path, mutate) -> None:
        spec = self._load(path)
        mutate(spec)
        self._write_json(path, spec)
        if path == self.base_path:
            manifest = self._load(self.manifest_path)
            manifest["sourceSpecSha256"] = file_sha256(self.base_path)
            self._write_json(self.manifest_path, manifest)

    def _report(self) -> dict:
        return build_report(
            self.base_path,
            self.manifest_path,
            cli_viewpoints=[],
            render_template=None,
            comparison_template=None,
            feature_ids=(),
        )

    @staticmethod
    def _review_for(spec: dict, pass_id: str) -> dict:
        return next(
            review
            for review in spec["reviewHistory"]
            if review["passId"] == pass_id
        )

    @staticmethod
    def _cell(report: dict, asset_id: str, viewpoint_id: str) -> dict:
        return next(
            cell
            for cell in report["cells"]
            if cell["assetId"] == asset_id
            and cell["viewpointId"] == viewpoint_id
        )

    def test_clean_matrix_is_deterministic_for_three_variants_and_two_views(self) -> None:
        first = self._report()
        second = self._report()
        self.assertEqual(first, second)
        self.assertTrue(first["ok"])
        self.assertEqual(
            [asset["id"] for asset in first["assets"]],
            ["base", "matrix-v001", "matrix-v002", "matrix-v003"],
        )
        self.assertEqual(
            [viewpoint["id"] for viewpoint in first["viewpoints"]],
            ["detail", "front"],
        )
        self.assertEqual(
            [
                (cell["assetId"], cell["viewpointId"], cell["status"])
                for cell in first["cells"]
            ],
            [
                ("base", "detail", "passing"),
                ("base", "front", "passing"),
                ("matrix-v001", "detail", "passing"),
                ("matrix-v001", "front", "passing"),
                ("matrix-v002", "detail", "passing"),
                ("matrix-v002", "front", "passing"),
                ("matrix-v003", "detail", "passing"),
                ("matrix-v003", "front", "passing"),
            ],
        )
        self.assertEqual(
            first["summary"],
            {
                "total": 8,
                "missing": 0,
                "stale": 0,
                "passing": 8,
                "failing": 0,
            },
        )
        self.assertEqual(first["authority"]["finalVisualAuthority"], "ai-vision")
        self.assertFalse(first["authority"]["pixelMetricsCanApprove"])

    def test_missing_render_and_comparison_evidence_are_classified(self) -> None:
        def remove_render(spec: dict) -> None:
            self._review_for(spec, "blockout")["visualEvidence"].pop(
                "renderScreenshot"
            )

        def remove_comparison(spec: dict) -> None:
            self._review_for(spec, "surface-pass")["visualEvidence"].pop(
                "comparisonImage"
            )

        self._rewrite_spec(self.base_path, remove_render)
        self._rewrite_spec(self.variant_paths["matrix-v001"], remove_comparison)
        report = self._report()
        base_cell = self._cell(report, "base", "front")
        variant_cell = self._cell(report, "matrix-v001", "detail")
        self.assertEqual(base_cell["status"], "missing")
        self.assertEqual(variant_cell["status"], "missing")
        self.assertTrue(
            any(item["code"] == "renderScreenshot-missing" for item in base_cell["issues"])
        )
        self.assertTrue(
            any(
                item["code"] == "comparisonImage-missing"
                for item in variant_cell["issues"]
            )
        )

    def test_overwritten_evidence_is_stale(self) -> None:
        spec = self._load(self.variant_paths["matrix-v002"])
        visual = self._review_for(spec, "blockout")["visualEvidence"]
        evidence_path = ROOT / visual["renderScreenshot"]
        evidence_path.write_bytes(evidence_path.read_bytes() + b":overwritten")
        report = self._report()
        cell = self._cell(report, "matrix-v002", "front")
        self.assertEqual(cell["status"], "stale")
        self.assertTrue(
            any(
                item["code"] == "evidence-binding"
                and "mismatch" in item["message"]
                for item in cell["issues"]
            )
        )

    def test_global_layer_and_critical_semantic_failures_are_reported(self) -> None:
        def fail_global(spec: dict) -> None:
            self._review_for(spec, "blockout")["aiVisionScore"] = 0.6

        def fail_layer(spec: dict) -> None:
            self._review_for(spec, "surface-pass")["layerScores"][
                "materialSurface"
            ] = 0.5

        def fail_feature(spec: dict) -> None:
            feature = self._review_for(spec, "blockout")["featureReviews"][0]
            feature["visible"] = False
            feature["score"] = 0.4

        self._rewrite_spec(self.variant_paths["matrix-v001"], fail_global)
        self._rewrite_spec(self.variant_paths["matrix-v002"], fail_layer)
        self._rewrite_spec(self.variant_paths["matrix-v003"], fail_feature)
        report = self._report()
        checks = (
            ("matrix-v001", "front", "global-ai-vision-failed"),
            ("matrix-v002", "detail", "layer-score-failed"),
            ("matrix-v003", "front", "semantic-feature-failed"),
        )
        for asset_id, viewpoint_id, code in checks:
            with self.subTest(asset_id=asset_id, viewpoint_id=viewpoint_id):
                cell = self._cell(report, asset_id, viewpoint_id)
                self.assertEqual(cell["status"], "failing")
                self.assertTrue(any(item["code"] == code for item in cell["issues"]))

    def test_latest_review_for_pass_takes_precedence(self) -> None:
        path = self.variant_paths["matrix-v001"]

        def add_older_failure(spec: dict) -> None:
            failing = copy.deepcopy(self._review_for(spec, "blockout"))
            failing["aiVisionScore"] = 0.1
            spec["reviewHistory"].insert(0, failing)

        self._rewrite_spec(path, add_older_failure)
        self.assertEqual(
            self._cell(self._report(), "matrix-v001", "front")["status"],
            "passing",
        )

        def add_latest_failure(spec: dict) -> None:
            failing = copy.deepcopy(self._review_for(spec, "blockout"))
            failing["aiVisionScore"] = 0.1
            spec["reviewHistory"].append(failing)

        self._rewrite_spec(path, add_latest_failure)
        cell = self._cell(self._report(), "matrix-v001", "front")
        self.assertEqual(cell["status"], "failing")
        self.assertEqual(cell["review"]["historyIndex"], 3)

    def test_malformed_and_non_finite_inputs_exit_two_with_json_error(self) -> None:
        cases = (
            ("malformed", "{"),
            ("non-finite", '{"schemaVersion": NaN}'),
        )
        for name, payload in cases:
            with self.subTest(name=name):
                self.manifest_path.write_text(payload, encoding="utf-8")
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = main(
                        [str(self.base_path), str(self.manifest_path)]
                    )
                result = json.loads(stdout.getvalue())
                self.assertEqual(exit_code, 2)
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"]["code"], "invalid-input")
                self._write_fixture()

    def test_invalid_templates_exit_two_with_json_error(self) -> None:
        cases = (
            ("unmatched-brace", "{"),
            ("format-spec", "{assetId:>10}"),
            ("conversion", "{assetId!r}"),
        )
        for name, template in cases:
            with self.subTest(name=name):
                manifest = self._load(self.manifest_path)
                manifest["visualRegressionMatrix"]["viewpoints"][0][
                    "renderPathTemplate"
                ] = template
                self._write_json(self.manifest_path, manifest)
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = main(
                        [str(self.base_path), str(self.manifest_path)]
                    )
                result = json.loads(stdout.getvalue())
                self.assertEqual(exit_code, 2)
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"]["code"], "invalid-input")
                self._write_fixture()

    def test_manifest_count_requires_a_positive_non_boolean_integer(self) -> None:
        cases = (
            ("boolean-equal-to-one", True, 1, "positive integer"),
            ("string", "3", 3, "positive integer"),
            ("negative", -1, 3, "positive integer"),
            ("count-mismatch", 2, 3, "equal the number"),
        )
        for name, count, variant_count, message in cases:
            with self.subTest(name=name):
                manifest = self._load(self.manifest_path)
                manifest["variants"] = manifest["variants"][:variant_count]
                manifest["count"] = count
                self._write_json(self.manifest_path, manifest)
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = main(
                        [str(self.base_path), str(self.manifest_path)]
                    )
                result = json.loads(stdout.getvalue())
                self.assertEqual(exit_code, 2)
                self.assertEqual(result["error"]["code"], "invalid-input")
                self.assertIn(message, result["error"]["message"])
                self._write_fixture()

    def test_json_output_is_byte_identical_across_working_directories(self) -> None:
        command = [
            sys.executable,
            str(SCRIPTS / "visual_regression_matrix.py"),
            str(self.base_path.resolve()),
            str(self.manifest_path.resolve()),
        ]
        from_repository = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        from_fixture = subprocess.run(
            command,
            cwd=self.root,
            check=False,
            capture_output=True,
        )
        self.assertEqual(from_repository.returncode, 0)
        self.assertEqual(from_fixture.returncode, 0)
        self.assertEqual(from_repository.stderr, b"")
        self.assertEqual(from_fixture.stderr, b"")
        self.assertEqual(from_repository.stdout, from_fixture.stdout)

    def test_cli_exit_codes_json_output_and_summary_are_explicit(self) -> None:
        clean_output = self.root / "clean-report.json"
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            clean_exit = main(
                [
                    str(self.base_path),
                    str(self.manifest_path),
                    "--out",
                    str(clean_output),
                    "--summary",
                ]
            )
        self.assertEqual(clean_exit, 0)
        self.assertTrue(self._load(clean_output)["ok"])
        self.assertIn("passing=8", stderr.getvalue())

        shutil.rmtree(self.root / "evidence" / "matrix-v003")
        failing_output = self.root / "failing-report.json"
        failing_exit = main(
            [
                str(self.base_path),
                str(self.manifest_path),
                "--out",
                str(failing_output),
            ]
        )
        self.assertEqual(failing_exit, 1)
        self.assertFalse(self._load(failing_output)["ok"])


if __name__ == "__main__":
    unittest.main()
