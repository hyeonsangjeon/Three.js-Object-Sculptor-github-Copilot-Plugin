#!/usr/bin/env python3
"""Verify a standalone and host runtime against a render integration contract."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from statistics import median
from typing import Any
from urllib.parse import urlparse

from visual_evidence_hashes import is_remote_or_virtual_path


SCHEMA_VERSION = "1.0"
CONTRACT_KIND = "render-integration-contract"
SNAPSHOT_KIND = "render-runtime-snapshot"
REPORT_KIND = "render-integration-contract-report"
STATUS_ORDER = ("missing", "stale", "passing", "failing")
ENVIRONMENTS = ("standalone", "host")
REPO_ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
JSON_SAFE_INTEGER = (1 << 53) - 1
_MISSING = object()


class ContractInputError(ValueError):
    """Raised when contract input cannot be evaluated safely."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ContractInputError(f"arguments: {message}")


def display_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_cli_path(path: Path, label: str) -> Path:
    try:
        return path.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ContractInputError(f"{label} path cannot be resolved: {path}: {exc}") from exc


def paths_alias(first: Path, second: Path) -> bool:
    if first == second:
        return True
    try:
        return first.exists() and second.exists() and first.samefile(second)
    except OSError as exc:
        raise ContractInputError(
            f"paths cannot be compared safely: {first}: {second}: {exc}"
        ) from exc


def reject_non_finite(value: Any, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractInputError(f"{label} must not contain non-finite numbers")
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and abs(value) > JSON_SAFE_INTEGER
    ):
        raise ContractInputError(
            f"{label} must not contain integers outside the JSON-safe range"
        )
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_non_finite(item, f"{label}[{index}]")
    elif isinstance(value, dict):
        for key in sorted(value):
            reject_non_finite(value[key], f"{label}.{key}")


def load_json_object(path: Path, label: str) -> tuple[dict[str, Any], str]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant {value}")

    try:
        source_bytes = path.read_bytes()
    except OSError as exc:
        raise ContractInputError(
            f"{label} cannot be read: {display_path(path)}: {exc}"
        ) from exc
    digest = sha256(source_bytes).hexdigest()
    try:
        payload = json.loads(
            source_bytes.decode("utf-8"),
            parse_constant=reject_constant,
        )
        reject_non_finite(payload, label)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ContractInputError(
            f"{label} is invalid JSON: {display_path(path)}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ContractInputError(f"{label} must contain a JSON object")
    return payload, digest


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractInputError(f"{label} must be an object")
    return value


def require_array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractInputError(f"{label} must be an array")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractInputError(f"{label} must be a non-empty string")
    return value


def require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ContractInputError(
            f"{label} must match {ID_PATTERN.pattern!r}; got {value!r}"
        )
    return value


def require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ContractInputError(
            f"{label} must be a 64-character hexadecimal SHA-256"
        )
    return value.lower()


def require_safe_path(value: Any, label: str) -> str:
    path = require_string(value, label)
    parsed = urlparse(path)
    pure = PurePosixPath(path)
    if (
        "\x00" in path
        or "\\" in path
        or is_remote_or_virtual_path(path)
        or bool(parsed.scheme)
        or pure.is_absolute()
        or PureWindowsPath(path).is_absolute()
        or ".." in pure.parts
        or "." in pure.parts
        or pure.as_posix() != path
    ):
        raise ContractInputError(
            f"{label} must be a canonical safe repository-relative path"
        )
    return path


def require_number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_exclusive: bool = False,
) -> int | float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ContractInputError(f"{label} must be a finite number")
    if isinstance(value, int) and abs(value) > JSON_SAFE_INTEGER:
        raise ContractInputError(f"{label} must be a JSON-safe integer")
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractInputError(f"{label} must be a finite number")
    if minimum is not None:
        if minimum_exclusive and value <= minimum:
            raise ContractInputError(f"{label} must be greater than {minimum}")
        if not minimum_exclusive and value < minimum:
            raise ContractInputError(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ContractInputError(f"{label} must be at most {maximum}")
    return value


def require_integer(
    value: Any,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ContractInputError(f"{label} must be an integer")
    if abs(value) > JSON_SAFE_INTEGER:
        raise ContractInputError(f"{label} must be a JSON-safe integer")
    if minimum is not None and value < minimum:
        raise ContractInputError(f"{label} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ContractInputError(f"{label} must be at most {maximum}")
    return value


def require_boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ContractInputError(f"{label} must be a boolean")
    return value


def optional_object(
    payload: dict[str, Any],
    key: str,
    label: str,
) -> dict[str, Any] | None:
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return None
    return require_object(value, f"{label}.{key}")


def optional_string(
    payload: dict[str, Any],
    key: str,
    label: str,
) -> str | None:
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return None
    return require_string(value, f"{label}.{key}")


def optional_id(
    payload: dict[str, Any],
    key: str,
    label: str,
) -> str | None:
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return None
    return require_id(value, f"{label}.{key}")


def optional_number(
    payload: dict[str, Any],
    key: str,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_exclusive: bool = False,
) -> int | float | None:
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return None
    return require_number(
        value,
        f"{label}.{key}",
        minimum=minimum,
        maximum=maximum,
        minimum_exclusive=minimum_exclusive,
    )


def optional_integer(
    payload: dict[str, Any],
    key: str,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return None
    return require_integer(
        value,
        f"{label}.{key}",
        minimum=minimum,
        maximum=maximum,
    )


def optional_boolean(
    payload: dict[str, Any],
    key: str,
    label: str,
) -> bool | None:
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return None
    return require_boolean(value, f"{label}.{key}")


def require_schema(payload: dict[str, Any], kind: str, label: str) -> None:
    version = payload.get("schemaVersion")
    if version != SCHEMA_VERSION:
        raise ContractInputError(
            f"{label}.schemaVersion must be {SCHEMA_VERSION!r}; got {version!r}"
        )
    actual_kind = payload.get("kind")
    if actual_kind != kind:
        raise ContractInputError(
            f"{label}.kind must be {kind!r}; got {actual_kind!r}"
        )


def normalize_binding(
    value: Any,
    label: str,
    *,
    optional: bool,
) -> dict[str, str] | None:
    if value is None and optional:
        return None
    payload = require_object(value, label)
    path_value = payload.get("path", _MISSING)
    sha_value = payload.get("sha256", _MISSING)
    if optional and path_value in (_MISSING, None) and sha_value in (_MISSING, None):
        return None
    if path_value in (_MISSING, None):
        path = None
    else:
        path = require_safe_path(path_value, f"{label}.path")
    if sha_value in (_MISSING, None):
        digest = None
    else:
        digest = require_sha256(sha_value, f"{label}.sha256")
    if not optional and (path is None or digest is None):
        raise ContractInputError(f"{label}.path and {label}.sha256 are required")
    result: dict[str, str] = {}
    if path is not None:
        result["path"] = path
    if digest is not None:
        result["sha256"] = digest
    return result


def normalize_id_array(
    value: Any,
    label: str,
    *,
    allow_missing: bool = False,
) -> list[str] | None:
    if value is None and allow_missing:
        return None
    values = require_array(value, label)
    ids = [require_id(item, f"{label}[{index}]") for index, item in enumerate(values)]
    if len(ids) != len(set(ids)):
        raise ContractInputError(f"{label} must not contain duplicate IDs")
    return sorted(ids)


def ensure_unique_ids(items: list[dict[str, Any]], label: str) -> None:
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ContractInputError(f"{label} must not contain duplicate IDs")


def normalize_bounds(payload: dict[str, Any], label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in (
        "minCoverage",
        "maxCoverage",
        "minP50Luminance",
        "maxP50Luminance",
        "minP90Luminance",
        "maxP90Luminance",
    ):
        value = optional_number(payload, key, label, minimum=0, maximum=1)
        if value is not None:
            result[key] = value
    for lower, upper in (
        ("minCoverage", "maxCoverage"),
        ("minP50Luminance", "maxP50Luminance"),
        ("minP90Luminance", "maxP90Luminance"),
    ):
        if lower in result and upper in result and result[lower] > result[upper]:
            raise ContractInputError(f"{label}.{lower} must not exceed {upper}")
    if result.get("minP50Luminance", 0) > result.get("maxP90Luminance", 1):
        raise ContractInputError(
            f"{label} luminance bounds cannot satisfy P50 <= P90"
        )
    return result


def normalize_contract(payload: dict[str, Any]) -> dict[str, Any]:
    label = "contract"
    require_schema(payload, CONTRACT_KIND, label)
    asset_payload = require_object(payload.get("asset"), "contract.asset")
    renderer_payload = require_object(payload.get("renderer"), "contract.renderer")

    asset = {
        "assetId": require_id(asset_payload.get("assetId"), "contract.asset.assetId"),
        "profileId": require_id(
            asset_payload.get("profileId"),
            "contract.asset.profileId",
        ),
        "source": normalize_binding(
            asset_payload.get("source"),
            "contract.asset.source",
            optional=False,
        ),
        "factory": normalize_binding(
            asset_payload.get("factory"),
            "contract.asset.factory",
            optional=False,
        ),
    }
    renderer = {
        "toneMapping": require_string(
            renderer_payload.get("toneMapping"),
            "contract.renderer.toneMapping",
        ),
        "outputColorSpace": require_string(
            renderer_payload.get("outputColorSpace"),
            "contract.renderer.outputColorSpace",
        ),
        "standaloneExposure": require_number(
            renderer_payload.get("standaloneExposure"),
            "contract.renderer.standaloneExposure",
            minimum=0,
        ),
        "maxHostExposureDelta": require_number(
            renderer_payload.get("maxHostExposureDelta"),
            "contract.renderer.maxHostExposureDelta",
            minimum=0,
        ),
        "outputPassCount": require_integer(
            renderer_payload.get("outputPassCount"),
            "contract.renderer.outputPassCount",
            minimum=0,
        ),
        "maxPixelRatio": require_number(
            renderer_payload.get("maxPixelRatio"),
            "contract.renderer.maxPixelRatio",
            minimum=0,
            minimum_exclusive=True,
        ),
    }

    target_values = require_array(
        payload.get("renderTargets"),
        "contract.renderTargets",
    )
    targets: list[dict[str, Any]] = []
    for index, value in enumerate(target_values):
        item_label = f"contract.renderTargets[{index}]"
        item = require_object(value, item_label)
        min_scale = require_number(
            item.get("minScale"),
            f"{item_label}.minScale",
            minimum=0,
            minimum_exclusive=True,
        )
        max_scale = require_number(
            item.get("maxScale"),
            f"{item_label}.maxScale",
            minimum=0,
            minimum_exclusive=True,
        )
        if min_scale > max_scale:
            raise ContractInputError(
                f"{item_label}.minScale must not exceed maxScale"
            )
        targets.append(
            {
                "id": require_id(item.get("id"), f"{item_label}.id"),
                "type": require_string(item.get("type"), f"{item_label}.type"),
                "colorSpace": require_string(
                    item.get("colorSpace"),
                    f"{item_label}.colorSpace",
                ),
                "depthBuffer": require_boolean(
                    item.get("depthBuffer"),
                    f"{item_label}.depthBuffer",
                ),
                "minScale": min_scale,
                "maxScale": max_scale,
                "maxPixels": require_integer(
                    item.get("maxPixels"),
                    f"{item_label}.maxPixels",
                    minimum=1,
                ),
            }
        )
    ensure_unique_ids(targets, "contract.renderTargets")
    targets.sort(key=lambda item: item["id"])

    selective_payload = require_object(
        payload.get("selectiveRendering"),
        "contract.selectiveRendering",
    )
    layer_values = require_array(
        selective_payload.get("layers"),
        "contract.selectiveRendering.layers",
    )
    layers: list[dict[str, Any]] = []
    for index, value in enumerate(layer_values):
        item_label = f"contract.selectiveRendering.layers[{index}]"
        item = require_object(value, item_label)
        required_members = normalize_id_array(
            item.get("requiredMembers"),
            f"{item_label}.requiredMembers",
        )
        forbidden_members = normalize_id_array(
            item.get("forbiddenMembers"),
            f"{item_label}.forbiddenMembers",
        )
        assert required_members is not None
        assert forbidden_members is not None
        overlap = sorted(set(required_members) & set(forbidden_members))
        if overlap:
            raise ContractInputError(
                f"{item_label} requires and forbids the same members: "
                + ", ".join(overlap)
            )
        layers.append(
            {
                "id": require_id(item.get("id"), f"{item_label}.id"),
                "index": require_integer(
                    item.get("index"),
                    f"{item_label}.index",
                    minimum=0,
                    maximum=31,
                ),
                "owner": require_id(item.get("owner"), f"{item_label}.owner"),
                "requiredMembers": required_members,
                "forbiddenMembers": forbidden_members,
            }
        )
    ensure_unique_ids(layers, "contract.selectiveRendering.layers")
    layers.sort(key=lambda item: item["id"])

    light_values = require_array(
        selective_payload.get("lights"),
        "contract.selectiveRendering.lights",
    )
    lights: list[dict[str, Any]] = []
    for index, value in enumerate(light_values):
        item_label = f"contract.selectiveRendering.lights[{index}]"
        item = require_object(value, item_label)
        required_layers = normalize_id_array(
            item.get("requiredLayers"),
            f"{item_label}.requiredLayers",
        )
        forbidden_layers = normalize_id_array(
            item.get("forbiddenLayers"),
            f"{item_label}.forbiddenLayers",
        )
        assert required_layers is not None
        assert forbidden_layers is not None
        overlap = sorted(set(required_layers) & set(forbidden_layers))
        if overlap:
            raise ContractInputError(
                f"{item_label} requires and forbids the same layers: "
                + ", ".join(overlap)
            )
        lights.append(
            {
                "id": require_id(item.get("id"), f"{item_label}.id"),
                "owner": require_id(item.get("owner"), f"{item_label}.owner"),
                "requiredLayers": required_layers,
                "forbiddenLayers": forbidden_layers,
                "maxTownSpill": require_number(
                    item.get("maxTownSpill"),
                    f"{item_label}.maxTownSpill",
                    minimum=0,
                    maximum=1,
                ),
            }
        )
    ensure_unique_ids(lights, "contract.selectiveRendering.lights")
    lights.sort(key=lambda item: item["id"])

    view_values = require_array(payload.get("views"), "contract.views")
    if not view_values:
        raise ContractInputError("contract.views must contain at least one view")
    views: list[dict[str, Any]] = []
    for view_index, value in enumerate(view_values):
        view_label = f"contract.views[{view_index}]"
        item = require_object(value, view_label)
        system_values = require_array(
            item.get("requiredSystems"),
            f"{view_label}.requiredSystems",
        )
        if not system_values:
            raise ContractInputError(
                f"{view_label}.requiredSystems must contain at least one system"
            )
        systems: list[dict[str, Any]] = []
        for system_index, system_value in enumerate(system_values):
            system_label = (
                f"{view_label}.requiredSystems[{system_index}]"
            )
            system_payload = require_object(system_value, system_label)
            system = {
                "id": require_id(
                    system_payload.get("id"),
                    f"{system_label}.id",
                ),
                **normalize_bounds(system_payload, system_label),
            }
            must_be_visible = optional_boolean(
                system_payload,
                "mustBeVisible",
                system_label,
            )
            if must_be_visible is not None:
                system["mustBeVisible"] = must_be_visible
            systems.append(system)
        ensure_unique_ids(systems, f"{view_label}.requiredSystems")
        systems.sort(key=lambda system: system["id"])
        views.append(
            {
                "id": require_id(item.get("id"), f"{view_label}.id"),
                "cameraId": require_id(
                    item.get("cameraId"),
                    f"{view_label}.cameraId",
                ),
                **normalize_bounds(item, view_label),
                "requiredSystems": systems,
            }
        )
    ensure_unique_ids(views, "contract.views")
    views.sort(key=lambda item: item["id"])
    view_ids = {item["id"] for item in views}

    angle_payload = require_object(
        payload.get("angleConsistency"),
        "contract.angleConsistency",
    )
    angle_view_ids = normalize_id_array(
        angle_payload.get("viewIds"),
        "contract.angleConsistency.viewIds",
    )
    assert angle_view_ids is not None
    if not angle_view_ids:
        raise ContractInputError(
            "contract.angleConsistency.viewIds must not be empty"
        )
    unknown_angle_views = sorted(set(angle_view_ids) - view_ids)
    if unknown_angle_views:
        raise ContractInputError(
            "contract.angleConsistency.viewIds references unknown views: "
            + ", ".join(unknown_angle_views)
        )
    angle_consistency = {
        "viewIds": angle_view_ids,
        "minCoverageToMedian": require_number(
            angle_payload.get("minCoverageToMedian"),
            "contract.angleConsistency.minCoverageToMedian",
            minimum=0,
            maximum=1,
        ),
        "maxP90LuminanceSpread": require_number(
            angle_payload.get("maxP90LuminanceSpread"),
            "contract.angleConsistency.maxP90LuminanceSpread",
            minimum=0,
            maximum=1,
        ),
        "forbidBlackFrames": require_boolean(
            angle_payload.get("forbidBlackFrames"),
            "contract.angleConsistency.forbidBlackFrames",
        ),
        "forbidClipping": require_boolean(
            angle_payload.get("forbidClipping"),
            "contract.angleConsistency.forbidClipping",
        ),
    }

    town_payload = require_object(
        payload.get("townExposure"),
        "contract.townExposure",
    )
    town_view_ids = normalize_id_array(
        town_payload.get("viewIds"),
        "contract.townExposure.viewIds",
    )
    assert town_view_ids is not None
    if not town_view_ids:
        raise ContractInputError("contract.townExposure.viewIds must not be empty")
    unknown_town_views = sorted(set(town_view_ids) - view_ids)
    if unknown_town_views:
        raise ContractInputError(
            "contract.townExposure.viewIds references unknown views: "
            + ", ".join(unknown_town_views)
        )
    town_system = require_id(
        town_payload.get("semanticSystemId"),
        "contract.townExposure.semanticSystemId",
    )
    systems_by_view = {
        item["id"]: {system["id"] for system in item["requiredSystems"]}
        for item in views
    }
    missing_town_system = [
        view_id
        for view_id in town_view_ids
        if town_system not in systems_by_view[view_id]
    ]
    if missing_town_system:
        raise ContractInputError(
            "contract.townExposure.semanticSystemId must be a required system "
            "for views: " + ", ".join(missing_town_system)
        )
    town_exposure = {
        "semanticSystemId": town_system,
        "viewIds": town_view_ids,
        "maxP50LuminanceDelta": require_number(
            town_payload.get("maxP50LuminanceDelta"),
            "contract.townExposure.maxP50LuminanceDelta",
            minimum=0,
            maximum=1,
        ),
    }

    performance_payload = require_object(
        payload.get("performance"),
        "contract.performance",
    )
    performance = {
        "maxCalls": require_integer(
            performance_payload.get("maxCalls"),
            "contract.performance.maxCalls",
            minimum=0,
        ),
        "maxTriangles": require_integer(
            performance_payload.get("maxTriangles"),
            "contract.performance.maxTriangles",
            minimum=0,
        ),
        "minFps": require_number(
            performance_payload.get("minFps"),
            "contract.performance.minFps",
            minimum=0,
        ),
        "maxFrameTimeP50Ms": require_number(
            performance_payload.get("maxFrameTimeP50Ms"),
            "contract.performance.maxFrameTimeP50Ms",
            minimum=0,
        ),
        "maxFrameTimeP95Ms": require_number(
            performance_payload.get("maxFrameTimeP95Ms"),
            "contract.performance.maxFrameTimeP95Ms",
            minimum=0,
        ),
        "maxDirectionCallsSpread": require_integer(
            performance_payload.get("maxDirectionCallsSpread"),
            "contract.performance.maxDirectionCallsSpread",
            minimum=0,
        ),
        "maxDirectionTrianglesSpread": require_integer(
            performance_payload.get("maxDirectionTrianglesSpread"),
            "contract.performance.maxDirectionTrianglesSpread",
            minimum=0,
        ),
        "maxDirectionFrameTimeP95SpreadMs": require_number(
            performance_payload.get("maxDirectionFrameTimeP95SpreadMs"),
            "contract.performance.maxDirectionFrameTimeP95SpreadMs",
            minimum=0,
        ),
    }
    if performance["maxFrameTimeP50Ms"] > performance["maxFrameTimeP95Ms"]:
        raise ContractInputError(
            "contract.performance.maxFrameTimeP50Ms must not exceed "
            "maxFrameTimeP95Ms"
        )

    errors_payload = require_object(payload.get("errors"), "contract.errors")
    errors = {
        "maxConsoleErrors": require_integer(
            errors_payload.get("maxConsoleErrors"),
            "contract.errors.maxConsoleErrors",
            minimum=0,
        ),
        "maxNetworkErrors": require_integer(
            errors_payload.get("maxNetworkErrors"),
            "contract.errors.maxNetworkErrors",
            minimum=0,
        ),
    }

    return {
        "contractId": require_id(payload.get("contractId"), "contract.contractId"),
        "asset": asset,
        "renderer": renderer,
        "renderTargets": targets,
        "selectiveRendering": {
            "layers": layers,
            "lights": lights,
        },
        "views": views,
        "angleConsistency": angle_consistency,
        "townExposure": town_exposure,
        "performance": performance,
        "errors": errors,
    }


def normalize_snapshot_binding(
    asset: dict[str, Any],
    key: str,
    label: str,
) -> dict[str, str] | None:
    value = asset.get(key, _MISSING)
    if value is _MISSING or value is None:
        return None
    return normalize_binding(value, f"{label}.{key}", optional=True)


def normalize_luminance(
    value: Any,
    label: str,
) -> dict[str, int | float] | None:
    if value is None:
        return None
    payload = require_object(value, label)
    result: dict[str, int | float] = {}
    for key in ("p50", "p90"):
        metric = optional_number(payload, key, label, minimum=0, maximum=1)
        if metric is not None:
            result[key] = metric
    if "p50" in result and "p90" in result and result["p50"] > result["p90"]:
        raise ContractInputError(f"{label}.p50 must not exceed p90")
    return result


def normalize_snapshot(payload: dict[str, Any], expected_role: str) -> dict[str, Any]:
    label = f"{expected_role} snapshot"
    require_schema(payload, SNAPSHOT_KIND, label)
    role = payload.get("role")
    if role != expected_role:
        raise ContractInputError(
            f"{label}.role must be {expected_role!r}; got {role!r}"
        )
    asset_payload = require_object(payload.get("asset"), f"{label}.asset")
    asset = {
        "assetId": require_id(
            asset_payload.get("assetId"),
            f"{label}.asset.assetId",
        ),
        "profileId": require_id(
            asset_payload.get("profileId"),
            f"{label}.asset.profileId",
        ),
        "source": normalize_snapshot_binding(asset_payload, "source", f"{label}.asset"),
        "factory": normalize_snapshot_binding(
            asset_payload,
            "factory",
            f"{label}.asset",
        ),
    }

    renderer_payload = optional_object(payload, "renderer", label)
    renderer: dict[str, Any] | None = None
    if renderer_payload is not None:
        renderer = {
            "toneMapping": optional_string(renderer_payload, "toneMapping", f"{label}.renderer"),
            "outputColorSpace": optional_string(
                renderer_payload,
                "outputColorSpace",
                f"{label}.renderer",
            ),
            "exposure": optional_number(
                renderer_payload,
                "exposure",
                f"{label}.renderer",
                minimum=0,
            ),
            "outputPassCount": optional_integer(
                renderer_payload,
                "outputPassCount",
                f"{label}.renderer",
                minimum=0,
            ),
            "pixelRatio": optional_number(
                renderer_payload,
                "pixelRatio",
                f"{label}.renderer",
                minimum=0,
                minimum_exclusive=True,
            ),
        }

    target_values = payload.get("renderTargets", [])
    if target_values is None:
        target_values = []
    target_values = require_array(target_values, f"{label}.renderTargets")
    targets: list[dict[str, Any]] = []
    for index, value in enumerate(target_values):
        item_label = f"{label}.renderTargets[{index}]"
        item = require_object(value, item_label)
        width = optional_integer(item, "width", item_label, minimum=0)
        height = optional_integer(item, "height", item_label, minimum=0)
        pixel_count = optional_integer(item, "pixelCount", item_label, minimum=0)
        if (
            width is not None
            and height is not None
            and pixel_count is not None
            and width * height != pixel_count
        ):
            raise ContractInputError(
                f"{item_label}.pixelCount must equal width * height"
            )
        targets.append(
            {
                "id": require_id(item.get("id"), f"{item_label}.id"),
                "type": optional_string(item, "type", item_label),
                "colorSpace": optional_string(item, "colorSpace", item_label),
                "depthBuffer": optional_boolean(item, "depthBuffer", item_label),
                "scale": optional_number(
                    item,
                    "scale",
                    item_label,
                    minimum=0,
                    minimum_exclusive=True,
                ),
                "width": width,
                "height": height,
                "pixelCount": pixel_count,
            }
        )
    ensure_unique_ids(targets, f"{label}.renderTargets")
    targets.sort(key=lambda item: item["id"])

    selective_payload = optional_object(payload, "selectiveRendering", label)
    layer_values: list[Any] = []
    light_values: list[Any] = []
    if selective_payload is not None:
        raw_layers = selective_payload.get("layers", [])
        raw_lights = selective_payload.get("lights", [])
        layer_values = require_array(
            [] if raw_layers is None else raw_layers,
            f"{label}.selectiveRendering.layers",
        )
        light_values = require_array(
            [] if raw_lights is None else raw_lights,
            f"{label}.selectiveRendering.lights",
        )
    layers: list[dict[str, Any]] = []
    for index, value in enumerate(layer_values):
        item_label = f"{label}.selectiveRendering.layers[{index}]"
        item = require_object(value, item_label)
        members_value = item.get("members", _MISSING)
        members = (
            None
            if members_value is _MISSING or members_value is None
            else normalize_id_array(members_value, f"{item_label}.members")
        )
        layers.append(
            {
                "id": require_id(item.get("id"), f"{item_label}.id"),
                "index": optional_integer(
                    item,
                    "index",
                    item_label,
                    minimum=0,
                    maximum=31,
                ),
                "owner": optional_id(item, "owner", item_label),
                "members": members,
            }
        )
    ensure_unique_ids(layers, f"{label}.selectiveRendering.layers")
    layers.sort(key=lambda item: item["id"])

    lights: list[dict[str, Any]] = []
    for index, value in enumerate(light_values):
        item_label = f"{label}.selectiveRendering.lights[{index}]"
        item = require_object(value, item_label)
        layers_value = item.get("layers", _MISSING)
        item_layers = (
            None
            if layers_value is _MISSING or layers_value is None
            else normalize_id_array(layers_value, f"{item_label}.layers")
        )
        lights.append(
            {
                "id": require_id(item.get("id"), f"{item_label}.id"),
                "owner": optional_id(item, "owner", item_label),
                "layers": item_layers,
                "townSpill": optional_number(
                    item,
                    "townSpill",
                    item_label,
                    minimum=0,
                    maximum=1,
                ),
            }
        )
    ensure_unique_ids(lights, f"{label}.selectiveRendering.lights")
    lights.sort(key=lambda item: item["id"])

    view_values = payload.get("views", [])
    if view_values is None:
        view_values = []
    view_values = require_array(view_values, f"{label}.views")
    views: list[dict[str, Any]] = []
    for view_index, value in enumerate(view_values):
        view_label = f"{label}.views[{view_index}]"
        item = require_object(value, view_label)
        semantic_values = item.get("semantics", [])
        if semantic_values is None:
            semantic_values = []
        semantic_values = require_array(
            semantic_values,
            f"{view_label}.semantics",
        )
        semantics: list[dict[str, Any]] = []
        for semantic_index, semantic_value in enumerate(semantic_values):
            semantic_label = f"{view_label}.semantics[{semantic_index}]"
            semantic_payload = require_object(semantic_value, semantic_label)
            semantics.append(
                {
                    "id": require_id(
                        semantic_payload.get("id"),
                        f"{semantic_label}.id",
                    ),
                    "visible": optional_boolean(
                        semantic_payload,
                        "visible",
                        semantic_label,
                    ),
                    "coverage": optional_number(
                        semantic_payload,
                        "coverage",
                        semantic_label,
                        minimum=0,
                        maximum=1,
                    ),
                    "luminance": normalize_luminance(
                        semantic_payload.get("luminance"),
                        f"{semantic_label}.luminance",
                    ),
                }
            )
        ensure_unique_ids(semantics, f"{view_label}.semantics")
        semantics.sort(key=lambda semantic: semantic["id"])

        performance_payload = optional_object(item, "performance", view_label)
        view_performance: dict[str, Any] | None = None
        if performance_payload is not None:
            view_performance = {
                "calls": optional_integer(
                    performance_payload,
                    "calls",
                    f"{view_label}.performance",
                    minimum=0,
                ),
                "triangles": optional_integer(
                    performance_payload,
                    "triangles",
                    f"{view_label}.performance",
                    minimum=0,
                ),
                "fps": optional_number(
                    performance_payload,
                    "fps",
                    f"{view_label}.performance",
                    minimum=0,
                ),
                "frameTimeP50Ms": optional_number(
                    performance_payload,
                    "frameTimeP50Ms",
                    f"{view_label}.performance",
                    minimum=0,
                ),
                "frameTimeP95Ms": optional_number(
                    performance_payload,
                    "frameTimeP95Ms",
                    f"{view_label}.performance",
                    minimum=0,
                ),
            }
            if (
                view_performance["frameTimeP50Ms"] is not None
                and view_performance["frameTimeP95Ms"] is not None
                and view_performance["frameTimeP50Ms"]
                > view_performance["frameTimeP95Ms"]
            ):
                raise ContractInputError(
                    f"{view_label}.performance.frameTimeP50Ms must not exceed "
                    "frameTimeP95Ms"
                )
        views.append(
            {
                "id": require_id(item.get("id"), f"{view_label}.id"),
                "cameraId": optional_id(item, "cameraId", view_label),
                "blackFrame": optional_boolean(item, "blackFrame", view_label),
                "clipped": optional_boolean(item, "clipped", view_label),
                "coverage": optional_number(
                    item,
                    "coverage",
                    view_label,
                    minimum=0,
                    maximum=1,
                ),
                "luminance": normalize_luminance(
                    item.get("luminance"),
                    f"{view_label}.luminance",
                ),
                "semantics": semantics,
                "performance": view_performance,
            }
        )
    ensure_unique_ids(views, f"{label}.views")
    views.sort(key=lambda item: item["id"])

    errors_payload = optional_object(payload, "errors", label)
    errors: dict[str, int | None] | None = None
    if errors_payload is not None:
        errors = {
            "console": optional_integer(
                errors_payload,
                "console",
                f"{label}.errors",
                minimum=0,
            ),
            "network": optional_integer(
                errors_payload,
                "network",
                f"{label}.errors",
                minimum=0,
            ),
        }

    return {
        "snapshotId": require_id(payload.get("snapshotId"), f"{label}.snapshotId"),
        "role": expected_role,
        "asset": asset,
        "renderer": renderer,
        "renderTargets": targets,
        "selectiveRendering": {
            "layers": layers,
            "lights": lights,
        },
        "views": views,
        "errors": errors,
    }


def stable_number(value: int | float) -> int | float:
    if isinstance(value, int):
        return value
    rounded = round(value, 12)
    return 0.0 if rounded == 0 else rounded


def item_map(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in items}


def check(
    check_id: str,
    code: str,
    scope: str,
    status: str,
    expected: Any,
    actual: Any,
    message: str,
) -> dict[str, Any]:
    if status not in STATUS_ORDER:
        raise ValueError(f"unsupported check status {status!r}")
    return {
        "id": check_id,
        "code": code,
        "scope": scope,
        "required": True,
        "status": status,
        "expected": expected,
        "actual": actual,
        "message": message,
    }


def equality_check(
    check_id: str,
    code: str,
    scope: str,
    label: str,
    expected: Any,
    actual: Any,
) -> dict[str, Any]:
    if actual is None:
        status = "missing"
        message = f"{scope} {label} is missing"
    elif actual == expected:
        status = "passing"
        message = f"{scope} {label} matches the contract"
    else:
        status = "failing"
        message = f"{scope} {label} does not match the contract"
    return check(check_id, code, scope, status, expected, actual, message)


def maximum_check(
    check_id: str,
    code: str,
    scope: str,
    label: str,
    maximum: int | float,
    actual: int | float | None,
) -> dict[str, Any]:
    if actual is None:
        status = "missing"
        message = f"{scope} {label} is missing"
    elif actual <= maximum:
        status = "passing"
        message = f"{scope} {label} is within the contract maximum"
    else:
        status = "failing"
        message = f"{scope} {label} exceeds the contract maximum"
    return check(
        check_id,
        code,
        scope,
        status,
        {"max": maximum},
        actual,
        message,
    )


def minimum_check(
    check_id: str,
    code: str,
    scope: str,
    label: str,
    minimum: int | float,
    actual: int | float | None,
) -> dict[str, Any]:
    if actual is None:
        status = "missing"
        message = f"{scope} {label} is missing"
    elif actual >= minimum:
        status = "passing"
        message = f"{scope} {label} meets the contract minimum"
    else:
        status = "failing"
        message = f"{scope} {label} is below the contract minimum"
    return check(
        check_id,
        code,
        scope,
        status,
        {"min": minimum},
        actual,
        message,
    )


def range_check(
    check_id: str,
    code: str,
    scope: str,
    label: str,
    minimum: int | float | None,
    maximum: int | float | None,
    actual: int | float | None,
) -> dict[str, Any]:
    expected = {"min": minimum, "max": maximum}
    if actual is None:
        status = "missing"
        message = f"{scope} {label} is missing"
    elif (minimum is None or actual >= minimum) and (
        maximum is None or actual <= maximum
    ):
        status = "passing"
        message = f"{scope} {label} is within the contract range"
    else:
        status = "failing"
        message = f"{scope} {label} is outside the contract range"
    return check(check_id, code, scope, status, expected, actual, message)


def binding_check(
    environment: str,
    binding_name: str,
    expected: dict[str, str],
    actual: dict[str, str] | None,
) -> dict[str, Any]:
    check_id = f"binding.{environment}.{binding_name}"
    code = f"{binding_name}-binding"
    if actual is None or "path" not in actual or "sha256" not in actual:
        status = "missing"
        message = f"{environment} {binding_name} binding is missing"
    elif actual == expected:
        status = "passing"
        message = f"{environment} {binding_name} binding is current"
    else:
        status = "stale"
        message = f"{environment} {binding_name} binding is stale"
    return check(
        check_id,
        code,
        environment,
        status,
        expected,
        actual,
        message,
    )


def presence_check(
    check_id: str,
    code: str,
    scope: str,
    label: str,
    item: dict[str, Any] | None,
) -> dict[str, Any]:
    present = item is not None
    return check(
        check_id,
        code,
        scope,
        "passing" if present else "missing",
        True,
        present,
        f"{scope} {label} is {'present' if present else 'missing'}",
    )


def bound_pair(
    policy: dict[str, Any],
    prefix: str,
) -> tuple[int | float | None, int | float | None]:
    return policy.get(f"min{prefix}"), policy.get(f"max{prefix}")


def luminance_value(
    item: dict[str, Any] | None,
    percentile: str,
) -> int | float | None:
    if item is None:
        return None
    luminance = item.get("luminance")
    return luminance.get(percentile) if isinstance(luminance, dict) else None


def append_renderer_checks(
    checks: list[dict[str, Any]],
    contract: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    renderer_policy = contract["renderer"]
    for environment in ENVIRONMENTS:
        renderer = snapshots[environment]["renderer"] or {}
        checks.append(
            equality_check(
                f"renderer.{environment}.tone-mapping",
                "tone-mapping",
                environment,
                "renderer toneMapping",
                renderer_policy["toneMapping"],
                renderer.get("toneMapping"),
            )
        )
        checks.append(
            equality_check(
                f"renderer.{environment}.output-color-space",
                "output-color-space",
                environment,
                "renderer outputColorSpace",
                renderer_policy["outputColorSpace"],
                renderer.get("outputColorSpace"),
            )
        )
        checks.append(
            equality_check(
                f"renderer.{environment}.tone-mapping-count",
                "tone-mapping-count",
                environment,
                "output-pass count",
                renderer_policy["outputPassCount"],
                renderer.get("outputPassCount"),
            )
        )
        checks.append(
            maximum_check(
                f"renderer.{environment}.pixel-ratio",
                "pixel-ratio",
                environment,
                "renderer pixel ratio",
                renderer_policy["maxPixelRatio"],
                renderer.get("pixelRatio"),
            )
        )

    standalone_exposure = (
        snapshots["standalone"]["renderer"] or {}
    ).get("exposure")
    checks.append(
        equality_check(
            "renderer.standalone.exposure-baseline",
            "exposure-baseline",
            "standalone",
            "renderer exposure",
            renderer_policy["standaloneExposure"],
            standalone_exposure,
        )
    )
    host_exposure = (snapshots["host"]["renderer"] or {}).get("exposure")
    if standalone_exposure is None or host_exposure is None:
        status = "missing"
        actual: Any = None
        message = "standalone or host renderer exposure is missing"
    else:
        delta = stable_number(abs(host_exposure - standalone_exposure))
        actual = delta
        if delta <= renderer_policy["maxHostExposureDelta"]:
            status = "passing"
            message = "host exposure delta is within the contract maximum"
        else:
            status = "failing"
            message = "host exposure delta exceeds the contract maximum"
    checks.append(
        check(
            "renderer.cross.exposure-delta",
            "exposure-delta",
            "cross-snapshot",
            status,
            {"max": renderer_policy["maxHostExposureDelta"]},
            actual,
            message,
        )
    )


def append_target_checks(
    checks: list[dict[str, Any]],
    contract: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    for environment in ENVIRONMENTS:
        actual_targets = item_map(snapshots[environment]["renderTargets"])
        for target in contract["renderTargets"]:
            target_id = target["id"]
            actual = actual_targets.get(target_id)
            prefix = f"target.{environment}.{target_id}"
            checks.append(
                presence_check(
                    f"{prefix}.present",
                    "render-target",
                    environment,
                    f"render target {target_id}",
                    actual,
                )
            )
            if actual is None:
                continue
            checks.extend(
                (
                    equality_check(
                        f"{prefix}.type",
                        "render-target-type",
                        environment,
                        f"render target {target_id} type",
                        target["type"],
                        actual["type"],
                    ),
                    equality_check(
                        f"{prefix}.color-space",
                        "render-target-color-space",
                        environment,
                        f"render target {target_id} color space",
                        target["colorSpace"],
                        actual["colorSpace"],
                    ),
                    equality_check(
                        f"{prefix}.depth",
                        "render-target-depth",
                        environment,
                        f"render target {target_id} depthBuffer",
                        target["depthBuffer"],
                        actual["depthBuffer"],
                    ),
                    range_check(
                        f"{prefix}.scale",
                        "render-target-scale",
                        environment,
                        f"render target {target_id} scale",
                        target["minScale"],
                        target["maxScale"],
                        actual["scale"],
                    ),
                    maximum_check(
                        f"{prefix}.pixels",
                        "render-target-pixels",
                        environment,
                        f"render target {target_id} pixel count",
                        target["maxPixels"],
                        actual["pixelCount"],
                    ),
                )
            )


def append_layer_checks(
    checks: list[dict[str, Any]],
    contract: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    for environment in ENVIRONMENTS:
        actual_layers = item_map(
            snapshots[environment]["selectiveRendering"]["layers"]
        )
        for layer in contract["selectiveRendering"]["layers"]:
            layer_id = layer["id"]
            actual = actual_layers.get(layer_id)
            prefix = f"layer.{environment}.{layer_id}"
            checks.append(
                presence_check(
                    f"{prefix}.present",
                    "selective-layer",
                    environment,
                    f"selective layer {layer_id}",
                    actual,
                )
            )
            if actual is None:
                continue
            checks.append(
                equality_check(
                    f"{prefix}.index",
                    "layer-index",
                    environment,
                    f"selective layer {layer_id} index",
                    layer["index"],
                    actual["index"],
                )
            )
            checks.append(
                equality_check(
                    f"{prefix}.owner",
                    "layer-owner",
                    environment,
                    f"selective layer {layer_id} owner",
                    layer["owner"],
                    actual["owner"],
                )
            )
            members = actual["members"]
            if members is None:
                required_status = forbidden_status = "missing"
                required_message = forbidden_message = (
                    f"{environment} selective layer {layer_id} members are missing"
                )
                missing_required: Any = None
                forbidden_present: Any = None
            else:
                missing_required = sorted(
                    set(layer["requiredMembers"]) - set(members)
                )
                forbidden_present = sorted(
                    set(layer["forbiddenMembers"]) & set(members)
                )
                required_status = "passing" if not missing_required else "failing"
                forbidden_status = (
                    "passing" if not forbidden_present else "failing"
                )
                required_message = (
                    f"{environment} selective layer {layer_id} "
                    + (
                        "contains required members"
                        if not missing_required
                        else "is missing required members"
                    )
                )
                forbidden_message = (
                    f"{environment} selective layer {layer_id} "
                    + (
                        "excludes forbidden members"
                        if not forbidden_present
                        else "contains forbidden members"
                    )
                )
            checks.append(
                check(
                    f"{prefix}.required-members",
                    "layer-required-members",
                    environment,
                    required_status,
                    layer["requiredMembers"],
                    missing_required,
                    required_message,
                )
            )
            checks.append(
                check(
                    f"{prefix}.forbidden-members",
                    "layer-forbidden-members",
                    environment,
                    forbidden_status,
                    layer["forbiddenMembers"],
                    forbidden_present,
                    forbidden_message,
                )
            )


def append_light_checks(
    checks: list[dict[str, Any]],
    contract: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    for environment in ENVIRONMENTS:
        actual_lights = item_map(
            snapshots[environment]["selectiveRendering"]["lights"]
        )
        for light in contract["selectiveRendering"]["lights"]:
            light_id = light["id"]
            actual = actual_lights.get(light_id)
            prefix = f"light.{environment}.{light_id}"
            checks.append(
                presence_check(
                    f"{prefix}.present",
                    "selective-light",
                    environment,
                    f"selective light {light_id}",
                    actual,
                )
            )
            if actual is None:
                continue
            checks.append(
                equality_check(
                    f"{prefix}.owner",
                    "light-owner",
                    environment,
                    f"selective light {light_id} owner",
                    light["owner"],
                    actual["owner"],
                )
            )
            actual_layers = actual["layers"]
            if actual_layers is None:
                required_status = forbidden_status = "missing"
                required_actual: Any = None
                forbidden_actual: Any = None
                required_message = forbidden_message = (
                    f"{environment} selective light {light_id} layers are missing"
                )
            else:
                required_actual = sorted(
                    set(light["requiredLayers"]) - set(actual_layers)
                )
                forbidden_actual = sorted(
                    set(light["forbiddenLayers"]) & set(actual_layers)
                )
                required_status = "passing" if not required_actual else "failing"
                forbidden_status = "passing" if not forbidden_actual else "failing"
                required_message = (
                    f"{environment} selective light {light_id} "
                    + (
                        "targets required layers"
                        if not required_actual
                        else "is missing required layers"
                    )
                )
                forbidden_message = (
                    f"{environment} selective light {light_id} "
                    + (
                        "excludes forbidden layers"
                        if not forbidden_actual
                        else "targets forbidden layers"
                    )
                )
            checks.append(
                check(
                    f"{prefix}.required-layers",
                    "light-required-layers",
                    environment,
                    required_status,
                    light["requiredLayers"],
                    required_actual,
                    required_message,
                )
            )
            checks.append(
                check(
                    f"{prefix}.forbidden-layers",
                    "light-forbidden-layers",
                    environment,
                    forbidden_status,
                    light["forbiddenLayers"],
                    forbidden_actual,
                    forbidden_message,
                )
            )
            checks.append(
                maximum_check(
                    f"{prefix}.town-spill",
                    "town-light-spill",
                    environment,
                    f"selective light {light_id} town spill",
                    light["maxTownSpill"],
                    actual["townSpill"],
                )
            )


def append_metric_bounds(
    checks: list[dict[str, Any]],
    *,
    prefix: str,
    code_prefix: str,
    scope: str,
    label: str,
    policy: dict[str, Any],
    actual: dict[str, Any],
) -> None:
    coverage_min, coverage_max = bound_pair(policy, "Coverage")
    if coverage_min is not None or coverage_max is not None:
        checks.append(
            range_check(
                f"{prefix}.coverage",
                f"{code_prefix}-coverage",
                scope,
                f"{label} coverage",
                coverage_min,
                coverage_max,
                actual.get("coverage"),
            )
        )
    for percentile, title in (("p50", "P50"), ("p90", "P90")):
        minimum_value = policy.get(f"min{title}Luminance")
        maximum_value = policy.get(f"max{title}Luminance")
        if minimum_value is None and maximum_value is None:
            continue
        checks.append(
            range_check(
                f"{prefix}.luminance-{percentile}",
                f"{code_prefix}-luminance-{percentile}",
                scope,
                f"{label} {title} luminance",
                minimum_value,
                maximum_value,
                luminance_value(actual, percentile),
            )
        )


def append_view_checks(
    checks: list[dict[str, Any]],
    contract: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    for environment in ENVIRONMENTS:
        actual_views = item_map(snapshots[environment]["views"])
        for view in contract["views"]:
            view_id = view["id"]
            actual = actual_views.get(view_id)
            prefix = f"view.{environment}.{view_id}"
            checks.append(
                presence_check(
                    f"{prefix}.present",
                    "view",
                    environment,
                    f"view {view_id}",
                    actual,
                )
            )
            if actual is None:
                continue
            checks.append(
                equality_check(
                    f"{prefix}.camera",
                    "camera-binding",
                    environment,
                    f"view {view_id} camera",
                    view["cameraId"],
                    actual["cameraId"],
                )
            )
            append_metric_bounds(
                checks,
                prefix=prefix,
                code_prefix="view",
                scope=environment,
                label=f"view {view_id}",
                policy=view,
                actual=actual,
            )
            actual_semantics = item_map(actual["semantics"])
            for system in view["requiredSystems"]:
                system_id = system["id"]
                semantic = actual_semantics.get(system_id)
                semantic_prefix = f"{prefix}.semantic.{system_id}"
                checks.append(
                    presence_check(
                        f"{semantic_prefix}.present",
                        "semantic-system",
                        environment,
                        f"view {view_id} semantic system {system_id}",
                        semantic,
                    )
                )
                if semantic is None:
                    continue
                if "mustBeVisible" in system:
                    checks.append(
                        equality_check(
                            f"{semantic_prefix}.visibility",
                            "semantic-visibility",
                            environment,
                            f"view {view_id} semantic system {system_id} visibility",
                            system["mustBeVisible"],
                            semantic["visible"],
                        )
                    )
                append_metric_bounds(
                    checks,
                    prefix=semantic_prefix,
                    code_prefix="semantic",
                    scope=environment,
                    label=f"view {view_id} semantic system {system_id}",
                    policy=system,
                    actual=semantic,
                )


def append_angle_checks(
    checks: list[dict[str, Any]],
    contract: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    policy = contract["angleConsistency"]
    for environment in ENVIRONMENTS:
        views = item_map(snapshots[environment]["views"])
        selected = [views.get(view_id) for view_id in policy["viewIds"]]
        for view_id, view in zip(policy["viewIds"], selected):
            if policy["forbidBlackFrames"]:
                actual = view["blackFrame"] if view is not None else None
                checks.append(
                    equality_check(
                        f"angle.{environment}.{view_id}.black-frame",
                        "black-frame",
                        environment,
                        f"view {view_id} black-frame flag",
                        False,
                        actual,
                    )
                )
            if policy["forbidClipping"]:
                actual = view["clipped"] if view is not None else None
                checks.append(
                    equality_check(
                        f"angle.{environment}.{view_id}.clipping",
                        "view-clipping",
                        environment,
                        f"view {view_id} clipping flag",
                        False,
                        actual,
                    )
                )

        coverage_values = [
            view["coverage"]
            for view in selected
            if view is not None and view["coverage"] is not None
        ]
        if len(coverage_values) != len(selected):
            coverage_status = "missing"
            coverage_actual: Any = None
            coverage_message = (
                f"{environment} angle coverage diagnostics are incomplete"
            )
        else:
            coverage_median = median(coverage_values)
            ratio = (
                0.0
                if coverage_median <= 0
                else min(coverage_values) / coverage_median
            )
            coverage_actual = stable_number(ratio)
            coverage_status = (
                "passing"
                if coverage_actual >= policy["minCoverageToMedian"]
                else "failing"
            )
            coverage_message = (
                f"{environment} minimum coverage-to-median ratio "
                + (
                    "meets the contract"
                    if coverage_status == "passing"
                    else "is below the contract"
                )
            )
        checks.append(
            check(
                f"angle.{environment}.coverage-consistency",
                "angle-coverage-consistency",
                environment,
                coverage_status,
                {"min": policy["minCoverageToMedian"]},
                coverage_actual,
                coverage_message,
            )
        )

        p90_values = [
            luminance_value(view, "p90")
            for view in selected
        ]
        if any(value is None for value in p90_values):
            luminance_status = "missing"
            luminance_actual: Any = None
            luminance_message = (
                f"{environment} angle P90 luminance diagnostics are incomplete"
            )
        else:
            numeric_values = [value for value in p90_values if value is not None]
            spread = max(numeric_values) - min(numeric_values)
            luminance_actual = stable_number(spread)
            luminance_status = (
                "passing"
                if luminance_actual <= policy["maxP90LuminanceSpread"]
                else "failing"
            )
            luminance_message = (
                f"{environment} angle P90 luminance spread "
                + (
                    "is within the contract"
                    if luminance_status == "passing"
                    else "exceeds the contract"
                )
            )
        checks.append(
            check(
                f"angle.{environment}.p90-luminance-spread",
                "angle-luminance-spread",
                environment,
                luminance_status,
                {"max": policy["maxP90LuminanceSpread"]},
                luminance_actual,
                luminance_message,
            )
        )


def town_semantic_p50(
    snapshot: dict[str, Any],
    view_id: str,
    semantic_id: str,
) -> int | float | None:
    view = item_map(snapshot["views"]).get(view_id)
    if view is None:
        return None
    semantic = item_map(view["semantics"]).get(semantic_id)
    return luminance_value(semantic, "p50")


def append_town_exposure_check(
    checks: list[dict[str, Any]],
    contract: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    policy = contract["townExposure"]
    deltas: list[dict[str, Any]] = []
    missing_views: list[str] = []
    for view_id in policy["viewIds"]:
        standalone_value = town_semantic_p50(
            snapshots["standalone"],
            view_id,
            policy["semanticSystemId"],
        )
        host_value = town_semantic_p50(
            snapshots["host"],
            view_id,
            policy["semanticSystemId"],
        )
        if standalone_value is None or host_value is None:
            missing_views.append(view_id)
            continue
        deltas.append(
            {
                "viewId": view_id,
                "delta": stable_number(abs(host_value - standalone_value)),
            }
        )
    if missing_views:
        status = "missing"
        actual: Any = {
            "missingViewIds": missing_views,
            "deltas": deltas,
        }
        message = "town exposure diagnostics are incomplete"
    else:
        maximum_delta = max((item["delta"] for item in deltas), default=0)
        actual = {
            "maxDelta": stable_number(maximum_delta),
            "deltas": deltas,
        }
        status = (
            "passing"
            if maximum_delta <= policy["maxP50LuminanceDelta"]
            else "failing"
        )
        message = (
            "town exposure is invariant within the contract"
            if status == "passing"
            else "town exposure drift exceeds the contract"
        )
    checks.append(
        check(
            "town.cross.exposure-invariance",
            "town-exposure-invariance",
            "cross-snapshot",
            status,
            {"max": policy["maxP50LuminanceDelta"]},
            actual,
            message,
        )
    )


def append_performance_checks(
    checks: list[dict[str, Any]],
    contract: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    policy = contract["performance"]
    angle_view_ids = contract["angleConsistency"]["viewIds"]
    for environment in ENVIRONMENTS:
        views = item_map(snapshots[environment]["views"])
        for view in contract["views"]:
            view_id = view["id"]
            actual_view = views.get(view_id)
            actual = (
                actual_view["performance"]
                if actual_view is not None
                else None
            ) or {}
            prefix = f"performance.{environment}.{view_id}"
            checks.extend(
                (
                    maximum_check(
                        f"{prefix}.calls",
                        "draw-calls",
                        environment,
                        f"view {view_id} draw calls",
                        policy["maxCalls"],
                        actual.get("calls"),
                    ),
                    maximum_check(
                        f"{prefix}.triangles",
                        "triangles",
                        environment,
                        f"view {view_id} triangles",
                        policy["maxTriangles"],
                        actual.get("triangles"),
                    ),
                    minimum_check(
                        f"{prefix}.fps",
                        "fps",
                        environment,
                        f"view {view_id} FPS",
                        policy["minFps"],
                        actual.get("fps"),
                    ),
                    maximum_check(
                        f"{prefix}.frame-time-p50",
                        "frame-time-p50",
                        environment,
                        f"view {view_id} P50 frame time",
                        policy["maxFrameTimeP50Ms"],
                        actual.get("frameTimeP50Ms"),
                    ),
                    maximum_check(
                        f"{prefix}.frame-time-p95",
                        "frame-time-p95",
                        environment,
                        f"view {view_id} P95 frame time",
                        policy["maxFrameTimeP95Ms"],
                        actual.get("frameTimeP95Ms"),
                    ),
                )
            )

        spread_policies = (
            (
                "calls",
                "camera-direction-calls-spread",
                policy["maxDirectionCallsSpread"],
            ),
            (
                "triangles",
                "camera-direction-triangles-spread",
                policy["maxDirectionTrianglesSpread"],
            ),
            (
                "frameTimeP95Ms",
                "camera-direction-frame-time-p95-spread",
                policy["maxDirectionFrameTimeP95SpreadMs"],
            ),
        )
        for field, code, maximum in spread_policies:
            values: list[int | float] = []
            for view_id in angle_view_ids:
                view = views.get(view_id)
                performance = view.get("performance") if view is not None else None
                value = (
                    performance.get(field)
                    if isinstance(performance, dict)
                    else None
                )
                if value is not None:
                    values.append(value)
            if len(values) != len(angle_view_ids):
                status = "missing"
                actual_spread: int | float | None = None
                message = (
                    f"{environment} camera-direction {field} diagnostics "
                    "are incomplete"
                )
            else:
                actual_spread = stable_number(max(values) - min(values))
                status = "passing" if actual_spread <= maximum else "failing"
                message = (
                    f"{environment} camera-direction {field} spread "
                    + (
                        "is within the contract"
                        if status == "passing"
                        else "exceeds the contract"
                    )
                )
            checks.append(
                check(
                    f"performance.{environment}.direction-{field}-spread",
                    code,
                    environment,
                    status,
                    {"max": maximum},
                    actual_spread,
                    message,
                )
            )


def append_error_checks(
    checks: list[dict[str, Any]],
    contract: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    policy = contract["errors"]
    for environment in ENVIRONMENTS:
        errors = snapshots[environment]["errors"] or {}
        checks.append(
            maximum_check(
                f"errors.{environment}.console",
                "console-errors",
                environment,
                "console error count",
                policy["maxConsoleErrors"],
                errors.get("console"),
            )
        )
        checks.append(
            maximum_check(
                f"errors.{environment}.network",
                "network-errors",
                environment,
                "network error count",
                policy["maxNetworkErrors"],
                errors.get("network"),
            )
        )


def validate_identity(
    contract: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    for environment in ENVIRONMENTS:
        asset = snapshots[environment]["asset"]
        for field in ("assetId", "profileId"):
            expected = contract["asset"][field]
            actual = asset[field]
            if actual != expected:
                raise ContractInputError(
                    f"{environment} snapshot asset.{field} must match "
                    f"contract asset.{field} {expected!r}; got {actual!r}"
                )


def build_report(
    contract_path: Path,
    standalone_path: Path,
    host_path: Path,
) -> dict[str, Any]:
    contract_payload, contract_sha256 = load_json_object(contract_path, "contract")
    standalone_payload, standalone_sha256 = load_json_object(
        standalone_path,
        "standalone snapshot",
    )
    host_payload, host_sha256 = load_json_object(host_path, "host snapshot")
    contract = normalize_contract(contract_payload)
    snapshots = {
        "standalone": normalize_snapshot(standalone_payload, "standalone"),
        "host": normalize_snapshot(host_payload, "host"),
    }
    validate_identity(contract, snapshots)

    checks: list[dict[str, Any]] = []
    for environment in ENVIRONMENTS:
        for binding_name in ("source", "factory"):
            checks.append(
                binding_check(
                    environment,
                    binding_name,
                    contract["asset"][binding_name],
                    snapshots[environment]["asset"][binding_name],
                )
            )
    append_renderer_checks(checks, contract, snapshots)
    append_target_checks(checks, contract, snapshots)
    append_layer_checks(checks, contract, snapshots)
    append_light_checks(checks, contract, snapshots)
    append_view_checks(checks, contract, snapshots)
    append_angle_checks(checks, contract, snapshots)
    append_town_exposure_check(checks, contract, snapshots)
    append_performance_checks(checks, contract, snapshots)
    append_error_checks(checks, contract, snapshots)

    counts = {
        status: sum(item["status"] == status for item in checks)
        for status in STATUS_ORDER
    }
    ok = counts["passing"] == len(checks)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "ok": ok,
        "authority": {
            "finalVisualAuthority": "ai-vision",
            "runtimeMetrics": "diagnostic-gates-only",
            "runtimeMetricsCanApproveVisualQuality": False,
            "integrationPassIsVisualApproval": False,
        },
        "inputs": {
            "contract": {
                "path": display_path(contract_path),
                "sha256": contract_sha256,
            },
            "standalone": {
                "path": display_path(standalone_path),
                "sha256": standalone_sha256,
            },
            "host": {
                "path": display_path(host_path),
                "sha256": host_sha256,
            },
        },
        "identity": {
            "contractId": contract["contractId"],
            "assetId": contract["asset"]["assetId"],
            "profileId": contract["asset"]["profileId"],
        },
        "policy": {
            "statusOrder": list(STATUS_ORDER),
            "environmentOrder": list(ENVIRONMENTS),
            "checkOrder": "fixed-family-then-id-ascending",
            "hostDifferences": "explicit-contract-thresholds-only",
            "extraSnapshotData": "allowed-and-unchecked",
            "computedPrecision": 12,
        },
        "checks": checks,
        "summary": {
            "total": len(checks),
            **counts,
        },
    }


def report_payload(report: dict[str, Any]) -> str:
    return json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def write_report(report: dict[str, Any], output: Path | None) -> None:
    payload = report_payload(report)
    if output is None:
        print(payload, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")


def print_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print("PASS" if report["ok"] else "FAIL", file=sys.stderr)
    print(
        "checks: "
        + " ".join(
            f"{key}={summary[key]}"
            for key in ("total", *STATUS_ORDER)
        ),
        file=sys.stderr,
    )
    non_passing = [
        item for item in report["checks"] if item["status"] != "passing"
    ]
    shown = non_passing[:16]
    for item in shown:
        print(
            f"{item['status']}: {item['code']} ({item['scope']}): "
            f"{item['message']}",
            file=sys.stderr,
        )
    omitted = len(non_passing) - len(shown)
    if omitted:
        print(f"... {omitted} additional non-passing checks omitted", file=sys.stderr)


def error_report(message: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "ok": False,
        "error": {
            "code": "invalid-input",
            "message": message,
        },
    }


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, help="Render integration contract JSON")
    parser.add_argument(
        "standalone",
        type=Path,
        help="Standalone runtime snapshot JSON",
    )
    parser.add_argument("host", type=Path, help="Host runtime snapshot JSON")
    parser.add_argument("--out", type=Path, help="Write deterministic JSON here")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Also print a concise summary to stderr",
    )
    return parser


def main(argv: list[str]) -> int:
    args: argparse.Namespace | None = None
    output: Path | None = None
    try:
        args = build_parser().parse_args(argv)
        output = resolve_cli_path(args.out, "--out") if args.out else None
        contract_path = resolve_cli_path(args.contract, "contract")
        standalone_path = resolve_cli_path(args.standalone, "standalone snapshot")
        host_path = resolve_cli_path(args.host, "host snapshot")
        if output is not None and any(
            paths_alias(output, input_path)
            for input_path in (contract_path, standalone_path, host_path)
        ):
            conflicting_output = output
            output = None
            raise ContractInputError(
                "--out must not overwrite an input file: "
                f"{display_path(conflicting_output)}"
            )
        report = build_report(contract_path, standalone_path, host_path)
    except ContractInputError as exc:
        report = error_report(str(exc))
        try:
            write_report(report, output)
        except OSError:
            print(report_payload(report), end="")
        if (args is not None and args.summary) or "--summary" in argv:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        report = error_report(f"I/O error: {exc}")
        try:
            write_report(report, output)
        except OSError:
            print(report_payload(report), end="")
        if (args is not None and args.summary) or "--summary" in argv:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        write_report(report, output)
    except OSError as exc:
        destination = display_path(output) if output is not None else "stdout"
        failure = error_report(f"report cannot be written: {destination}: {exc}")
        print(report_payload(failure), end="")
        if args.summary:
            print(f"ERROR: {failure['error']['message']}", file=sys.stderr)
        return 2
    if args.summary:
        print_summary(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
