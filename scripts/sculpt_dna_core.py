#!/usr/bin/env python3
"""Shared Sculpt DNA schema, validation, and deterministic variant generation."""

from __future__ import annotations

import copy
import hashlib
import math
import random
import re
from typing import Any


DNA_SCHEMA_VERSION = "1.0"
DEFAULT_INVARIANTS = [
    "component-ids",
    "parent-links",
    "material-refs",
    "socket-ids",
    "fracture-groups",
    "attachment-roots",
    "build-pass-order",
    "feature-review-targets",
]
VALID_INVARIANTS = set(DEFAULT_INVARIANTS)
VALID_TARGET_KINDS = {"component", "material", "repetition"}
VALID_OPERATIONS = {"set", "multiply", "add"}
VALID_DISTRIBUTIONS = {"uniform", "triangular", "normal", "choice"}
MUTABLE_PATH_PREFIXES = {
    "component": (
        "dimensions.",
        "transform.scale.",
        "attachment.localEnd.",
        "attachment.baseRadius",
        "attachment.endRadius",
        "attachment.embedDepth",
        "attachment.overlap",
        "geometryDescriptor.edgeTreatment.bevelRadius",
        "surfaceDetail.",
    ),
    "material": (
        "baseColor",
        "color",
        "albedo.",
        "colorVariation.",
        "roughness.",
        "metalness.",
        "normal.",
        "bump.",
        "displacement.",
        "ambientOcclusion.",
        "wear.",
        "dirt.",
        "textureProjection.",
        "surfaceFrequencyBands.",
    ),
    "repetition": (
        "count",
        "density",
        "spacing",
        "scale",
        "jitter",
        "radius",
        "length",
    ),
}


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def safe_target_slug(value: Any) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return (slug or "object")[:64].rstrip("-") or "object"


def make_disabled_sculpt_dna() -> dict[str, Any]:
    return {
        "schemaVersion": DNA_SCHEMA_VERSION,
        "enabled": False,
        "strategy": "constraint-aware semantic variation",
        "parameters": [],
        "constraints": [],
        "invariants": list(DEFAULT_INVARIANTS),
        "variantPolicy": {
            "defaultCount": 4,
            "defaultSeed": 1337,
            "maxAttemptsPerVariant": 64,
            "resetReviewEvidence": True,
        },
        "authoringRule": (
            "Enable only after the base ObjectSculptSpec is structurally meaningful. "
            "Run sculpt_dna.py init to derive safe starter controls, then replace generic "
            "controls with object-specific semantic parameters."
        ),
    }


def _target(kind: str, record_id: str, path: str) -> dict[str, str]:
    return {"kind": kind, "id": record_id, "path": path}


def make_default_sculpt_dna(spec: dict[str, Any]) -> dict[str, Any]:
    dna = make_disabled_sculpt_dna()
    dna["enabled"] = True
    parameters: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []

    components = [item for item in spec.get("componentTree", []) if isinstance(item, dict)]
    root = next((item for item in components if item.get("id") == "root"), None)
    if root is None:
        root = next((item for item in components if not item.get("parent")), components[0] if components else None)
    if root is not None:
        root_id = str(root.get("id") or "root")
        root_profile = root.get("actionProfile") if isinstance(root.get("actionProfile"), dict) else {}
        root_pivot = root_profile.get("pivot") if isinstance(root_profile.get("pivot"), dict) else {}
        root_collider = root_profile.get("collider") if isinstance(root_profile.get("collider"), dict) else {}
        root_sockets = root_profile.get("sockets") if isinstance(root_profile.get("sockets"), list) else []
        root_constraints = root_profile.get("constraints") if isinstance(root_profile.get("constraints"), list) else []
        pivot_position = root_pivot.get("localPosition")
        pivot_position_safe = (
            pivot_position is None
            or (
                isinstance(pivot_position, list)
                and len(pivot_position) == 3
                and all(is_number(value) and abs(float(value)) <= 1e-12 for value in pivot_position)
            )
        )
        pivot_safe = (
            not root_pivot
            or (
                root_pivot.get("mode", "center") == "center"
                and pivot_position_safe
            )
        )
        collider_safe = not root_collider or root_collider.get("type") == "none"
        has_child_components = any(item.get("parent") == root_id for item in components)
        geometry_controls_safe = (
            not has_child_components
            and not root_sockets
            and not root_constraints
            and pivot_safe
            and collider_safe
        )
        transform = root.get("transform") if isinstance(root.get("transform"), dict) else {}
        scale = transform.get("scale")
        dimensions = root.get("dimensions") if isinstance(root.get("dimensions"), dict) else {}
        dimension_values = [
            dimensions.get("width"),
            dimensions.get("height"),
            dimensions.get("depth"),
        ]
        target_paths: list[str] | None = None
        base_values: list[float] | None = None
        if all(is_number(value) and float(value) > 0 for value in dimension_values):
            target_paths = ["dimensions.width", "dimensions.height", "dimensions.depth"]
            base_values = [float(value) for value in dimension_values]
        elif isinstance(scale, list) and len(scale) == 3 and all(is_number(value) and float(value) > 0 for value in scale):
            target_paths = ["transform.scale.0", "transform.scale.1", "transform.scale.2"]
            base_values = [float(value) for value in scale]
        if geometry_controls_safe and target_paths is not None and base_values is not None:
            axis_names = ("width", "height", "depth")
            semantic_effects = (
                ["silhouette", "horizontal proportions", "collider review"],
                ["silhouette", "vertical proportions", "pivot review"],
                ["depth inference", "side-view proportions", "collider review"],
            )
            for index, axis_name in enumerate(axis_names):
                parameters.append(
                    {
                        "id": f"{root_id}-{axis_name}",
                        "label": f"{root_id} {axis_name}",
                        "target": _target("component", root_id, target_paths[index]),
                        "operation": "multiply",
                        "distribution": "triangular",
                        "range": {"min": 0.85, "max": 1.15},
                        "precision": 4,
                        "semanticEffects": semantic_effects[index],
                    }
                )
            constraints.extend(
                [
                    {
                        "id": f"{root_id}-width-height-ratio",
                        "type": "ratio",
                        "left": _target("component", root_id, target_paths[0]),
                        "right": _target("component", root_id, target_paths[1]),
                        "min": round((base_values[0] / base_values[1]) * 0.8, 4),
                        "max": round((base_values[0] / base_values[1]) * 1.2, 4),
                    },
                    {
                        "id": f"{root_id}-depth-width-ratio",
                        "type": "ratio",
                        "left": _target("component", root_id, target_paths[2]),
                        "right": _target("component", root_id, target_paths[0]),
                        "min": round((base_values[2] / base_values[0]) * 0.8, 4),
                        "max": round((base_values[2] / base_values[0]) * 1.2, 4),
                    },
                ]
            )

    materials = [item for item in spec.get("materials", []) if isinstance(item, dict)]
    for material in materials:
        material_id = str(material.get("id") or "")
        if not material_id:
            continue
        roughness = material.get("roughness")
        roughness_base = roughness.get("base") if isinstance(roughness, dict) else None
        if is_number(roughness_base):
            lower = max(0.0, float(roughness_base) - 0.12)
            upper = min(1.0, float(roughness_base) + 0.12)
            if lower < upper:
                parameters.append(
                    {
                        "id": f"{material_id}-roughness",
                        "label": f"{material_id} roughness",
                        "target": _target("material", material_id, "roughness.base"),
                        "operation": "set",
                        "distribution": "triangular",
                        "range": {"min": round(lower, 4), "max": round(upper, 4)},
                        "precision": 4,
                        "semanticEffects": ["highlight width", "surface age", "material readability"],
                    }
                )
        color_variation = material.get("colorVariation")
        palette = color_variation.get("palette") if isinstance(color_variation, dict) else None
        if (
            isinstance(palette, list)
            and len(palette) > 1
            and all(isinstance(color, str) for color in palette)
        ):
            parameters.append(
                {
                    "id": f"{material_id}-dominant-palette",
                    "label": f"{material_id} dominant palette color",
                    "target": _target("material", material_id, "colorVariation.palette.0"),
                    "operation": "set",
                    "distribution": "choice",
                    "choices": list(dict.fromkeys(palette)),
                    "semanticEffects": ["palette family", "local albedo variation"],
                }
            )

    repetitions = [item for item in spec.get("repetitionSystems", []) if isinstance(item, dict)]
    for repetition in repetitions:
        repetition_id = str(repetition.get("id") or "")
        count = repetition.get("count")
        if not repetition_id or not is_number(count) or float(count) <= 0:
            continue
        lower = max(1, round(float(count) * 0.8))
        upper = max(lower, round(float(count) * 1.2))
        parameters.append(
            {
                "id": f"{repetition_id}-count",
                "label": f"{repetition_id} repetition count",
                "target": _target("repetition", repetition_id, "count"),
                "operation": "set",
                "distribution": "triangular",
                "range": {"min": lower, "max": upper},
                "precision": 0,
                "semanticEffects": ["repetition density", "draw-call and triangle budget"],
            }
        )

    dna["parameters"] = parameters
    dna["constraints"] = constraints
    dna["authoringRule"] = (
        "These controls are conservative starters. Rename them in object language, add coupling groups "
        "for dependent proportions, and add ratio/range constraints before generating a production family."
    )
    return dna


def _path_tokens(path: str) -> list[str | int]:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("target.path must be a non-empty dotted path")
    tokens: list[str | int] = []
    for segment in path.split("."):
        if not segment or "__" in segment:
            raise ValueError(f"unsafe target path segment {segment!r}")
        tokens.append(int(segment) if segment.isdigit() else segment)
    return tokens


def _record_for_target(spec: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    kind = target.get("kind")
    record_id = target.get("id")
    collection_name = {
        "component": "componentTree",
        "material": "materials",
        "repetition": "repetitionSystems",
    }.get(kind)
    if not isinstance(kind, str) or collection_name is None:
        raise ValueError(f"target.kind must be one of: {', '.join(sorted(VALID_TARGET_KINDS))}")
    if not isinstance(record_id, str) or not record_id:
        raise ValueError(f"{kind} target.id must be a non-empty string")
    collection = spec.get(collection_name)
    if not isinstance(collection, list):
        raise ValueError(f"spec.{collection_name} must be an array")
    record = next(
        (item for item in collection if isinstance(item, dict) and item.get("id") == record_id),
        None,
    )
    if record is None:
        raise ValueError(f"{kind} target {record_id!r} does not exist")
    return record


def _path_is_mutable(kind: str, path: str) -> bool:
    return any(
        path.startswith(prefix) if prefix.endswith(".") else path == prefix or path.startswith(prefix + ".")
        for prefix in MUTABLE_PATH_PREFIXES[kind]
    )


def resolve_target(spec: dict[str, Any], target: dict[str, Any]) -> Any:
    if not isinstance(target, dict):
        raise ValueError("target must be an object")
    kind = target.get("kind")
    path = target.get("path")
    if not isinstance(kind, str) or kind not in VALID_TARGET_KINDS:
        raise ValueError(f"target.kind must be one of: {', '.join(sorted(VALID_TARGET_KINDS))}")
    if not isinstance(path, str) or not _path_is_mutable(kind, path):
        raise ValueError(f"{kind} target path {path!r} is not mutable in Sculpt DNA v{DNA_SCHEMA_VERSION}")
    current: Any = _record_for_target(spec, target)
    for token in _path_tokens(path):
        if isinstance(token, int):
            if not isinstance(current, list) or token < 0 or token >= len(current):
                raise ValueError(f"target path {path!r} has invalid list index {token}")
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                raise ValueError(f"target path {path!r} does not exist at {token!r}")
            current = current[token]
    return current


def assign_target(spec: dict[str, Any], target: dict[str, Any], value: Any) -> None:
    path = str(target.get("path") or "")
    tokens = _path_tokens(path)
    current: Any = _record_for_target(spec, target)
    for token in tokens[:-1]:
        current = current[token]
    final = tokens[-1]
    if isinstance(final, int):
        if not isinstance(current, list) or final < 0 or final >= len(current):
            raise ValueError(f"target path {path!r} has invalid final list index {final}")
        current[final] = value
    else:
        if not isinstance(current, dict) or final not in current:
            raise ValueError(f"target path {path!r} does not exist at {final!r}")
        current[final] = value


def _validate_target(spec: dict[str, Any], value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return
    try:
        resolve_target(spec, value)
    except ValueError as exc:
        errors.append(f"{label}: {exc}")


def _validate_constraint_shape(
    spec: dict[str, Any],
    constraint: Any,
    index: int,
    errors: list[str],
) -> None:
    label = f"sculptDNA.constraints[{index}]"
    if not isinstance(constraint, dict):
        errors.append(f"{label} must be an object")
        return
    constraint_id = constraint.get("id")
    if not isinstance(constraint_id, str) or not constraint_id:
        errors.append(f"{label}.id is required")
    constraint_type = constraint.get("type")
    if not isinstance(constraint_type, str):
        errors.append(f"{label}.type must be range, ratio, or equals")
        return
    if constraint_type == "range":
        _validate_target(spec, constraint.get("target"), f"{label}.target", errors)
        try:
            target_value = resolve_target(spec, constraint.get("target"))
            if not is_number(target_value):
                errors.append(f"{label}.target must resolve to a number")
        except (TypeError, ValueError):
            pass
        if "min" not in constraint and "max" not in constraint:
            errors.append(f"{label} range constraint needs min or max")
        for field in ("min", "max"):
            if field in constraint and not is_number(constraint[field]):
                errors.append(f"{label}.{field} must be numeric")
    elif constraint_type == "ratio":
        _validate_target(spec, constraint.get("left"), f"{label}.left", errors)
        _validate_target(spec, constraint.get("right"), f"{label}.right", errors)
        for side in ("left", "right"):
            try:
                target_value = resolve_target(spec, constraint.get(side))
                if not is_number(target_value):
                    errors.append(f"{label}.{side} must resolve to a number")
            except (TypeError, ValueError):
                pass
        for field in ("min", "max"):
            if not is_number(constraint.get(field)):
                errors.append(f"{label}.{field} must be numeric")
    elif constraint_type == "equals":
        _validate_target(spec, constraint.get("left"), f"{label}.left", errors)
        _validate_target(spec, constraint.get("right"), f"{label}.right", errors)
        tolerance = constraint.get("tolerance", 0)
        if not is_number(tolerance) or float(tolerance) < 0:
            errors.append(f"{label}.tolerance must be a non-negative number")
    else:
        errors.append(f"{label}.type must be range, ratio, or equals")
    if (
        isinstance(constraint_type, str)
        and constraint_type in {"range", "ratio"}
        and is_number(constraint.get("min"))
        and is_number(constraint.get("max"))
        and float(constraint["min"]) > float(constraint["max"])
    ):
        errors.append(f"{label}.min must be <= max")


def validate_sculpt_dna_block(
    spec: dict[str, Any],
    dna: Any | None = None,
) -> tuple[list[str], list[str]]:
    block = spec.get("sculptDNA") if dna is None else dna
    errors: list[str] = []
    warnings: list[str] = []
    if block is None:
        return errors, warnings
    if not isinstance(block, dict):
        return ["sculptDNA must be an object"], warnings
    if block.get("schemaVersion") != DNA_SCHEMA_VERSION:
        errors.append(f"sculptDNA.schemaVersion must be {DNA_SCHEMA_VERSION!r}")
    enabled = block.get("enabled")
    if not isinstance(enabled, bool):
        errors.append("sculptDNA.enabled must be boolean")
    strategy = block.get("strategy")
    if strategy is not None and not isinstance(strategy, str):
        errors.append("sculptDNA.strategy must be a string")
    authoring_rule = block.get("authoringRule")
    if authoring_rule is not None and not isinstance(authoring_rule, str):
        errors.append("sculptDNA.authoringRule must be a string")

    parameters = block.get("parameters")
    if not isinstance(parameters, list):
        errors.append("sculptDNA.parameters must be an array")
        parameters = []
    elif enabled and not parameters:
        errors.append("enabled sculptDNA requires at least one parameter")
    parameter_ids: set[str] = set()
    mutable_target_keys: set[tuple[str, str, str]] = set()
    group_distributions: dict[str, str] = {}
    for index, parameter in enumerate(parameters):
        label = f"sculptDNA.parameters[{index}]"
        if not isinstance(parameter, dict):
            errors.append(f"{label} must be an object")
            continue
        parameter_id = parameter.get("id")
        if not isinstance(parameter_id, str) or not parameter_id:
            errors.append(f"{label}.id is required")
        elif parameter_id in parameter_ids:
            errors.append(f"duplicate Sculpt DNA parameter id {parameter_id!r}")
        else:
            parameter_ids.add(parameter_id)
        target = parameter.get("target")
        _validate_target(spec, target, f"{label}.target", errors)
        target_identity = target_key(target)
        if target_identity is not None:
            mutable_target_keys.add(target_identity)
        operation = parameter.get("operation")
        if not isinstance(operation, str) or operation not in VALID_OPERATIONS:
            errors.append(f"{label}.operation must be one of: {', '.join(sorted(VALID_OPERATIONS))}")
        distribution = parameter.get("distribution")
        if not isinstance(distribution, str) or distribution not in VALID_DISTRIBUTIONS:
            errors.append(
                f"{label}.distribution must be one of: {', '.join(sorted(VALID_DISTRIBUTIONS))}"
            )
        current_value: Any = None
        try:
            current_value = resolve_target(spec, target)
        except (ValueError, TypeError):
            pass
        if distribution == "choice":
            choices = parameter.get("choices")
            if not isinstance(choices, list) or not choices:
                errors.append(f"{label}.choices must be a non-empty array")
            elif current_value is not None:
                compatible = all(
                    (
                        is_number(choice)
                        if is_number(current_value)
                        else isinstance(choice, type(current_value))
                    )
                    for choice in choices
                )
                if not compatible:
                    errors.append(f"{label}.choices must match the current target value type")
            if operation != "set":
                errors.append(f"{label} choice distribution requires operation='set'")
        else:
            value_range = parameter.get("range")
            if not isinstance(value_range, dict):
                errors.append(f"{label}.range must be an object")
            else:
                minimum = value_range.get("min")
                maximum = value_range.get("max")
                if not is_number(minimum) or not is_number(maximum):
                    errors.append(f"{label}.range min and max must be numeric")
                elif float(minimum) > float(maximum):
                    errors.append(f"{label}.range min must be <= max")
            if not is_number(current_value):
                errors.append(f"{label}.target must currently resolve to a number")
        precision = parameter.get("precision", 4)
        if not isinstance(precision, int) or isinstance(precision, bool) or not 0 <= precision <= 8:
            errors.append(f"{label}.precision must be an integer from 0 to 8")
        group = parameter.get("group")
        if group is not None and (not isinstance(group, str) or not group):
            errors.append(f"{label}.group must be a non-empty string")
        elif isinstance(group, str):
            if distribution == "choice":
                errors.append(f"{label}.group is not supported for choice distributions")
            previous_distribution = group_distributions.setdefault(group, str(distribution))
            if previous_distribution != distribution:
                errors.append(
                    f"{label}.distribution must match other parameters in group {group!r}"
                )
        effects = parameter.get("semanticEffects")
        if effects is not None and (
            not isinstance(effects, list) or not all(isinstance(item, str) for item in effects)
        ):
            errors.append(f"{label}.semanticEffects must be an array of strings")

    constraints = block.get("constraints")
    if not isinstance(constraints, list):
        errors.append("sculptDNA.constraints must be an array")
        constraints = []
    constraint_ids: set[str] = set()
    for index, constraint in enumerate(constraints):
        _validate_constraint_shape(spec, constraint, index, errors)
        if isinstance(constraint, dict) and isinstance(constraint.get("id"), str):
            if constraint["id"] in constraint_ids:
                errors.append(f"duplicate Sculpt DNA constraint id {constraint['id']!r}")
            constraint_ids.add(constraint["id"])
        if isinstance(constraint, dict) and constraint.get("type") == "ratio":
            right_key = target_key(constraint.get("right"))
            try:
                right_value = resolve_target(spec, constraint.get("right"))
            except (TypeError, ValueError):
                right_value = None
            if (
                is_number(right_value)
                and abs(float(right_value)) <= 1e-12
                and right_key not in mutable_target_keys
            ):
                errors.append(
                    f"sculptDNA.constraints[{index}].right is an immutable zero denominator"
                )

    invariants = block.get("invariants")
    if not isinstance(invariants, list) or not all(isinstance(item, str) for item in invariants):
        errors.append("sculptDNA.invariants must be an array of strings")
    else:
        unknown = sorted(set(invariants) - VALID_INVARIANTS)
        if unknown:
            errors.append(f"sculptDNA.invariants contains unknown values: {', '.join(unknown)}")

    policy = block.get("variantPolicy")
    if not isinstance(policy, dict):
        errors.append("sculptDNA.variantPolicy must be an object")
    else:
        for field in ("defaultCount", "maxAttemptsPerVariant"):
            value = policy.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                errors.append(f"sculptDNA.variantPolicy.{field} must be a positive integer")
        default_count = policy.get("defaultCount")
        if (
            isinstance(default_count, int)
            and not isinstance(default_count, bool)
            and default_count > 100
        ):
            errors.append("sculptDNA.variantPolicy.defaultCount must be <= 100")
        attempts = policy.get("maxAttemptsPerVariant")
        if isinstance(attempts, int) and not isinstance(attempts, bool) and attempts > 10000:
            errors.append("sculptDNA.variantPolicy.maxAttemptsPerVariant must be <= 10000")
        default_seed = policy.get("defaultSeed")
        if not isinstance(default_seed, int) or isinstance(default_seed, bool):
            errors.append("sculptDNA.variantPolicy.defaultSeed must be an integer")
        reset = policy.get("resetReviewEvidence")
        if not isinstance(reset, bool):
            errors.append("sculptDNA.variantPolicy.resetReviewEvidence must be boolean")
        elif enabled and reset is not True:
            errors.append(
                "enabled sculptDNA requires variantPolicy.resetReviewEvidence=true"
            )

    if not errors and enabled:
        for constraint in constraints:
            failures = constraint_failures(spec, [constraint])
            if not failures:
                continue
            involved_targets = constraint_targets(constraint)
            if involved_targets & mutable_target_keys:
                warnings.extend(
                    f"base spec violates Sculpt DNA constraint: {failure}"
                    for failure in failures
                )
            else:
                errors.extend(
                    f"base spec violates immutable Sculpt DNA constraint: {failure}"
                    for failure in failures
                )
    return errors, warnings


def target_key(target: Any) -> tuple[str, str, str] | None:
    if not isinstance(target, dict):
        return None
    kind = target.get("kind")
    record_id = target.get("id")
    path = target.get("path")
    if not all(isinstance(item, str) and item for item in (kind, record_id, path)):
        return None
    return kind, record_id, path


def constraint_targets(constraint: Any) -> set[tuple[str, str, str]]:
    if not isinstance(constraint, dict):
        return set()
    keys = ("target",) if constraint.get("type") == "range" else ("left", "right")
    return {
        key
        for key in (target_key(constraint.get(field)) for field in keys)
        if key is not None
    }


def constraint_failures(
    spec: dict[str, Any],
    constraints: list[dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    for index, constraint in enumerate(constraints):
        constraint_id = str(constraint.get("id") or f"constraint-{index}")
        constraint_type = constraint.get("type")
        try:
            if constraint_type == "range":
                value = resolve_target(spec, constraint["target"])
                if not is_number(value):
                    failures.append(f"{constraint_id}: target is not numeric")
                    continue
                if "min" in constraint and float(value) < float(constraint["min"]):
                    failures.append(f"{constraint_id}: {value} < min {constraint['min']}")
                if "max" in constraint and float(value) > float(constraint["max"]):
                    failures.append(f"{constraint_id}: {value} > max {constraint['max']}")
            elif constraint_type == "ratio":
                left = resolve_target(spec, constraint["left"])
                right = resolve_target(spec, constraint["right"])
                if not is_number(left) or not is_number(right) or abs(float(right)) <= 1e-12:
                    failures.append(f"{constraint_id}: ratio operands must be numeric with non-zero right")
                    continue
                ratio = float(left) / float(right)
                if ratio < float(constraint["min"]) or ratio > float(constraint["max"]):
                    failures.append(
                        f"{constraint_id}: ratio {ratio:.6f} outside "
                        f"[{constraint['min']}, {constraint['max']}]"
                    )
            elif constraint_type == "equals":
                left = resolve_target(spec, constraint["left"])
                right = resolve_target(spec, constraint["right"])
                tolerance = float(constraint.get("tolerance", 0))
                if is_number(left) and is_number(right):
                    if abs(float(left) - float(right)) > tolerance:
                        failures.append(
                            f"{constraint_id}: |{left} - {right}| exceeds tolerance {tolerance}"
                        )
                elif left != right:
                    failures.append(f"{constraint_id}: values are not equal")
        except (KeyError, TypeError, ValueError) as exc:
            failures.append(f"{constraint_id}: {exc}")
    return failures


def _id_tuple(value: Any) -> tuple[Any, ...]:
    return tuple(
        item.get("id") for item in value if isinstance(item, dict)
    ) if isinstance(value, list) else ()


def _value_tuple(value: Any) -> tuple[Any, ...]:
    return tuple(value) if isinstance(value, list) else ()


def semantic_snapshot(spec: dict[str, Any]) -> dict[str, Any]:
    components = [item for item in spec.get("componentTree", []) if isinstance(item, dict)]
    materials = [item for item in spec.get("materials", []) if isinstance(item, dict)]
    repetitions = [item for item in spec.get("repetitionSystems", []) if isinstance(item, dict)]
    return {
        "component-ids": [item.get("id") for item in components],
        "parent-links": [(item.get("id"), item.get("parent")) for item in components],
        "material-refs": [
            (item.get("id"), item.get("material"), _value_tuple(item.get("materialLayers")))
            for item in components
        ]
        + [("material-id", item.get("id")) for item in materials],
        "socket-ids": [
            (
                item.get("id"),
                _id_tuple(
                    item.get("actionProfile", {}).get("sockets")
                    if isinstance(item.get("actionProfile"), dict)
                    else None
                ),
            )
            for item in components
        ],
        "fracture-groups": [
            (
                item.get("id"),
                (
                    item.get("actionProfile", {}).get("destruction", {}).get("fractureGroup")
                    if isinstance(item.get("actionProfile"), dict)
                    and isinstance(item.get("actionProfile", {}).get("destruction"), dict)
                    else None
                ),
            )
            for item in components
        ],
        "attachment-roots": [
            (
                item.get("id"),
                (
                    item.get("attachment", {}).get("parentId"),
                    item.get("attachment", {}).get("parentSocket"),
                    item.get("attachment", {}).get("localStart"),
                )
                if isinstance(item.get("attachment"), dict)
                else None,
            )
            for item in components
        ],
        "build-pass-order": [
            item.get("id") for item in spec.get("buildPasses", []) if isinstance(item, dict)
        ],
        "feature-review-targets": [
            item.get("id")
            for item in spec.get("featureReviewTargets", [])
            if isinstance(item, dict)
        ],
        "repetition-ids": [item.get("id") for item in repetitions],
    }


def invariant_failures(
    before: dict[str, Any],
    after: dict[str, Any],
    invariant_names: list[str],
) -> list[str]:
    failures: list[str] = []
    for invariant in invariant_names:
        if before.get(invariant) != after.get(invariant):
            failures.append(f"{invariant} changed")
    if before.get("repetition-ids") != after.get("repetition-ids"):
        failures.append("repetition system ids changed")
    return failures


def _sample_unit(rng: random.Random, distribution: str) -> float:
    if distribution == "triangular":
        return rng.triangular(0.0, 1.0, 0.5)
    if distribution == "normal":
        return min(1.0, max(0.0, rng.gauss(0.5, 0.18)))
    return rng.random()


def _sample_parameter(
    parameter: dict[str, Any],
    current: Any,
    rng: random.Random,
    group_samples: dict[str, float],
) -> Any:
    distribution = str(parameter.get("distribution"))
    operation = str(parameter.get("operation"))
    if distribution == "choice":
        return copy.deepcopy(rng.choice(parameter["choices"]))
    group = parameter.get("group")
    if isinstance(group, str):
        if group not in group_samples:
            group_samples[group] = _sample_unit(rng, distribution)
        unit = group_samples[group]
    else:
        unit = _sample_unit(rng, distribution)
    value_range = parameter["range"]
    sampled = float(value_range["min"]) + (float(value_range["max"]) - float(value_range["min"])) * unit
    if operation == "multiply":
        result = float(current) * sampled
    elif operation == "add":
        result = float(current) + sampled
    else:
        result = sampled
    precision = int(parameter.get("precision", 4))
    rounded = round(result, precision)
    return int(rounded) if precision == 0 else rounded


def _variant_seed(root_seed: int, index: int, attempt: int) -> int:
    digest = hashlib.sha256(f"{root_seed}:{index}:{attempt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _reset_review_evidence(spec: dict[str, Any]) -> None:
    spec["reviewHistory"] = []
    spec["visualEvidence"] = []
    pipeline = spec.get("sculptPipeline")
    build_passes = [
        item.get("id") for item in spec.get("buildPasses", []) if isinstance(item, dict)
    ]
    first_pass = next((item for item in build_passes if isinstance(item, str)), "blockout")
    if isinstance(pipeline, dict):
        pipeline["currentPass"] = first_pass
        pipeline["completedPasses"] = []
        pipeline["lastCompletedPass"] = ""
        pipeline["blockedReason"] = (
            "Sculpt DNA changed visible geometry or material parameters; this variant needs fresh "
            "browser and AI-vision evidence before deeper passes unlock."
        )
        pipeline["nextRequiredEvidence"] = [
            "fresh blockout browser screenshot for this Sculpt DNA variant",
            "side-by-side comparison against the intended family reference or design target",
            "AI vision layer and semantic feature scores for this variant",
            "new reviewHistory entry with action=continue",
        ]


def generate_variant(
    source_spec: dict[str, Any],
    root_seed: int,
    index: int,
    dna: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    block = source_spec.get("sculptDNA") if dna is None else dna
    errors, _ = validate_sculpt_dna_block(source_spec, block)
    if errors:
        raise ValueError("; ".join(errors))
    if not isinstance(block, dict) or block.get("enabled") is not True:
        raise ValueError("sculptDNA must be enabled before variant generation")
    policy = block["variantPolicy"]
    max_attempts = int(policy.get("maxAttemptsPerVariant", 64))
    constraints = block.get("constraints", [])
    invariants = block.get("invariants", DEFAULT_INVARIANTS)
    before = semantic_snapshot(source_spec)
    last_failures: list[str] = []

    for attempt in range(max_attempts):
        seed = _variant_seed(root_seed, index, attempt)
        rng = random.Random(seed)
        variant = copy.deepcopy(source_spec)
        mutations: list[dict[str, Any]] = []
        group_samples: dict[str, float] = {}
        for parameter in block["parameters"]:
            current = resolve_target(variant, parameter["target"])
            generated = _sample_parameter(parameter, current, rng, group_samples)
            assign_target(variant, parameter["target"], generated)
            mutations.append(
                {
                    "parameterId": parameter["id"],
                    "target": copy.deepcopy(parameter["target"]),
                    "before": current,
                    "after": generated,
                }
            )
        last_failures = constraint_failures(variant, constraints)
        if last_failures:
            continue
        invariant_errors = invariant_failures(before, semantic_snapshot(variant), invariants)
        if invariant_errors:
            raise ValueError("; ".join(invariant_errors))
        _reset_review_evidence(variant)
        source_target_id = str(source_spec.get("targetId") or "object")
        source_target_slug = safe_target_slug(source_target_id)
        variant_id = f"{source_target_slug}-v{index:03d}"
        variant["targetId"] = variant_id
        provenance = {
            "sculptDNAVersion": DNA_SCHEMA_VERSION,
            "variantId": variant_id,
            "sourceTargetId": source_target_id,
            "sourceTargetSlug": source_target_slug,
            "rootSeed": root_seed,
            "variantSeed": seed,
            "index": index,
            "attempt": attempt + 1,
            "mutations": mutations,
            "invariants": {"ok": True, "checked": list(invariants)},
            "reviewEvidenceReset": True,
        }
        variant["variantProvenance"] = provenance
        return variant, provenance

    failure_text = "; ".join(last_failures) if last_failures else "no valid sample found"
    raise ValueError(
        f"could not generate variant {index} after {max_attempts} attempts: {failure_text}"
    )
