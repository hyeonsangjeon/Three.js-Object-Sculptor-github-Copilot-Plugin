#!/usr/bin/env python3
"""Build a deterministic AI-authoritative visual regression matrix."""

from __future__ import annotations

import argparse
import json
import re
import string
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sculpt_pass_orchestrator import VISUAL_PASS_IDS, pass_order, review_completes_pass
from validate_sculpt_spec import load_spec, validate_spec
from verify_release import score_meets_threshold
from visual_evidence_hashes import (
    LATEST_REVIEW_SELECTION,
    authoritative_reviews,
    file_sha256,
    is_remote_or_virtual_path,
    review_visual_evidence_failures,
)
from visual_feature_gate import feature_gate_failures, feature_targets_for_pass


REPORT_SCHEMA_VERSION = "1.0"
MANIFEST_CONFIG_VERSION = "1.0"
REPORT_KIND = "sculpt-dna-visual-regression-matrix"
CONFIG_FIELD = "visualRegressionMatrix"
REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_ORDER = ("missing", "stale", "passing", "failing")
STATUS_PRECEDENCE = ("missing", "stale", "failing")
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
TEMPLATE_FIELDS = {
    "assetId",
    "assetRole",
    "passId",
    "variantIndex",
    "viewpointId",
}


class MatrixInputError(ValueError):
    """Raised when a matrix cannot be enumerated safely."""


@dataclass(frozen=True)
class Viewpoint:
    id: str
    pass_id: str
    camera_view: str
    render_template: str | None
    comparison_template: str | None
    feature_ids: tuple[str, ...]


@dataclass
class Asset:
    id: str
    role: str
    path: Path
    variant_index: int
    manifest_item: dict[str, Any] | None
    spec: dict[str, Any] | None = None
    digest: str | None = None
    load_error: str | None = None
    validation_errors: tuple[str, ...] = ()


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant {value}")

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
        )
    except OSError as exc:
        raise MatrixInputError(f"{label} cannot be read: {path}: {exc}") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise MatrixInputError(f"{label} is invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MatrixInputError(f"{label} must contain a JSON object: {path}")
    return payload


def display_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise MatrixInputError(
            f"{label} must match {ID_PATTERN.pattern!r}; got {value!r}"
        )
    return value


def validate_template(template: Any, label: str) -> str | None:
    if template is None:
        return None
    if not isinstance(template, str) or not template.strip():
        raise MatrixInputError(f"{label} must be a non-empty string")
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise MatrixInputError(f"{label} is not a valid format template: {exc}") from exc
    for _literal, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if (
            field_name not in TEMPLATE_FIELDS
            or format_spec
            or conversion
        ):
            raise MatrixInputError(
                f"{label} may use only simple placeholders: "
                + ", ".join(sorted(TEMPLATE_FIELDS))
            )
    return template


def parse_feature_ids(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise MatrixInputError(f"{label} must be an array")
    feature_ids = [require_id(item, f"{label}[]") for item in value]
    if len(feature_ids) != len(set(feature_ids)):
        raise MatrixInputError(f"{label} must not contain duplicates")
    return tuple(sorted(feature_ids))


def viewpoint_from_payload(payload: Any, index: int) -> Viewpoint:
    label = f"{CONFIG_FIELD}.viewpoints[{index}]"
    if not isinstance(payload, dict):
        raise MatrixInputError(f"{label} must be an object")
    viewpoint_id = require_id(payload.get("id"), f"{label}.id")
    pass_id = require_id(payload.get("passId"), f"{label}.passId")
    camera_view = payload.get("cameraView", viewpoint_id)
    if not isinstance(camera_view, str) or not camera_view.strip():
        raise MatrixInputError(f"{label}.cameraView must be a non-empty string")
    return Viewpoint(
        id=viewpoint_id,
        pass_id=pass_id,
        camera_view=camera_view,
        render_template=validate_template(
            payload.get("renderPathTemplate"),
            f"{label}.renderPathTemplate",
        ),
        comparison_template=validate_template(
            payload.get("comparisonPathTemplate"),
            f"{label}.comparisonPathTemplate",
        ),
        feature_ids=parse_feature_ids(payload.get("featureIds"), f"{label}.featureIds"),
    )


def parse_cli_viewpoint(
    value: str,
    *,
    render_template: str | None,
    comparison_template: str | None,
    feature_ids: tuple[str, ...],
) -> Viewpoint:
    separator = "=" if "=" in value else ":"
    parts = value.split(separator, 1)
    if len(parts) != 2 or not all(parts):
        raise MatrixInputError(
            "--viewpoint must use VIEWPOINT_ID=PASS_ID, for example front=surface-pass"
        )
    viewpoint_id = require_id(parts[0], "--viewpoint VIEWPOINT_ID")
    pass_id = require_id(parts[1], "--viewpoint PASS_ID")
    return Viewpoint(
        id=viewpoint_id,
        pass_id=pass_id,
        camera_view=viewpoint_id,
        render_template=render_template,
        comparison_template=comparison_template,
        feature_ids=feature_ids,
    )


def configured_viewpoints(
    manifest: dict[str, Any],
    cli_values: list[str],
    *,
    render_template: str | None,
    comparison_template: str | None,
    feature_ids: tuple[str, ...],
) -> list[Viewpoint]:
    config = manifest.get(CONFIG_FIELD)
    if config is not None and cli_values:
        raise MatrixInputError(
            f"use either manifest {CONFIG_FIELD}.viewpoints or --viewpoint, not both"
        )
    if config is not None:
        if not isinstance(config, dict):
            raise MatrixInputError(f"{CONFIG_FIELD} must be an object")
        if config.get("schemaVersion") != MANIFEST_CONFIG_VERSION:
            raise MatrixInputError(
                f"{CONFIG_FIELD}.schemaVersion must be {MANIFEST_CONFIG_VERSION!r}"
            )
        payloads = config.get("viewpoints")
        if not isinstance(payloads, list) or not payloads:
            raise MatrixInputError(f"{CONFIG_FIELD}.viewpoints must be a non-empty array")
        viewpoints = [
            viewpoint_from_payload(payload, index)
            for index, payload in enumerate(payloads)
        ]
    else:
        if not cli_values:
            raise MatrixInputError(
                f"no viewpoints configured; add {CONFIG_FIELD}.viewpoints "
                "or repeat --viewpoint VIEWPOINT_ID=PASS_ID"
            )
        viewpoints = [
            parse_cli_viewpoint(
                value,
                render_template=render_template,
                comparison_template=comparison_template,
                feature_ids=feature_ids,
            )
            for value in cli_values
        ]
    ids = [item.id for item in viewpoints]
    if len(ids) != len(set(ids)):
        raise MatrixInputError("viewpoint ids must be unique")
    return sorted(viewpoints, key=lambda item: item.id)


def resolve_variant_path(manifest_path: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise MatrixInputError(f"{label} must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute():
        raise MatrixInputError(f"{label} must be relative to the curated manifest")
    root = manifest_path.parent.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise MatrixInputError(f"{label} escapes the curated manifest directory") from exc
    return resolved


def build_assets(
    base_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> list[Asset]:
    variants = manifest.get("variants")
    if not isinstance(variants, list) or not variants:
        raise MatrixInputError("manifest.variants must be a non-empty array")
    count = manifest.get("count")
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count < 1
    ):
        raise MatrixInputError("manifest.count must be a positive integer")
    if count != len(variants):
        raise MatrixInputError("manifest.count must equal the number of variants")

    variant_assets: list[Asset] = []
    seen_ids: set[str] = set()
    for position, item in enumerate(variants, start=1):
        label = f"manifest.variants[{position - 1}]"
        if not isinstance(item, dict):
            raise MatrixInputError(f"{label} must be an object")
        variant_id = require_id(item.get("variantId"), f"{label}.variantId")
        if variant_id == "base":
            raise MatrixInputError("variantId 'base' is reserved for the base asset")
        if variant_id in seen_ids:
            raise MatrixInputError(f"duplicate variantId {variant_id!r}")
        seen_ids.add(variant_id)
        curated_index = item.get("curatedIndex", position)
        if (
            not isinstance(curated_index, int)
            or isinstance(curated_index, bool)
            or curated_index < 1
        ):
            raise MatrixInputError(f"{label}.curatedIndex must be a positive integer")
        variant_assets.append(
            Asset(
                id=variant_id,
                role="variant",
                path=resolve_variant_path(
                    manifest_path,
                    item.get("path"),
                    f"{label}.path",
                ),
                variant_index=curated_index,
                manifest_item=item,
            )
        )
    variant_assets.sort(key=lambda item: item.id)
    return [
        Asset(
            id="base",
            role="base",
            path=base_path,
            variant_index=0,
            manifest_item=None,
        ),
        *variant_assets,
    ]


def load_asset(asset: Asset) -> None:
    try:
        asset.digest = file_sha256(asset.path)
        asset.spec = load_spec(asset.path)
    except (OSError, ValueError) as exc:
        asset.load_error = str(exc)
        return
    errors, _warnings = validate_spec(asset.spec, asset.path)
    asset.validation_errors = tuple(sorted(set(errors)))


def issue(kind: str, code: str, message: str) -> dict[str, str]:
    return {"kind": kind, "code": code, "message": message}


def classify_validation_error(message: str) -> str:
    lowered = message.lower()
    if "mismatch" in lowered or "stale" in lowered:
        return "stale"
    if "missing" in lowered or "is required" in lowered or "does not exist" in lowered:
        return "missing"
    return "failing"


def visual_acceptance(spec: dict[str, Any]) -> dict[str, Any]:
    loop = spec.get("selfCorrectLoop")
    if not isinstance(loop, dict):
        return {}
    acceptance = loop.get("visualAcceptance")
    return acceptance if isinstance(acceptance, dict) else {}


def numeric_threshold(spec: dict[str, Any], review: dict[str, Any]) -> float:
    acceptance = visual_acceptance(spec)
    declared = acceptance.get("threshold")
    reviewed = review.get("visualAcceptanceThreshold")
    thresholds = [
        float(value)
        for value in (declared, reviewed)
        if score_meets_threshold(value, 0.0)
    ]
    return max(thresholds, default=0.7)


def required_layers(spec: dict[str, Any]) -> tuple[str, ...]:
    acceptance = visual_acceptance(spec)
    if acceptance.get("layerScoresRequired") is not True:
        return ()
    values = acceptance.get("requiredLayerScores")
    if not isinstance(values, list):
        return ()
    return tuple(sorted({item for item in values if isinstance(item, str) and item}))


def selected_feature_ids(spec: dict[str, Any], viewpoint: Viewpoint) -> tuple[str, ...]:
    if viewpoint.feature_ids:
        return viewpoint.feature_ids
    return tuple(
        sorted(
            {
                target["id"]
                for target in feature_targets_for_pass(spec, viewpoint.pass_id)
                if isinstance(target.get("id"), str)
                and (
                    target.get("tier") == "critical"
                    or target.get("mustPass") is True
                )
            }
        )
    )


def feature_minimum(
    spec: dict[str, Any],
    target: dict[str, Any] | None,
    global_threshold: float,
) -> float:
    target_minimum = target.get("minimumScore") if isinstance(target, dict) else None
    if score_meets_threshold(target_minimum, 0.0):
        return float(target_minimum)
    acceptance = visual_acceptance(spec)
    policy = acceptance.get("featureReviewPolicy")
    policy = policy if isinstance(policy, dict) else {}
    default_threshold = policy.get("criticalDefaultThreshold")
    if score_meets_threshold(default_threshold, 0.0):
        return float(default_threshold)
    return global_threshold


def format_expected_path(
    template: str | None,
    *,
    actual: Any,
    asset: Asset,
    viewpoint: Viewpoint,
    kind: str,
) -> str:
    if template is None:
        if isinstance(actual, str) and actual.strip():
            return actual
        return (
            f"visual-regression/{asset.id}/"
            f"{viewpoint.id}-{kind}.png"
        )
    context = {
        "assetId": asset.id,
        "assetRole": asset.role,
        "passId": viewpoint.pass_id,
        "variantIndex": asset.variant_index,
        "viewpointId": viewpoint.id,
    }
    try:
        rendered = template.format(**context)
    except (KeyError, IndexError, ValueError) as exc:
        raise MatrixInputError(
            f"{kind} path template could not be rendered: {exc}"
        ) from exc
    if (
        not rendered
        or is_remote_or_virtual_path(rendered)
        or Path(rendered).is_absolute()
        or ".." in PurePosixPath(rendered).parts
    ):
        raise MatrixInputError(
            f"{kind} path template produced an unsafe repository-relative path: "
            f"{rendered!r}"
        )
    return PurePosixPath(rendered).as_posix()


def promotion_issues(
    asset: Asset,
    manifest: dict[str, Any],
) -> list[dict[str, str]]:
    if asset.role != "variant":
        return []
    item = asset.manifest_item or {}
    spec = asset.spec or {}
    provenance = spec.get("variantProvenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    failures: list[dict[str, str]] = []
    if manifest.get("previewMode") is True or item.get("previewMode") is True:
        failures.append(
            issue(
                "failing",
                "preview-variant",
                "preview variants are not promoted visual-regression targets",
            )
        )
    for label, status in (
        ("manifest variant", item.get("passGateStatus")),
        ("variant provenance", provenance.get("passGateStatus")),
    ):
        if status != "evidence-backed-production":
            failures.append(
                issue(
                    "failing",
                    "variant-not-promoted",
                    f"{label} passGateStatus must be 'evidence-backed-production'",
                )
            )
    return failures


def build_cell(
    asset: Asset,
    viewpoint: Viewpoint,
    manifest: dict[str, Any],
    source_binding_stale: bool,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    layer_results: list[dict[str, Any]] = []
    feature_results: list[dict[str, Any]] = []
    review_summary: dict[str, Any] | None = None
    actual = {
        "cameraView": None,
        "renderScreenshot": None,
        "comparisonImage": None,
        "renderSha256": None,
        "comparisonSha256": None,
    }

    if source_binding_stale:
        issues.append(
            issue(
                "stale",
                "source-spec-sha256-mismatch",
                "manifest.sourceSpecSha256 does not match the current base spec",
            )
        )
    if asset.load_error is not None or asset.spec is None:
        issues.append(
            issue(
                "missing",
                "asset-spec-unavailable",
                f"asset spec is unavailable: {asset.load_error or asset.path}",
            )
        )
        expected_render = format_expected_path(
            viewpoint.render_template,
            actual=None,
            asset=asset,
            viewpoint=viewpoint,
            kind="render",
        )
        expected_comparison = format_expected_path(
            viewpoint.comparison_template,
            actual=None,
            asset=asset,
            viewpoint=viewpoint,
            kind="comparison",
        )
    else:
        spec = asset.spec
        issues.extend(promotion_issues(asset, manifest))
        for validation_error in asset.validation_errors:
            issues.append(
                issue(
                    classify_validation_error(validation_error),
                    "spec-validation",
                    validation_error,
                )
            )

        if viewpoint.pass_id not in pass_order(spec):
            issues.append(
                issue(
                    "failing",
                    "unknown-review-pass",
                    f"pass {viewpoint.pass_id!r} is not declared by this asset",
                )
            )

        authoritative = authoritative_reviews(spec)
        selected = authoritative.get(viewpoint.pass_id)
        review = selected[1] if selected is not None else None
        history_index = selected[0] if selected is not None else None
        visual = review.get("visualEvidence") if isinstance(review, dict) else None
        visual = visual if isinstance(visual, dict) else {}
        for field in actual:
            actual[field] = visual.get(field)
        expected_render = format_expected_path(
            viewpoint.render_template,
            actual=actual["renderScreenshot"],
            asset=asset,
            viewpoint=viewpoint,
            kind="render",
        )
        expected_comparison = format_expected_path(
            viewpoint.comparison_template,
            actual=actual["comparisonImage"],
            asset=asset,
            viewpoint=viewpoint,
            kind="comparison",
        )

        if review is None:
            issues.append(
                issue(
                    "missing",
                    "authoritative-review-missing",
                    f"no latest authoritative review exists for pass {viewpoint.pass_id!r}",
                )
            )
        else:
            threshold = numeric_threshold(spec, review)
            review_summary = {
                "historyIndex": history_index,
                "reviewId": visual.get("reviewId"),
                "reviewedAt": visual.get("reviewedAt"),
                "action": review.get("action"),
                "aiVisionScore": review.get("aiVisionScore"),
                "requiredThreshold": threshold,
            }
            if review.get("action") != "continue":
                issues.append(
                    issue(
                        "failing",
                        "review-action-failed",
                        "latest authoritative review action must be 'continue'",
                    )
                )
            score = review.get("aiVisionScore")
            if not score_meets_threshold(score, threshold):
                issues.append(
                    issue(
                        "failing",
                        "global-ai-vision-failed",
                        f"AI vision score {score!r} is below required threshold {threshold}",
                    )
                )
            declared_threshold = visual_acceptance(spec).get("threshold")
            review_threshold = review.get("visualAcceptanceThreshold")
            if (
                score_meets_threshold(declared_threshold, 0.0)
                and not score_meets_threshold(review_threshold, float(declared_threshold))
            ):
                issues.append(
                    issue(
                        "failing",
                        "review-threshold-below-policy",
                        "review visualAcceptanceThreshold is below the spec policy",
                    )
                )

            camera = visual.get("cameraView")
            if not isinstance(camera, str) or not camera.strip():
                issues.append(
                    issue(
                        "missing",
                        "camera-view-missing",
                        f"review does not identify required camera {viewpoint.camera_view!r}",
                    )
                )
            elif camera != viewpoint.camera_view:
                issues.append(
                    issue(
                        "stale",
                        "camera-view-mismatch",
                        f"review camera {camera!r} does not match {viewpoint.camera_view!r}",
                    )
                )

            for field, expected in (
                ("renderScreenshot", expected_render),
                ("comparisonImage", expected_comparison),
            ):
                value = visual.get(field)
                if not isinstance(value, str) or not value.strip():
                    issues.append(
                        issue(
                            "missing",
                            f"{field}-missing",
                            f"{field} is required for this matrix cell",
                        )
                    )
                elif value != expected:
                    issues.append(
                        issue(
                            "stale",
                            f"{field}-path-mismatch",
                            f"{field} records {value!r}, expected {expected!r}",
                        )
                    )

            for failure in review_visual_evidence_failures(
                spec,
                visual,
                asset.path,
                require_local=True,
            ):
                issues.append(
                    issue(
                        classify_validation_error(failure),
                        "evidence-binding",
                        failure,
                    )
                )

            scores = review.get("layerScores")
            scores = scores if isinstance(scores, dict) else {}
            for layer in required_layers(spec):
                value = scores.get(layer)
                status = (
                    "passing"
                    if score_meets_threshold(value, threshold)
                    else ("missing" if value is None else "failing")
                )
                layer_results.append(
                    {
                        "id": layer,
                        "score": value,
                        "minimum": threshold,
                        "status": status,
                    }
                )
                if status != "passing":
                    issues.append(
                        issue(
                            status,
                            "layer-score-missing"
                            if status == "missing"
                            else "layer-score-failed",
                            f"layer {layer!r} score {value!r} does not meet {threshold}",
                        )
                    )

            targets = {
                target.get("id"): target
                for target in spec.get("featureReviewTargets", [])
                if isinstance(target, dict) and isinstance(target.get("id"), str)
            }
            reviews = review.get("featureReviews")
            review_by_id = {
                item.get("id"): item
                for item in reviews
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            } if isinstance(reviews, list) else {}
            for feature_id in selected_feature_ids(spec, viewpoint):
                target = targets.get(feature_id)
                feature_review = review_by_id.get(feature_id)
                minimum = feature_minimum(spec, target, threshold)
                score = (
                    feature_review.get("score")
                    if isinstance(feature_review, dict)
                    else None
                )
                visible = (
                    feature_review.get("visible")
                    if isinstance(feature_review, dict)
                    else None
                )
                if target is None or feature_review is None:
                    status = "missing"
                elif visible is not True or not score_meets_threshold(score, minimum):
                    status = "failing"
                else:
                    status = "passing"
                feature_results.append(
                    {
                        "id": feature_id,
                        "visible": visible,
                        "score": score,
                        "minimum": minimum,
                        "status": status,
                    }
                )
                if status != "passing":
                    issues.append(
                        issue(
                            status,
                            "semantic-feature-missing"
                            if status == "missing"
                            else "semantic-feature-failed",
                            f"semantic feature {feature_id!r} does not meet {minimum}",
                        )
                    )

            for failure in feature_gate_failures(spec, review, viewpoint.pass_id):
                issues.append(
                    issue("failing", "semantic-feature-policy-failed", failure)
                )
            if (
                viewpoint.pass_id in VISUAL_PASS_IDS
                and not review_completes_pass(
                    spec,
                    review,
                    viewpoint.pass_id,
                    asset.path,
                )
            ):
                issues.append(
                    issue(
                        "failing",
                        "production-pass-gate-failed",
                        "existing sculpt pass completion gate rejects this review",
                    )
                )

    unique_issues = {
        (item["kind"], item["code"], item["message"]): item for item in issues
    }
    issues = sorted(
        unique_issues.values(),
        key=lambda item: (
            STATUS_PRECEDENCE.index(item["kind"])
            if item["kind"] in STATUS_PRECEDENCE
            else len(STATUS_PRECEDENCE),
            item["code"],
            item["message"],
        ),
    )
    status = next(
        (
            candidate
            for candidate in STATUS_PRECEDENCE
            if any(item["kind"] == candidate for item in issues)
        ),
        "passing",
    )
    return {
        "assetId": asset.id,
        "assetRole": asset.role,
        "viewpointId": viewpoint.id,
        "passId": viewpoint.pass_id,
        "cameraView": viewpoint.camera_view,
        "status": status,
        "expected": {
            "renderScreenshot": expected_render,
            "comparisonImage": expected_comparison,
        },
        "actual": actual,
        "review": review_summary,
        "layerScores": layer_results,
        "semanticFeatures": feature_results,
        "issues": issues,
    }


def build_report(
    base_path: Path,
    manifest_path: Path,
    *,
    cli_viewpoints: list[str],
    render_template: str | None,
    comparison_template: str | None,
    feature_ids: tuple[str, ...],
) -> dict[str, Any]:
    if not base_path.is_file():
        raise MatrixInputError(f"base spec does not exist: {base_path}")
    if not manifest_path.is_file():
        raise MatrixInputError(f"curated manifest does not exist: {manifest_path}")
    try:
        base_spec = load_spec(base_path)
    except (OSError, ValueError) as exc:
        raise MatrixInputError(f"base spec is invalid: {base_path}: {exc}") from exc
    manifest = load_json_object(manifest_path, "curated manifest")
    viewpoints = configured_viewpoints(
        manifest,
        cli_viewpoints,
        render_template=render_template,
        comparison_template=comparison_template,
        feature_ids=feature_ids,
    )
    declared_passes = set(pass_order(base_spec))
    unknown_passes = sorted(
        {item.pass_id for item in viewpoints if item.pass_id not in declared_passes}
    )
    if unknown_passes:
        raise MatrixInputError(
            "viewpoints reference passes absent from the base spec: "
            + ", ".join(unknown_passes)
        )

    source_sha = manifest.get("sourceSpecSha256")
    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 64
        or any(character not in string.hexdigits for character in source_sha)
    ):
        raise MatrixInputError(
            "manifest.sourceSpecSha256 must be a 64-character hexadecimal SHA-256"
        )
    base_sha = file_sha256(base_path)
    source_binding_stale = source_sha.lower() != base_sha

    assets = build_assets(base_path, manifest_path, manifest)
    for asset in assets:
        load_asset(asset)
    cells = [
        build_cell(asset, viewpoint, manifest, source_binding_stale)
        for asset in assets
        for viewpoint in viewpoints
    ]
    counts = {
        status: sum(cell["status"] == status for cell in cells)
        for status in STATUS_ORDER
    }
    summary = {"total": len(cells), **counts}
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "ok": counts["passing"] == len(cells),
        "authority": {
            "finalVisualAuthority": "ai-vision",
            "pixelMetrics": "diagnostic-only",
            "pixelMetricsCanApprove": False,
        },
        "inputs": {
            "baseSpec": display_path(base_path),
            "baseSpecSha256": base_sha,
            "curatedManifest": display_path(manifest_path),
            "curatedManifestSha256": file_sha256(manifest_path),
        },
        "policy": {
            "authoritativeReview": LATEST_REVIEW_SELECTION,
            "statusOrder": list(STATUS_ORDER),
            "assetOrder": "base then variantId ascending",
            "viewpointOrder": "viewpoint id ascending",
        },
        "viewpoints": [
            {
                "id": item.id,
                "passId": item.pass_id,
                "cameraView": item.camera_view,
                "renderPathTemplate": item.render_template,
                "comparisonPathTemplate": item.comparison_template,
                "featureIds": list(item.feature_ids),
            }
            for item in viewpoints
        ],
        "assets": [
            {
                "id": asset.id,
                "role": asset.role,
                "path": display_path(asset.path),
                "sha256": asset.digest,
                "variantIndex": asset.variant_index,
                "targetName": (
                    asset.spec.get("targetName")
                    if isinstance(asset.spec, dict)
                    else None
                ),
            }
            for asset in assets
        ],
        "cells": cells,
        "summary": summary,
    }


def write_report(report: dict[str, Any], output: Path | None) -> None:
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if output is None:
        print(payload, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")


def print_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print("PASS" if report["ok"] else "FAIL", file=sys.stderr)
    print(
        "cells: "
        + " ".join(
            f"{key}={summary[key]}"
            for key in ("total", *STATUS_ORDER)
        ),
        file=sys.stderr,
    )
    for cell in report["cells"]:
        if cell["status"] == "passing":
            continue
        message = (
            cell["issues"][0]["message"]
            if cell["issues"]
            else "matrix cell did not pass"
        )
        print(
            f"{cell['status']}: {cell['assetId']}/{cell['viewpointId']} "
            f"({cell['passId']}): {message}",
            file=sys.stderr,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_spec", type=Path, help="Base ObjectSculptSpec JSON")
    parser.add_argument("manifest", type=Path, help="Curated Sculpt DNA manifest JSON")
    parser.add_argument(
        "--viewpoint",
        action="append",
        default=[],
        metavar="VIEWPOINT_ID=PASS_ID",
        help=(
            "Required viewpoint and authoritative pass; repeat for multiple views. "
            f"Not allowed when the manifest defines {CONFIG_FIELD}.viewpoints."
        ),
    )
    parser.add_argument(
        "--render-template",
        help="Expected render path template for CLI-defined viewpoints",
    )
    parser.add_argument(
        "--comparison-template",
        help="Expected comparison path template for CLI-defined viewpoints",
    )
    parser.add_argument(
        "--feature-id",
        action="append",
        default=[],
        help="Selected semantic feature required for every CLI-defined viewpoint",
    )
    parser.add_argument("--out", type=Path, help="Write deterministic JSON to this path")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Also print a concise human-readable summary to stderr",
    )
    return parser


def error_report(message: str) -> dict[str, Any]:
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "ok": False,
        "error": {
            "code": "invalid-input",
            "message": message,
        },
    }


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        render_template = validate_template(
            args.render_template,
            "--render-template",
        )
        comparison_template = validate_template(
            args.comparison_template,
            "--comparison-template",
        )
        feature_ids = tuple(
            sorted(
                {
                    require_id(value, "--feature-id")
                    for value in args.feature_id
                }
            )
        )
        if (
            (render_template or comparison_template or feature_ids)
            and not args.viewpoint
        ):
            raise MatrixInputError(
                "--render-template, --comparison-template, and --feature-id "
                "require at least one --viewpoint"
            )
        report = build_report(
            args.base_spec.expanduser().resolve(),
            args.manifest.expanduser().resolve(),
            cli_viewpoints=args.viewpoint,
            render_template=render_template,
            comparison_template=comparison_template,
            feature_ids=feature_ids,
        )
    except MatrixInputError as exc:
        report = error_report(str(exc))
        write_report(report, args.out.expanduser().resolve() if args.out else None)
        if args.summary:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    write_report(report, args.out.expanduser().resolve() if args.out else None)
    if args.summary:
        print_summary(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
