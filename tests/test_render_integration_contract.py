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
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SAMPLE = ROOT / "examples" / "render-integration-contract"
sys.path.insert(0, str(SCRIPTS))

from render_integration_contract import (  # noqa: E402
    STATUS_ORDER,
    build_report,
    main,
    report_payload,
)


class RenderIntegrationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="render-contract-")
        self.root = Path(self._temporary.name)
        self.contract_path = self.root / "contract.json"
        self.standalone_path = self.root / "standalone.json"
        self.host_path = self.root / "host.json"
        self._reset()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _reset(self) -> None:
        shutil.copyfile(
            SAMPLE / "render-integration-contract.json",
            self.contract_path,
        )
        shutil.copyfile(
            SAMPLE / "standalone-snapshot.json",
            self.standalone_path,
        )
        shutil.copyfile(SAMPLE / "host-snapshot.json", self.host_path)

    @staticmethod
    def _load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, payload: dict) -> None:
        path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def _mutate(self, path: Path, mutate) -> None:
        payload = self._load(path)
        mutate(payload)
        self._write(path, payload)

    def _report(self) -> dict:
        return build_report(
            self.contract_path.resolve(),
            self.standalone_path.resolve(),
            self.host_path.resolve(),
        )

    @staticmethod
    def _checks(report: dict, code: str, scope: str | None = None) -> list[dict]:
        return [
            item
            for item in report["checks"]
            if item["code"] == code
            and (scope is None or item["scope"] == scope)
        ]

    def _assert_failing(
        self,
        report: dict,
        code: str,
        scope: str | None = None,
    ) -> None:
        checks = self._checks(report, code, scope)
        self.assertTrue(checks, f"missing check code {code}")
        self.assertTrue(
            any(item["status"] == "failing" for item in checks),
            f"{code} did not fail: {checks}",
        )

    def _assert_missing(
        self,
        report: dict,
        code: str,
        scope: str | None = None,
    ) -> None:
        checks = self._checks(report, code, scope)
        self.assertTrue(checks, f"missing check code {code}")
        self.assertTrue(
            any(item["status"] == "missing" for item in checks),
            f"{code} was not missing: {checks}",
        )

    def _run_main(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _assert_exit_two(self, argv: list[str] | None = None) -> dict:
        command = argv or [
            str(self.contract_path),
            str(self.standalone_path),
            str(self.host_path),
        ]
        exit_code, stdout, stderr = self._run_main(command)
        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "invalid-input")
        return result

    @staticmethod
    def _view(payload: dict, view_id: str) -> dict:
        return next(item for item in payload["views"] if item["id"] == view_id)

    @classmethod
    def _semantic(cls, payload: dict, view_id: str, semantic_id: str) -> dict:
        view = cls._view(payload, view_id)
        return next(
            item for item in view["semantics"] if item["id"] == semantic_id
        )

    def test_clean_pass_is_deterministic_and_stably_ordered(self) -> None:
        first = self._report()
        second = self._report()
        self.assertEqual(first, second)
        self.assertEqual(report_payload(first), report_payload(second))
        self.assertTrue(first["ok"])
        self.assertEqual(
            first["summary"],
            {
                "total": 211,
                "missing": 0,
                "stale": 0,
                "passing": 211,
                "failing": 0,
            },
        )
        self.assertEqual(first["policy"]["statusOrder"], list(STATUS_ORDER))
        check_ids = [item["id"] for item in first["checks"]]
        self.assertEqual(len(check_ids), len(set(check_ids)))
        self.assertEqual(
            check_ids[:4],
            [
                "binding.standalone.source",
                "binding.standalone.factory",
                "binding.host.source",
                "binding.host.factory",
            ],
        )
        self.assertEqual(
            [item["status"] for item in first["checks"]],
            ["passing"] * 211,
        )

    def test_output_is_byte_identical_across_working_directories(self) -> None:
        command = [
            sys.executable,
            str(SCRIPTS / "render_integration_contract.py"),
            str(self.contract_path.resolve()),
            str(self.standalone_path.resolve()),
            str(self.host_path.resolve()),
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

    def test_committed_sample_matches_bindings_and_golden_report(self) -> None:
        contract_path = SAMPLE / "render-integration-contract.json"
        standalone_path = SAMPLE / "standalone-snapshot.json"
        host_path = SAMPLE / "host-snapshot.json"
        contract = self._load(contract_path)
        for binding in ("source", "factory"):
            item = contract["asset"][binding]
            self.assertEqual(
                item["sha256"],
                sha256((ROOT / item["path"]).read_bytes()).hexdigest(),
            )
        report = build_report(contract_path, standalone_path, host_path)
        expected = (SAMPLE / "expected-integration-report.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(report_payload(report), expected)
        self.assertTrue(report["ok"])

    def test_malformed_non_finite_and_numeric_boolean_inputs_exit_two(self) -> None:
        raw_cases = (
            ("malformed", "{"),
            ("nan", '{"schemaVersion": NaN}'),
            ("infinity", '{"schemaVersion": Infinity}'),
            ("overflow", '{"schemaVersion": "1.0", "value": 1e999}'),
            (
                "huge-integer",
                '{"schemaVersion":"1.0","value":' + str(10**400) + "}",
            ),
        )
        for name, raw in raw_cases:
            with self.subTest(name=name):
                self.host_path.write_text(raw, encoding="utf-8")
                result = self._assert_exit_two()
                if name == "huge-integer":
                    self.assertIn("JSON-safe range", result["error"]["message"])
                self._reset()

        self._mutate(
            self.contract_path,
            lambda value: value["renderer"].__setitem__("maxPixelRatio", True),
        )
        result = self._assert_exit_two()
        self.assertIn("finite number", result["error"]["message"])

    def test_schema_kind_sha_duplicate_role_and_identity_errors_exit_two(self) -> None:
        cases = (
            (
                "schema",
                self.contract_path,
                lambda value: value.__setitem__("schemaVersion", "2.0"),
            ),
            (
                "kind",
                self.host_path,
                lambda value: value.__setitem__("kind", "not-a-snapshot"),
            ),
            (
                "contract-sha",
                self.contract_path,
                lambda value: value["asset"]["source"].__setitem__("sha256", "bad"),
            ),
            (
                "snapshot-sha",
                self.host_path,
                lambda value: value["asset"]["factory"].__setitem__("sha256", "bad"),
            ),
            (
                "duplicate-contract-view",
                self.contract_path,
                lambda value: value["views"].append(copy.deepcopy(value["views"][0])),
            ),
            (
                "duplicate-snapshot-target",
                self.host_path,
                lambda value: value["renderTargets"].append(
                    copy.deepcopy(value["renderTargets"][0])
                ),
            ),
            (
                "swapped-role",
                self.host_path,
                lambda value: value.__setitem__("role", "standalone"),
            ),
            (
                "asset-identity",
                self.host_path,
                lambda value: value["asset"].__setitem__("assetId", "other-asset"),
            ),
            (
                "profile-identity",
                self.standalone_path,
                lambda value: value["asset"].__setitem__(
                    "profileId",
                    "other-profile",
                ),
            ),
        )
        for name, path, mutate in cases:
            with self.subTest(name=name):
                self._mutate(path, mutate)
                self._assert_exit_two()
                self._reset()

    def test_unsafe_binding_paths_exit_two(self) -> None:
        unsafe_paths = (
            "/tmp/source.json",
            "C:\\private\\source.json",
            "../source.json",
            "https://example.com/source.json",
            "examples//source.json",
            "examples\\source.json",
        )
        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path):
                self._mutate(
                    self.contract_path,
                    lambda value: value["asset"]["source"].__setitem__(
                        "path",
                        unsafe_path,
                    ),
                )
                result = self._assert_exit_two()
                self.assertIn("safe repository-relative path", result["error"]["message"])
                self._reset()

    def test_symlink_loop_path_exits_two_without_traceback(self) -> None:
        first = self.root / "loop-a"
        second = self.root / "loop-b"
        try:
            first.symlink_to(second.name)
            second.symlink_to(first.name)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        output = self.root / "symlink-error.json"
        exit_code, stdout, stderr = self._run_main(
            [
                str(first),
                str(self.standalone_path),
                str(self.host_path),
                "--out",
                str(output),
            ]
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        result = self._load(output)
        self.assertEqual(result["error"]["code"], "invalid-input")
        self.assertIn("path cannot be resolved", result["error"]["message"])

    def test_nul_path_exits_two_without_traceback(self) -> None:
        output = self.root / "nul-error.json"
        exit_code, stdout, stderr = self._run_main(
            [
                "invalid\x00contract.json",
                str(self.standalone_path),
                str(self.host_path),
                "--out",
                str(output),
            ]
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        result = self._load(output)
        self.assertEqual(result["error"]["code"], "invalid-input")
        self.assertIn("path cannot be resolved", result["error"]["message"])

    def test_deeply_nested_json_exits_two_without_traceback(self) -> None:
        self.contract_path.write_text(
            "[" * 2000 + "0" + "]" * 2000,
            encoding="utf-8",
        )
        output = self.root / "deep-json-error.json"
        exit_code, stdout, stderr = self._run_main(
            [
                str(self.contract_path),
                str(self.standalone_path),
                str(self.host_path),
                "--out",
                str(output),
            ]
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        result = self._load(output)
        self.assertEqual(result["error"]["code"], "invalid-input")
        self.assertIn("invalid JSON", result["error"]["message"])

    def test_initial_input_io_error_honors_output_path(self) -> None:
        output = self.root / "input-io-error.json"
        with patch.object(
            Path,
            "read_bytes",
            side_effect=OSError("input cannot be read"),
        ):
            exit_code, stdout, stderr = self._run_main(
                [
                    str(self.contract_path),
                    str(self.standalone_path),
                    str(self.host_path),
                    "--out",
                    str(output),
                ]
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        result = self._load(output)
        self.assertEqual(result["error"]["code"], "invalid-input")
        self.assertIn("input cannot be read", result["error"]["message"])

    def test_report_hashes_bind_the_exact_evaluated_bytes(self) -> None:
        original_read_bytes = Path.read_bytes
        original_host_bytes = original_read_bytes(self.host_path)
        changed_host = json.loads(original_host_bytes)
        changed_host["renderer"]["outputPassCount"] = 2
        changed_host_bytes = (
            json.dumps(changed_host, indent=2) + "\n"
        ).encode("utf-8")
        read_counts: dict[Path, int] = {}

        def read_once_then_rotate(path: Path) -> bytes:
            resolved = path.resolve()
            data = original_read_bytes(path)
            read_counts[resolved] = read_counts.get(resolved, 0) + 1
            if resolved == self.host_path.resolve():
                path.write_bytes(changed_host_bytes)
            return data

        with patch.object(Path, "read_bytes", new=read_once_then_rotate):
            report = self._report()

        self.assertTrue(report["ok"])
        self.assertEqual(
            report["inputs"]["host"]["sha256"],
            sha256(original_host_bytes).hexdigest(),
        )
        self.assertEqual(
            read_counts,
            {
                self.contract_path.resolve(): 1,
                self.standalone_path.resolve(): 1,
                self.host_path.resolve(): 1,
            },
        )
        self.assertEqual(self.host_path.read_bytes(), changed_host_bytes)
        count_check = next(
            item
            for item in report["checks"]
            if item["id"] == "renderer.host.tone-mapping-count"
        )
        self.assertEqual(count_check["actual"], 1)
        self.assertEqual(count_check["status"], "passing")

    def test_output_path_cannot_overwrite_an_input(self) -> None:
        original = self.host_path.read_bytes()
        exit_code, stdout, stderr = self._run_main(
            [
                str(self.contract_path),
                str(self.standalone_path),
                str(self.host_path),
                "--out",
                str(self.host_path),
            ]
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr, "")
        self.assertEqual(self.host_path.read_bytes(), original)
        result = json.loads(stdout)
        self.assertEqual(result["error"]["code"], "invalid-input")
        self.assertIn("must not overwrite an input file", result["error"]["message"])

    def test_inverted_percentiles_and_contract_bounds_exit_two(self) -> None:
        cases = (
            (
                "view-luminance",
                self.host_path,
                lambda value: self._view(value, "front")["luminance"].update(
                    {"p50": 0.8, "p90": 0.7}
                ),
            ),
            (
                "semantic-luminance",
                self.host_path,
                lambda value: self._semantic(
                    value,
                    "front",
                    "hero-emissive",
                )["luminance"].update({"p50": 0.8, "p90": 0.7}),
            ),
            (
                "frame-time",
                self.host_path,
                lambda value: self._view(value, "front")["performance"].update(
                    {"frameTimeP50Ms": 20.0, "frameTimeP95Ms": 19.0}
                ),
            ),
            (
                "contract-luminance",
                self.contract_path,
                lambda value: value["views"][0].update(
                    {"minP50Luminance": 0.8, "maxP90Luminance": 0.7}
                ),
            ),
            (
                "contract-frame-time",
                self.contract_path,
                lambda value: value["performance"].update(
                    {
                        "maxFrameTimeP50Ms": 30.0,
                        "maxFrameTimeP95Ms": 20.0,
                    }
                ),
            ),
        )
        for name, path, mutate in cases:
            with self.subTest(name=name):
                self._mutate(path, mutate)
                self._assert_exit_two()
                self._reset()

    def test_angle_boundaries_use_reported_precision(self) -> None:
        contract = self._load(self.contract_path)
        contract["angleConsistency"]["minCoverageToMedian"] = 0.666666666667
        contract["angleConsistency"]["maxP90LuminanceSpread"] = 0.3
        for view in contract["views"]:
            view["minCoverage"] = 0.1
            view["minP50Luminance"] = 0.0
        self._write(self.contract_path, contract)

        standalone = self._load(self.standalone_path)
        values = {
            "front": (0.4, 0.2, 0.4),
            "quarter": (0.3, 0.15, 0.25),
            "back": (0.2, 0.05, 0.1),
        }
        for view_id, (coverage, p50, p90) in values.items():
            view = self._view(standalone, view_id)
            view["coverage"] = coverage
            view["luminance"] = {"p50": p50, "p90": p90}
        self._write(self.standalone_path, standalone)

        report = self._report()
        coverage = next(
            item
            for item in report["checks"]
            if item["id"] == "angle.standalone.coverage-consistency"
        )
        luminance = next(
            item
            for item in report["checks"]
            if item["id"] == "angle.standalone.p90-luminance-spread"
        )
        self.assertEqual(coverage["actual"], 0.666666666667)
        self.assertEqual(
            coverage["actual"],
            coverage["expected"]["min"],
        )
        self.assertEqual(coverage["status"], "passing")
        self.assertEqual(luminance["actual"], 0.3)
        self.assertEqual(
            luminance["actual"],
            luminance["expected"]["max"],
        )
        self.assertEqual(luminance["status"], "passing")

    def test_missing_renderer_target_light_layer_view_and_semantic_data(self) -> None:
        standalone = self._load(self.standalone_path)
        standalone.pop("renderer")
        self._write(self.standalone_path, standalone)

        host = self._load(self.host_path)
        host["renderTargets"] = [
            item for item in host["renderTargets"] if item["id"] != "hero-bloom"
        ]
        host["selectiveRendering"]["layers"] = []
        host["selectiveRendering"]["lights"] = []
        host["views"] = [
            item for item in host["views"] if item["id"] != "back"
        ]
        front = self._view(host, "front")
        front["semantics"] = [
            item
            for item in front["semantics"]
            if item["id"] != "hero-emissive"
        ]
        self._write(self.host_path, host)

        report = self._report()
        self.assertFalse(report["ok"])
        self._assert_missing(report, "tone-mapping", "standalone")
        self._assert_missing(report, "render-target", "host")
        self._assert_missing(report, "selective-layer", "host")
        self._assert_missing(report, "selective-light", "host")
        self._assert_missing(report, "view", "host")
        self._assert_missing(report, "semantic-system", "host")

    def test_stale_source_and_factory_bindings_are_classified(self) -> None:
        standalone = self._load(self.standalone_path)
        standalone["asset"]["source"]["path"] = "examples/repolis-tree/stale.json"
        self._write(self.standalone_path, standalone)
        host = self._load(self.host_path)
        host["asset"]["factory"]["sha256"] = "0" * 64
        self._write(self.host_path, host)

        report = self._report()
        source = self._checks(report, "source-binding", "standalone")
        factory = self._checks(report, "factory-binding", "host")
        self.assertEqual(source[0]["status"], "stale")
        self.assertEqual(factory[0]["status"], "stale")
        self.assertEqual(report["summary"]["stale"], 2)

    def test_renderer_output_and_exposure_failures(self) -> None:
        def fail_renderer(value: dict) -> None:
            renderer = value["renderer"]
            renderer["toneMapping"] = "NoToneMapping"
            renderer["outputColorSpace"] = "LinearSRGBColorSpace"
            renderer["exposure"] = 1.2
            renderer["outputPassCount"] = 2
            renderer["pixelRatio"] = 3.0

        self._mutate(self.host_path, fail_renderer)
        report = self._report()
        for code in (
            "tone-mapping",
            "output-color-space",
            "exposure-delta",
            "tone-mapping-count",
            "pixel-ratio",
        ):
            self._assert_failing(report, code)

    def test_render_target_type_color_depth_scale_and_pixel_failures(self) -> None:
        def fail_target(value: dict) -> None:
            target = next(
                item
                for item in value["renderTargets"]
                if item["id"] == "hero-bloom"
            )
            target.update(
                {
                    "type": "UnsignedByteType",
                    "colorSpace": "SRGBColorSpace",
                    "depthBuffer": True,
                    "scale": 1.5,
                    "width": 2000,
                    "height": 2000,
                    "pixelCount": 4000000,
                }
            )

        self._mutate(self.host_path, fail_target)
        report = self._report()
        for code in (
            "render-target-type",
            "render-target-color-space",
            "render-target-depth",
            "render-target-scale",
            "render-target-pixels",
        ):
            self._assert_failing(report, code, "host")

    def test_selective_layer_light_ownership_and_town_spill_failures(self) -> None:
        def fail_selective(value: dict) -> None:
            layer = next(
                item
                for item in value["selectiveRendering"]["layers"]
                if item["id"] == "hero-bloom"
            )
            layer["index"] = 3
            layer["owner"] = "host"
            layer["members"] = ["town"]
            light = next(
                item
                for item in value["selectiveRendering"]["lights"]
                if item["id"] == "hero-energy-light"
            )
            light["owner"] = "host"
            light["layers"] = ["town"]
            light["townSpill"] = 0.2

        self._mutate(self.host_path, fail_selective)
        report = self._report()
        for code in (
            "layer-index",
            "layer-owner",
            "layer-required-members",
            "layer-forbidden-members",
            "light-owner",
            "light-required-layers",
            "light-forbidden-layers",
            "town-light-spill",
        ):
            self._assert_failing(report, code, "host")

    def test_view_semantic_black_clipping_and_angle_failures(self) -> None:
        def fail_views(value: dict) -> None:
            back = self._view(value, "back")
            back["blackFrame"] = True
            back["coverage"] = 0.1
            back["luminance"]["p90"] = 0.4
            front = self._view(value, "front")
            front["clipped"] = True
            emissive = self._semantic(value, "front", "hero-emissive")
            emissive["visible"] = False
            emissive["coverage"] = 0.001
            emissive["luminance"]["p50"] = 0.01
            emissive["luminance"]["p90"] = 0.1
            proxy = self._semantic(value, "quarter", "hero-occlusion-proxy")
            proxy["coverage"] = 0.5

        self._mutate(self.host_path, fail_views)
        report = self._report()
        for code in (
            "black-frame",
            "view-clipping",
            "view-coverage",
            "semantic-visibility",
            "semantic-coverage",
            "semantic-luminance-p50",
            "semantic-luminance-p90",
            "angle-coverage-consistency",
            "angle-luminance-spread",
        ):
            self._assert_failing(report, code, "host")

    def test_town_exposure_drift_fails(self) -> None:
        def drift_town(value: dict) -> None:
            for view_id in ("front", "quarter", "back"):
                town = self._semantic(value, view_id, "town")
                town["luminance"]["p50"] += 0.1

        self._mutate(self.host_path, drift_town)
        report = self._report()
        self._assert_failing(
            report,
            "town-exposure-invariance",
            "cross-snapshot",
        )

    def test_performance_direction_spread_console_and_network_failures(self) -> None:
        def fail_runtime(value: dict) -> None:
            front = self._view(value, "front")["performance"]
            front.update(
                {
                    "calls": 181,
                    "triangles": 920000,
                    "fps": 49.0,
                    "frameTimeP50Ms": 19.0,
                    "frameTimeP95Ms": 30.0,
                }
            )
            value["errors"] = {"console": 1, "network": 2}

        self._mutate(self.host_path, fail_runtime)
        report = self._report()
        for code in (
            "draw-calls",
            "triangles",
            "fps",
            "frame-time-p50",
            "frame-time-p95",
            "camera-direction-calls-spread",
            "camera-direction-triangles-spread",
            "camera-direction-frame-time-p95-spread",
            "console-errors",
            "network-errors",
        ):
            self._assert_failing(report, code, "host")

    def test_allowed_host_specific_differences_and_extra_data_pass(self) -> None:
        report = self._report()
        self.assertTrue(report["ok"])
        self.assertEqual(
            report["policy"]["hostDifferences"],
            "explicit-contract-thresholds-only",
        )
        check_ids = [item["id"] for item in report["checks"]]
        self.assertFalse(any("host-picking" in item for item in check_ids))
        self.assertFalse(any("host-overview" in item for item in check_ids))
        self.assertFalse(any("town-sun" in item for item in check_ids))
        host_scale = next(
            item
            for item in report["checks"]
            if item["id"] == "target.host.hero-bloom.scale"
        )
        self.assertEqual(host_scale["actual"], 0.75)
        self.assertEqual(host_scale["status"], "passing")

    def test_browser_helper_normalizes_runtime_values_and_view_stats(self) -> None:
        script = r"""
            import {
              canonicalColorSpace,
              captureViewPerformance,
              createRenderIntegrationSnapshot,
              snapshotRenderTarget,
              summarizeFrameTimes,
            } from './browser-snapshot-helper.js';

            const renderer = {
              outputColorSpace: 'srgb',
              toneMappingExposure: 1,
              getPixelRatio: () => 2,
              info: { render: { calls: 101, triangles: 1001 } },
            };
            const frontPerformance = captureViewPerformance(renderer, [16, 17, 18]);
            renderer.info.render.calls = 202;
            renderer.info.render.triangles = 2002;
            const backPerformance = captureViewPerformance(renderer, [20, 21, 22]);
            renderer.info.render.calls = 999;
            renderer.info.render.triangles = 9999;

            const target = snapshotRenderTarget({
              id: 'hero-bloom',
              type: 'HalfFloatType',
              colorSpace: 'srgb-linear',
              depthBuffer: false,
              scale: 1,
              width: 100,
              height: 50,
            });
            const baseView = {
              blackFrame: false,
              clipped: false,
              coverage: 0.4,
              luminance: { p50: 0.3, p90: 0.6 },
              semantics: [],
            };
            const snapshot = createRenderIntegrationSnapshot({
              role: 'host',
              snapshotId: 'helper-test',
              asset: {
                assetId: 'repolis-tree',
                profileId: 'repolis-living-archive',
                source: { path: 'source.json', sha256: '1'.repeat(64) },
                factory: { path: 'factory.js', sha256: '2'.repeat(64) },
              },
              renderer,
              toneMapping: 'ACESFilmicToneMapping',
              outputPassCount: 1,
              renderTargets: [target],
              views: [
                {
                  ...baseView,
                  id: 'front',
                  cameraId: 'front',
                  performance: frontPerformance,
                },
                {
                  ...baseView,
                  id: 'back',
                  cameraId: 'back',
                  performance: backPerformance,
                },
              ],
            });

            const invalidSamples = [null, true, '16', 0, -1, Infinity, NaN];
            const rejectedSamples = invalidSamples.map((value) => {
              try {
                summarizeFrameTimes([value]);
                return false;
              } catch {
                return true;
              }
            });
            let missingPerformanceRejected = false;
            try {
              createRenderIntegrationSnapshot({
                role: 'host',
                snapshotId: 'missing-performance',
                asset: snapshot.asset,
                renderer,
                toneMapping: 'ACESFilmicToneMapping',
                outputPassCount: 1,
                views: [{ ...baseView, id: 'front', cameraId: 'front' }],
              });
            } catch {
              missingPerformanceRejected = true;
            }

            console.log(JSON.stringify({
              rendererColorSpace: snapshot.renderer.outputColorSpace,
              targetColorSpace: snapshot.renderTargets[0].colorSpace,
              noColorSpace: canonicalColorSpace(''),
              viewCalls: snapshot.views.map((view) => view.performance.calls),
              viewTriangles: snapshot.views.map(
                (view) => view.performance.triangles,
              ),
              rejectedSamples,
              missingPerformanceRejected,
            }));
        """
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            cwd=SAMPLE,
            check=True,
            capture_output=True,
            text=True,
        )
        probe = json.loads(result.stdout)
        self.assertEqual(probe["rendererColorSpace"], "SRGBColorSpace")
        self.assertEqual(probe["targetColorSpace"], "LinearSRGBColorSpace")
        self.assertEqual(probe["noColorSpace"], "NoColorSpace")
        self.assertEqual(probe["viewCalls"], [101, 202])
        self.assertEqual(probe["viewTriangles"], [1001, 2002])
        self.assertEqual(probe["rejectedSamples"], [True] * 7)
        self.assertTrue(probe["missingPerformanceRejected"])

    def test_ai_authority_is_explicit_and_diagnostics_cannot_approve(self) -> None:
        report = self._report()
        self.assertEqual(report["authority"]["finalVisualAuthority"], "ai-vision")
        self.assertEqual(
            report["authority"]["runtimeMetrics"],
            "diagnostic-gates-only",
        )
        self.assertFalse(
            report["authority"]["runtimeMetricsCanApproveVisualQuality"]
        )
        self.assertFalse(report["authority"]["integrationPassIsVisualApproval"])
        self.assertNotIn("aiVisionScore", report)

        self._mutate(
            self.host_path,
            lambda value: value["renderer"].__setitem__("outputPassCount", 2),
        )
        failing = self._report()
        self.assertFalse(failing["ok"])
        self.assertFalse(
            failing["authority"]["runtimeMetricsCanApproveVisualQuality"]
        )

    def test_public_docs_expose_copy_paste_workflow_and_skill_gate(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (
            ROOT / "skills" / "object-to-threejs-procedural" / "SKILL.md"
        ).read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
        reference = (
            ROOT
            / "skills"
            / "object-to-threejs-procedural"
            / "references"
            / "render-integration-contract.md"
        ).read_text(encoding="utf-8")
        self.assertIn("## Verify a model inside a host app", readme)
        self.assertIn(
            "examples/render-integration-contract/standalone-snapshot.json",
            readme,
        )
        for code in ("tone-mapping-count", "town-light-spill", "view-coverage"):
            self.assertIn(code, readme)
            self.assertIn(code, reference)
        self.assertIn(
            "python3 scripts/render_integration_contract.py",
            readme,
        )
        self.assertIn(
            "python3 ../../scripts/render_integration_contract.py",
            skill,
        )
        self.assertIn("After `optimization-pass`", skill)
        self.assertIn("before production acceptance", skill)
        self.assertIn(
            "python3 scripts/render_integration_contract.py",
            guide,
        )
        self.assertIn("runtimeMetricsCanApproveVisualQuality", reference)

    def test_cli_exit_codes_output_and_bounded_summary(self) -> None:
        output = self.root / "report.json"
        exit_code, stdout, stderr = self._run_main(
            [
                str(self.contract_path),
                str(self.standalone_path),
                str(self.host_path),
                "--out",
                str(output),
                "--summary",
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(len(stderr.splitlines()), 2)
        self.assertTrue(self._load(output)["ok"])

        self._mutate(
            self.host_path,
            lambda value: value["renderer"].__setitem__("outputPassCount", 2),
        )
        exit_code, stdout, stderr = self._run_main(
            [
                str(self.contract_path),
                str(self.standalone_path),
                str(self.host_path),
                "--summary",
            ]
        )
        self.assertEqual(exit_code, 1)
        self.assertFalse(json.loads(stdout)["ok"])
        self.assertLessEqual(len(stderr.splitlines()), 19)
        self.assertIn("tone-mapping-count", stderr)

        self.host_path.write_text("{", encoding="utf-8")
        exit_code, stdout, stderr = self._run_main(
            [
                str(self.contract_path),
                str(self.standalone_path),
                str(self.host_path),
                "--summary",
            ]
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(stdout)["error"]["code"], "invalid-input")
        self.assertEqual(len(stderr.splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
