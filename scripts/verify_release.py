#!/usr/bin/env python3
"""Verify flagship specs, production evidence, reviews, and artifact manifests."""

from __future__ import annotations

import json
import math
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from typing import Any

from sculpt_dna import variant_gate
from validate_sculpt_spec import validate_spec


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_REVIEW_POLICY = {
    "version": 2,
    "authoritativeReview": "latest-per-pass",
    "evidenceBinding": "local-sha256-required",
}
PRODUCTION_PASS_ORDER = (
    "blockout",
    "structural-pass",
    "form-refinement",
    "material-pass",
    "surface-pass",
    "lighting-pass",
    "interaction-pass",
    "optimization-pass",
)
SEOUL_HERO_SHA256 = "949c602517b73ed10c6889ef8b62601ea4a182773513693308635157b638be10"
SEOUL_GIF_SHA256 = "143856881f5302ddcf1a022ec4b8cb2c9d18e06f746cd4ac289b20ad7193afc1"
SEOUL_INTERMEDIATE_SHA256 = (
    "34ff48d78ee5f0db9a81eba4a172dfa96fe0e15275a2c45ac8e4fd06f8b92b76"
)
SEOUL_RUNTIME_SEED_DERIVATION = "bigint-low-32"
SEOUL_ROOT_SEED = 20260712
SEOUL_VISUAL_THRESHOLD = 0.86
SEOUL_REQUIRED_LAYER_SCORES = frozenset(
    {
        "silhouetteProportion",
        "componentStructure",
        "formDetail",
        "materialSurface",
        "lightingCamera",
    }
)
SEOUL_CRITICAL_FEATURES = frozenset(
    {
        "palace-axial-hierarchy",
        "korean-roof-system",
        "ceremonial-negative-space",
        "atmospheric-depth-layers",
        "asymmetric-mountain-composition",
    }
)
SEOUL_PRODUCTION_VARIANTS = {
    "seoul-palace-hero-v001": {
        "candidateIndex": 18,
        "sourceSeed": "1996682606581385420",
        "runtimeSeed": 1987840204,
    },
    "seoul-palace-hero-v002": {
        "candidateIndex": 21,
        "sourceSeed": "15943353861346949412",
        "runtimeSeed": 2314205476,
    },
    "seoul-palace-hero-v003": {
        "candidateIndex": 22,
        "sourceSeed": "13524487735928202990",
        "runtimeSeed": 2770380526,
    },
}
REPOLIS_CANONICAL_SOURCE_FILES = (
    "index.html",
    "main.js",
    "style.css",
    "repolis-output/createRepolisHero.js",
    "repolis-output/repolis-hero-profile.json",
    "../repolis-tree/object-sculpt-spec.json",
)
BRICK_CANONICAL_SOURCE_FILES = (
    "index.html",
    "main.js",
    "style.css",
    "package.json",
    "package-lock.json",
    "vite.config.js",
    "scripts/capture.mjs",
    "brick-output/createBrickOffroad.js",
    "brick-output/createBrickOffroad.d.ts",
    "brick-output/brick-variant-config.json",
    "brick-output/brick-offroad-profile.json",
    "../../scripts/append_sculpt_review.py",
    "../../scripts/make_visual_comparison_sheet.py",
    "../../scripts/sculpt_dna.py",
    "../../scripts/sculpt_pass_orchestrator.py",
    "../../scripts/validate_sculpt_spec.py",
    "../../scripts/visual_evidence_hashes.py",
    "../../scripts/migrate_review_policy.py",
    "../../scripts/refresh_brick_reviews.py",
    "../../scripts/verify_release.py",
    "../brick-offroad/object-sculpt-spec.json",
    "../showcase/variants/brick/brick-offroad-v001.json",
    "../showcase/variants/brick/brick-offroad-v002.json",
    "../showcase/variants/brick/brick-offroad-v003.json",
    "../showcase/variants/brick/sculpt-dna-manifest.json",
    "../showcase/showcase-review.json",
    "reference/brick-offroad-reference.jpeg",
)
BRICK_FINGERPRINT_SOURCE_FILES = (
    "main.js",
    "brick-output/createBrickOffroad.js",
)
SEOUL_CANONICAL_SOURCE_FILES = (
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
    "reference/seoul-challenge-reference.jpeg",
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
)
EXPECTED_ARTIFACT_SOURCES = {
    "repolis-hero": REPOLIS_CANONICAL_SOURCE_FILES,
    "brick-offroad-hero": BRICK_CANONICAL_SOURCE_FILES,
    "seoul-palace-hero": SEOUL_CANONICAL_SOURCE_FILES,
}
SEOUL_RUNTIME_SOURCE_FILES = (
    "index.html",
    "main.js",
    "package-lock.json",
    "package.json",
    "reference/seoul-challenge-reference.jpeg",
    "style.css",
    "vite.config.js",
    "seoul-output/createSeoulPalaceHero.js",
    "seoul-output/createProceduralMaterials.js",
    "seoul-output/seoul-variant-config.json",
)
EXPECTED_ARTIFACT_OUTPUTS = {
    "repolis-hero": {
        "../../assets/repolis-tree-hero.png",
        "../../assets/repolis-tree-hero.gif",
        "evidence/blockout.webp",
        "evidence/blockout-comparison.webp",
        "evidence/structural-pass.webp",
        "evidence/structural-pass-comparison.webp",
        "evidence/form-refinement.webp",
        "evidence/form-refinement-comparison.webp",
        "evidence/material-pass.webp",
        "evidence/material-pass-comparison.webp",
        "evidence/surface-pass.webp",
        "evidence/surface-pass-comparison.webp",
        "evidence/final.webp",
        "evidence/final-comparison.webp",
    },
    "brick-offroad-hero": {
        "../../assets/brick-offroad-hero.png",
        "../../assets/brick-offroad-hero.gif",
        "../../assets/brick-offroad-sculpt-dna-result.png",
        "evidence/door-articulation.webp",
        "evidence/showcase-comparison.webp",
        "evidence/blockout.webp",
        "evidence/blockout-comparison.webp",
        "evidence/structural-pass.webp",
        "evidence/structural-pass-comparison.webp",
        "evidence/form-refinement.webp",
        "evidence/form-refinement-comparison.webp",
        "evidence/material-pass.webp",
        "evidence/material-pass-comparison.webp",
        "evidence/surface-pass.webp",
        "evidence/surface-pass-comparison.webp",
        "evidence/final.webp",
        "evidence/final-comparison.webp",
        "evidence/variant-1.webp",
        "evidence/variant-1-comparison.webp",
        "evidence/variant-2.webp",
        "evidence/variant-2-comparison.webp",
        "evidence/variant-3.webp",
        "evidence/variant-3-comparison.webp",
    },
    "seoul-palace-hero": {
        "../../assets/seoul-palace-hero.png",
        "../../assets/seoul-palace-hero.gif",
        "evidence/final.png",
        "evidence/final-comparison.png",
        "evidence/variant-1.png",
        "evidence/variant-1-comparison.png",
        "evidence/variant-2.png",
        "evidence/variant-2-comparison.png",
        "evidence/variant-3.png",
        "evidence/variant-3-comparison.png",
        "evidence/optimization-reference.png",
        "evidence/optimization-axis.png",
        "evidence/optimization-side.png",
        "evidence/optimization-mountain.png",
        "evidence/optimization-material.png",
        "evidence/optimization-hierarchy.png",
        "evidence/optimization-pass-comparison.png",
    },
}


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def repository_file(base_dir: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} must be a non-empty repository-relative path")
    if Path(relative).is_absolute() or PureWindowsPath(relative).is_absolute():
        raise ValueError(f"{label} exposes absolute path {relative}")
    path = (base_dir / relative).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as error:
        raise ValueError(f"{label} escapes repository root: {relative}") from error
    if not path.is_file():
        raise ValueError(f"{label} is missing file {relative}")
    return path


def fingerprint_files(base_dir: Path, relative_paths: tuple[str, ...]) -> str:
    fingerprint = sha256()
    for relative in relative_paths:
        fingerprint.update(relative.encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update((base_dir / relative).resolve().read_bytes())
        fingerprint.update(b"\0")
    return fingerprint.hexdigest()


def deterministic_variant_seed(root_seed: int, index: int, attempt: int) -> str:
    digest_bytes = sha256(
        f"{root_seed}:{index}:{attempt}".encode("utf-8")
    ).digest()
    return str(int.from_bytes(digest_bytes[:8], "big"))


def runtime_seed_from_variant_seed(variant_seed: str) -> int:
    if (
        not isinstance(variant_seed, str)
        or not variant_seed
        or not variant_seed.isascii()
        or not variant_seed.isdecimal()
        or (len(variant_seed) > 1 and variant_seed.startswith("0"))
    ):
        raise ValueError("variantSeed must be a canonical unsigned decimal string")
    return int(variant_seed) & 0xFFFFFFFF


def load(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"{path} contains non-standard JSON constant {value}")

    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def verify_spec(path: Path) -> dict[str, Any]:
    spec = load(path)
    errors, warnings = validate_spec(spec, path)
    strict_errors = [item for item in warnings if item.startswith("quality:")]
    if errors or strict_errors:
        raise ValueError(
            f"{path.relative_to(ROOT)} failed strict validation: "
            + "; ".join([*errors, *strict_errors])
        )
    return spec


def latest_review(spec: dict[str, Any], pass_id: str) -> dict[str, Any]:
    reviews = [
        review
        for review in spec.get("reviewHistory", [])
        if isinstance(review, dict) and review.get("passId") == pass_id
    ]
    if not reviews:
        raise ValueError(f"missing authoritative {pass_id} review")
    return reviews[-1]


def action_ready_contract(spec: dict[str, Any]) -> dict[str, Any]:
    components: dict[str, str | None] = {}
    sockets: dict[str, dict[str, Any]] = {}
    colliders: dict[str, dict[str, Any]] = {}
    component_tree = spec.get("componentTree")
    if not isinstance(component_tree, list) or not component_tree:
        raise ValueError("action-ready component tree is missing")
    for component in component_tree:
        if not isinstance(component, dict):
            raise ValueError("action-ready component must be an object")
        component_id = component.get("id")
        parent_id = component.get("parent")
        if (
            not isinstance(component_id, str)
            or not component_id
            or component_id in components
            or (
                parent_id is not None
                and (not isinstance(parent_id, str) or not parent_id)
            )
        ):
            raise ValueError("action-ready component IDs or parents are invalid")
        components[component_id] = parent_id
        profile = component.get("actionProfile")
        if not isinstance(profile, dict):
            raise ValueError(f"{component_id} actionProfile is missing")
        component_sockets = profile.get("sockets")
        if not isinstance(component_sockets, list):
            raise ValueError(f"{component_id} socket contract is missing")
        for socket in component_sockets:
            if (
                not isinstance(socket, dict)
                or set(socket)
                != {
                    "id",
                    "parentNodeId",
                    "localPosition",
                    "localRotation",
                }
                or not isinstance(socket.get("id"), str)
                or not socket["id"]
                or socket["id"] in sockets
                or not isinstance(socket.get("parentNodeId"), str)
                or not socket["parentNodeId"]
                or any(
                    not isinstance(socket.get(field), list)
                    or len(socket[field]) != 3
                    or any(
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        for value in socket[field]
                    )
                    for field in ("localPosition", "localRotation")
                )
            ):
                raise ValueError(f"{component_id} socket contract is invalid")
            sockets[socket["id"]] = socket
        collider = profile.get("collider")
        if not isinstance(collider, dict) or collider.get("isTrigger") is not False:
            raise ValueError(f"{component_id} collider contract is missing")
        if collider.get("type") == "none":
            if set(collider) != {"type", "isTrigger"}:
                raise ValueError(f"{component_id} disabled collider is stale")
            continue
        parts = collider.get("parts")
        if (
            collider.get("type") != "compound"
            or set(collider) != {"type", "isTrigger", "parts"}
            or not isinstance(parts, list)
            or not parts
        ):
            raise ValueError(f"{component_id} collider contract is stale")
        for part in parts:
            if (
                not isinstance(part, dict)
                or set(part)
                != {
                    "id",
                    "parentId",
                    "parentNodeId",
                    "offset",
                    "scale",
                    "dynamic",
                }
                or not isinstance(part.get("id"), str)
                or not part["id"]
                or part["id"] in colliders
                or any(
                    not isinstance(part.get(field), str) or not part[field]
                    for field in ("parentId", "parentNodeId")
                )
                or not isinstance(part.get("dynamic"), bool)
                or any(
                    not isinstance(part.get(field), list)
                    or len(part[field]) != 3
                    or any(
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        or (field == "scale" and value <= 0)
                        for value in part[field]
                    )
                    for field in ("offset", "scale")
                )
            ):
                raise ValueError(f"{component_id} collider parts are invalid")
            colliders[part["id"]] = {**part, "componentId": component_id}
    roots = [
        component_id
        for component_id, parent_id in components.items()
        if parent_id is None
    ]
    if roots != ["root"] or any(
        parent_id is not None and parent_id not in components
        for parent_id in components.values()
    ):
        raise ValueError("action-ready component hierarchy is disconnected")
    for component_id in components:
        path: set[str] = set()
        current = component_id
        while current != "root":
            if current in path:
                raise ValueError("action-ready component hierarchy contains a cycle")
            path.add(current)
            parent_id = components[current]
            if parent_id is None:
                raise ValueError(
                    "action-ready component hierarchy is disconnected"
                )
            current = parent_id
    return {
        "components": components,
        "sockets": sockets,
        "colliders": colliders,
    }


def collider_contract(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return action_ready_contract(spec)["colliders"]


def verify_production_review_policy(
    spec: dict[str, Any], spec_path: Path
) -> None:
    if spec.get("reviewPolicy") != PRODUCTION_REVIEW_POLICY:
        raise ValueError(
            f"{spec_path.name} must use exact production reviewPolicy v2"
        )


def verify_complete_latest_review_pipeline(
    spec: dict[str, Any], spec_path: Path
) -> dict[str, dict[str, Any]]:
    pipeline = spec.get("sculptPipeline", {})
    latest_reviews = {
        review.get("passId"): review
        for review in spec.get("reviewHistory", [])
        if isinstance(review, dict)
    }
    if (
        pipeline.get("currentPass") != "complete"
        or pipeline.get("passOrder") != list(PRODUCTION_PASS_ORDER)
        or pipeline.get("completedPasses") != list(PRODUCTION_PASS_ORDER)
        or set(latest_reviews) != set(PRODUCTION_PASS_ORDER)
        or any(
            latest_reviews[pass_id].get("action") != "continue"
            or not isinstance(
                latest_reviews[pass_id].get("visualEvidence"), dict
            )
            for pass_id in PRODUCTION_PASS_ORDER
        )
    ):
        raise ValueError(
            f"{spec_path.name} must complete every latest evidence-backed pass"
        )
    return latest_reviews


def json_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [
            item
            for child in value
            for item in json_strings(child)
        ]
    if isinstance(value, dict):
        return [
            item
            for key, child in value.items()
            for item in (*json_strings(key), *json_strings(child))
        ]
    return []


def verify_repository_relative_paths(payload: Any, label: str) -> None:
    for value in json_strings(payload):
        if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
            raise ValueError(f"{label} exposes absolute path {value}")


def verify_no_absolute_evidence_paths() -> None:
    files = {
        ROOT / "examples" / "seoul-challenge" / "assessment.json",
        ROOT / "examples" / "seoul-challenge" / "object-sculpt-spec.json",
        ROOT / "examples" / "seoul-palace-hero" / "artifact-manifest.json",
        ROOT / "examples" / "seoul-palace-hero" / "seoul-output"
        / "seoul-palace-profile.json",
        ROOT / "examples" / "seoul-palace-hero" / "seoul-output"
        / "seoul-variant-config.json",
        ROOT / "examples" / "showcase" / "showcase-review.json",
    }
    files.update(
        (
            ROOT / "examples" / "seoul-palace-hero" / "evidence"
        ).rglob("*.json")
    )
    files.update(
        (
            ROOT / "examples" / "showcase" / "variants" / "seoul-production"
        ).rglob("*.json")
    )
    for path in sorted(files):
        verify_repository_relative_paths(
            json.loads(path.read_text(encoding="utf-8")),
            str(path.relative_to(ROOT)),
        )


def verify_performance_probe(
    probe: dict[str, Any],
    runtime_fingerprint: str,
    label: str,
    *,
    variant: bool,
) -> None:
    conditions = probe.get("conditions", {})
    aggregate = probe.get("aggregate", {})
    runs = probe.get("runs", [])
    aggregate_metrics = (
        "meanFps",
        "meanFrameMs",
        "p50FrameMs",
        "p95FrameMs",
        "p99FrameMs",
    )
    run_metrics = (
        "meanFps",
        "p50FrameMs",
        "p95FrameMs",
        "p99FrameMs",
        "heapBeforeMiB",
        "heapAfterMiB",
    )
    gc_diagnostics = probe.get("gcDiagnostics", [])
    if (
        not isinstance(conditions, dict)
        or not isinstance(aggregate, dict)
        or not isinstance(runs, list)
        or any(
            isinstance(aggregate.get(field), bool)
            or not isinstance(aggregate.get(field), (int, float))
            or not math.isfinite(aggregate[field])
            for field in aggregate_metrics
        )
        or any(
            not isinstance(run, dict)
            or any(
                isinstance(run.get(field), bool)
                or not isinstance(run.get(field), (int, float))
                or not math.isfinite(run[field])
                for field in run_metrics
            )
            for run in runs
        )
        or isinstance(aggregate.get("droppedFrameCount"), bool)
        or not isinstance(aggregate.get("droppedFrameCount"), int)
        or not isinstance(gc_diagnostics, list)
        or len(gc_diagnostics) != 3
        or any(
            not isinstance(item, dict)
            or isinstance(item.get("primaryEvents"), bool)
            or not isinstance(item.get("primaryEvents"), int)
            or isinstance(item.get("primaryDurationMs"), bool)
            or not isinstance(item.get("primaryDurationMs"), (int, float))
            or not math.isfinite(item["primaryDurationMs"])
            for item in gc_diagnostics
        )
        or any(
            isinstance(run.get(field), bool)
            or not isinstance(run.get(field), int)
            for run in runs
            for field in ("droppedFrameCount", "longTaskCount")
        )
    ):
        raise ValueError(f"{label} performance probe has non-finite metrics")
    warmup_field = (
        "warmupFramesExcludedPerRun" if variant else "warmupFramesExcluded"
    )
    if (
        probe.get("runtimeFingerprint") != runtime_fingerprint
        or conditions.get("viewport")
        != {"width": 1200, "height": 675, "deviceScaleFactor": 1}
        or conditions.get(warmup_field) != 180
        or conditions.get("measuredFramesPerRun") != 600
        or (variant and conditions.get("runsPerVariant") != 3)
        or aggregate.get("frameCount") != 1800
        or len(runs) != 3
        or aggregate.get("meanFps", 0) < 58.5
        or aggregate.get("p50FrameMs", float("inf")) > 16.9
        or aggregate.get("p95FrameMs", float("inf")) > 22
        or aggregate.get("droppedFrameCount") != 0
        or any(
            run.get("frameCount") != 600
            or run.get("meanFps", 0) < 58.5
            or run.get("p50FrameMs", float("inf")) > 16.9
            or run.get("p95FrameMs", float("inf")) > 22
            or run.get("droppedFrameCount") != 0
            or run.get("longTaskCount") != 0
            for run in runs
        )
    ):
        raise ValueError(f"{label} performance probe is stale or below gate")
    if variant:
        if (
            conditions.get("physicalRefreshHz") != 60
            or "headed physical-60Hz" not in probe.get("authority", "")
        ):
            raise ValueError(f"{label} is not a headed physical-60Hz probe")
    elif conditions.get("mode") != "headed physical 60 Hz presentation":
        raise ValueError(f"{label} is not a headed physical 60 Hz probe")


def verify_exact_artifact_outputs(
    hero_name: str, output_hashes: dict[str, Any]
) -> None:
    if set(output_hashes) != EXPECTED_ARTIFACT_OUTPUTS[hero_name]:
        raise ValueError(
            f"{hero_name} manifest must contain the exact canonical outputs"
        )


def verify_exact_artifact_sources(
    hero_name: str, source_hashes: dict[str, Any]
) -> None:
    if tuple(source_hashes) != EXPECTED_ARTIFACT_SOURCES[hero_name]:
        raise ValueError(
            f"{hero_name} artifact manifest must cover the exact "
            "canonical source inputs"
        )


def verify_brick_capture_fingerprint(
    hero_dir: Path, manifest: dict[str, Any]
) -> None:
    expected_fingerprint = fingerprint_files(
        hero_dir, BRICK_FINGERPRINT_SOURCE_FILES
    )
    if (
        manifest.get("capture", {}).get("sourceFingerprint")
        != expected_fingerprint
    ):
        raise ValueError("Brick artifact manifest source fingerprint is stale")


def verify_artifact_manifest(hero_dir: Path) -> None:
    manifest = load(hero_dir / "artifact-manifest.json")
    for section in ("sourceSha256", "outputSha256"):
        values = manifest.get(section)
        if not isinstance(values, dict) or not values:
            raise ValueError(f"{hero_dir.name} manifest has no {section}")
        if section == "outputSha256":
            verify_exact_artifact_outputs(hero_dir.name, values)
        for relative, expected in values.items():
            path = repository_file(
                hero_dir,
                relative,
                f"{hero_dir.name} manifest {section}",
            )
            actual = digest(path)
            if actual != expected:
                raise ValueError(
                    f"{hero_dir.name} {section} mismatch for {relative}: "
                    f"expected {expected}, actual {actual}"
                )
    source_hashes = manifest["sourceSha256"]
    verify_exact_artifact_sources(hero_dir.name, source_hashes)
    if hero_dir.name == "brick-offroad-hero":
        verify_brick_capture_fingerprint(hero_dir, manifest)
    if hero_dir.name != "seoul-palace-hero":
        return
    expected_fingerprint = fingerprint_files(
        hero_dir, SEOUL_CANONICAL_SOURCE_FILES
    )
    if manifest.get("sourceFingerprint") != expected_fingerprint:
        raise ValueError("Seoul artifact manifest source fingerprint is stale")
    if (
        tuple(manifest.get("runtimeFiles", ()))
        != SEOUL_RUNTIME_SOURCE_FILES
        or tuple(manifest.get("runtimeSha256", {}))
        != SEOUL_RUNTIME_SOURCE_FILES
    ):
        raise ValueError("Seoul runtime fingerprint input set is incomplete")
    for relative, expected in manifest["runtimeSha256"].items():
        if (
            digest(repository_file(hero_dir, relative, "Seoul runtime manifest"))
            != expected
        ):
            raise ValueError(f"Seoul runtime input hash is stale: {relative}")
    runtime_fingerprint = fingerprint_files(
        hero_dir, SEOUL_RUNTIME_SOURCE_FILES
    )
    if (
        manifest.get("runtimeFingerprint") != runtime_fingerprint
        or manifest.get("runtimeStats", {}).get("runtimeFingerprint")
        != runtime_fingerprint
        or any(
            item.get("runtimeFingerprint") != runtime_fingerprint
            for item in manifest.get("variantRuntimeStats", [])
        )
    ):
        raise ValueError("Seoul runtime fingerprint is stale")
    base_spec = load(
        ROOT / "examples" / "seoul-challenge" / "object-sculpt-spec.json"
    )
    action_contract = action_ready_contract(base_spec)
    component_contract = action_contract["components"]
    socket_contract = action_contract["sockets"]
    collider_contract = action_contract["colliders"]
    runtime_snapshot = manifest.get("runtimeSnapshot", {})
    node_ids = runtime_snapshot.get("nodeIds", [])
    mesh_ids = runtime_snapshot.get("meshIds", [])
    socket_ids = runtime_snapshot.get("socketIds", [])
    collider_ids = runtime_snapshot.get("colliderIds", [])
    semantic_aliases = runtime_snapshot.get("semanticNodeAliases", {})
    socket_snapshot = manifest.get("socketSnapshot", {})
    collider_snapshot = manifest.get("colliderSnapshot", {})
    gate_collider_ids = {
        f"{gate}-{side}-{part}-collider"
        for gate in ("outer-gate", "inner-gate")
        for side in ("west", "east")
        for part in ("leaf", "pier")
    }
    foreground_collider = collider_snapshot.get("foreground-collider", {})
    if (
        len(component_contract) != 33
        or len(socket_contract) != 14
        or len(collider_contract) != 27
        or not isinstance(node_ids, list)
        or not isinstance(mesh_ids, list)
        or not isinstance(socket_ids, list)
        or not isinstance(collider_ids, list)
        or any(not isinstance(item, str) for item in node_ids)
        or any(not isinstance(item, str) for item in mesh_ids)
        or any(not isinstance(item, str) for item in socket_ids)
        or any(not isinstance(item, str) for item in collider_ids)
        or not isinstance(semantic_aliases, dict)
        or set(semantic_aliases) != set(component_contract)
        or not set(component_contract).issubset(node_ids)
        or any(
            not isinstance(target_id, str)
            or target_id not in set(node_ids) | set(mesh_ids)
            for target_id in semantic_aliases.values()
        )
        or not isinstance(socket_snapshot, dict)
        or set(socket_snapshot) != set(socket_ids)
        or set(socket_snapshot) != set(socket_contract)
        or any(
            not isinstance(socket_snapshot[socket_id], dict)
            or set(socket_snapshot[socket_id])
            != {
                "parentNodeId",
                "declaredParentNodeId",
                "position",
                "rotation",
            }
            or socket_snapshot[socket_id].get("parentNodeId")
            != expected.get("parentNodeId")
            or socket_snapshot[socket_id].get("declaredParentNodeId")
            != expected.get("parentNodeId")
            or any(
                not isinstance(socket_snapshot[socket_id].get(actual_field), list)
                or len(socket_snapshot[socket_id][actual_field]) != 3
                or any(
                    not math.isclose(left, right, abs_tol=1e-9)
                    for left, right in zip(
                        socket_snapshot[socket_id][actual_field],
                        expected[expected_field],
                        strict=True,
                    )
                )
                for actual_field, expected_field in (
                    ("position", "localPosition"),
                    ("rotation", "localRotation"),
                )
            )
            for socket_id, expected in socket_contract.items()
        )
        or not isinstance(collider_snapshot, dict)
        or set(collider_snapshot) != set(collider_ids)
        or set(collider_snapshot) != set(collider_contract)
        or not gate_collider_ids.issubset(collider_snapshot)
        or {"outer-gate-collider", "inner-gate-collider"} & set(collider_snapshot)
        or foreground_collider.get("parentId") != "foreground-ground"
        or foreground_collider.get("center") != [0, -0.18, -28]
        or foreground_collider.get("size") != [90, 0.35, 34]
        or any(
            (
                collider_snapshot[collider_id].get("parentId")
                != collider_id.removesuffix("-collider")
                or collider_snapshot[collider_id].get("parentNodeId")
                != collider_id.removesuffix("-collider") + "-pivot"
            )
            for collider_id in gate_collider_ids
            if "-leaf-" in collider_id
        )
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("size"), list)
            or len(item["size"]) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
                for value in item["size"]
            )
            for item in collider_snapshot.values()
        )
        or any(
            not isinstance(collider_snapshot[collider_id], dict)
            or set(collider_snapshot[collider_id])
            != {"parentId", "parentNodeId", "center", "size"}
            or collider_snapshot[collider_id].get("parentId")
            != expected.get("parentId")
            or collider_snapshot[collider_id].get("parentNodeId")
            != expected.get("parentNodeId")
            or any(
                not isinstance(collider_snapshot[collider_id].get(actual_field), list)
                or len(collider_snapshot[collider_id][actual_field]) != 3
                or any(
                    not math.isclose(left, right, abs_tol=1e-9)
                    for left, right in zip(
                        collider_snapshot[collider_id][actual_field],
                        expected[expected_field],
                        strict=True,
                    )
                )
                for actual_field, expected_field in (
                    ("center", "offset"),
                    ("size", "scale"),
                )
            )
            for collider_id, expected in collider_contract.items()
        )
    ):
        raise ValueError(
            "Seoul component/socket/collider runtime contract is stale or invalid"
        )
    base_metrics = load(hero_dir / "evidence" / "optimization-metrics.json")
    verify_performance_probe(
        base_metrics.get("performanceProbe", {}),
        runtime_fingerprint,
        "Seoul base",
        variant=False,
    )
    measured_snapshot = base_metrics.get("runtime", {})
    measured_hero = measured_snapshot.get("hero", {})
    measured_render = measured_snapshot.get("render", {})
    captured_stats = manifest.get("runtimeStats", {})
    comparable_stat_fields = (
        "seed",
        "stage",
        "variantId",
        "macroGroups",
        "nodes",
        "meshes",
        "sceneDrawables",
        "triangles",
        "instances",
        "treeInstances",
        "cityInstances",
        "sockets",
        "colliders",
        "importedMeshes",
        "generatedTextureCount",
    )
    probe = base_metrics["performanceProbe"]
    raw_hashes = (
        probe.get("rawArtifactSummarySha256", ""),
        probe.get("rawRuntimeSnapshotSha256", ""),
    )
    if (
        any(
            measured_hero.get(field) != captured_stats.get(field)
            for field in comparable_stat_fields
        )
        or measured_render.get("calls") != captured_stats.get("renderCalls")
        or measured_render.get("triangles")
        != captured_stats.get("renderedTriangles")
        or measured_render.get("runtimeFingerprint") != runtime_fingerprint
        or measured_snapshot.get("runtime") != manifest.get("runtimeSnapshot")
        or (
            "frustum-culling-and-linear-texture-minification"
            not in measured_snapshot.get("runtime", {})
            .get("optimization", {})
            .get("strategies", [])
        )
        or any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in raw_hashes
        )
    ):
        raise ValueError("Seoul base runtime snapshot is stale or incomplete")
    required_outputs = {
        "../../assets/seoul-palace-hero.png": SEOUL_HERO_SHA256,
        "../../assets/seoul-palace-hero.gif": SEOUL_GIF_SHA256,
        "evidence/final.png": SEOUL_HERO_SHA256,
    }
    for relative, expected in required_outputs.items():
        if manifest["outputSha256"].get(relative) != expected:
            raise ValueError(f"Seoul canonical output changed: {relative}")
    if (
        manifest.get("capture", {}).get("repeatedCanonicalSha256")
        != SEOUL_HERO_SHA256
        or manifest.get("capture", {}).get("animation", {}).get("reducedMotion")
        != "no-preference"
        or manifest.get("capture", {}).get("animation", {}).get(
            "uniqueFrameCount", 0
        )
        < 2
        or digest(ROOT / "assets" / "seoul-challenge-sculpt-dna-result.png")
        != SEOUL_INTERMEDIATE_SHA256
    ):
        raise ValueError("Seoul repeated capture or intermediate hash changed")
    profile = load(
        hero_dir / "seoul-output" / "seoul-palace-profile.json"
    )
    if (
        profile.get("actionReadiness", {}).get("semanticComponents")
        != len(component_contract)
        or profile.get("actionReadiness", {}).get("sockets")
        != len(socket_snapshot)
        or profile.get("actionReadiness", {}).get("colliders")
        != len(collider_snapshot)
        or any(
            expected.get("dynamic") != ("-leaf-" in collider_id)
            for collider_id, expected in collider_contract.items()
        )
    ):
        raise ValueError(
            "Seoul action-ready profile does not match captured runtime"
        )
    optimization = latest_review(base_spec, "optimization-pass")
    visual = optimization.get("visualEvidence", {})
    if (
        optimization.get("action") != "continue"
        or visual.get("renderScreenshot")
        != "examples/seoul-palace-hero/evidence/final.png"
        or visual.get("renderSha256") != SEOUL_HERO_SHA256
        or visual.get("comparisonImage")
        != "examples/seoul-palace-hero/evidence/final-comparison.png"
    ):
        raise ValueError(
            "Authoritative optimization review must bind the canonical release"
        )
    supplemental = {
        item.get("path"): item.get("sha256")
        for item in visual.get("supplementalEvidence", [])
        if isinstance(item, dict)
    }
    if (
        supplemental.get("assets/seoul-palace-hero.gif")
        != SEOUL_GIF_SHA256
        or supplemental.get("assets/seoul-challenge-sculpt-dna-result.png")
        != SEOUL_INTERMEDIATE_SHA256
    ):
        raise ValueError(
            "Authoritative optimization review must bind GIF and intermediate"
        )


def verify_showcase_review() -> None:
    review = load(ROOT / "examples" / "showcase" / "showcase-review.json")
    for family_id, label in (
        ("brick-offroad", "Brick"),
        ("seoul-challenge", "Seoul"),
    ):
        family = next(
            (item for item in review.get("families", []) if item.get("id") == family_id),
            None,
        )
        if not isinstance(family, dict):
            raise ValueError(f"showcase review is missing {label}")
        if family.get("reviewStatus") != "accepted":
            raise ValueError(f"{label} showcase review is not accepted")
        for path_field, hash_field in (
            ("reference", "referenceSha256"),
            ("render", "renderSha256"),
            ("comparison", "comparisonSha256"),
        ):
            path = repository_file(
                ROOT,
                family.get(path_field, ""),
                f"{label} showcase {path_field}",
            )
            if digest(path) != family.get(hash_field):
                raise ValueError(
                    f"{label} showcase {path_field} binding is missing or stale"
                )
        if not family.get("reviewId") or not family.get("reviewedAt"):
            raise ValueError(f"{label} showcase review identity is missing")
        if not isinstance(family.get("scores"), dict):
            raise ValueError(f"{label} showcase review has no fresh scores")
        if family_id == "seoul-challenge" and (
            set(family["scores"]) != SEOUL_REQUIRED_LAYER_SCORES
            or any(
                not score_meets_threshold(score, SEOUL_VISUAL_THRESHOLD)
                for score in family["scores"].values()
            )
        ):
            raise ValueError("Seoul showcase layer scores must all meet 0.86")


def score_meets_threshold(value: Any, threshold: float) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value >= threshold
    )


def verify_seoul_visual_acceptance(
    variant: dict[str, Any],
    acceptance: dict[str, Any],
    label: str,
) -> None:
    declared = variant.get("selfCorrectLoop", {}).get("visualAcceptance", {})
    feature_policy = declared.get("featureReviewPolicy", {})
    critical_targets = {
        target.get("id"): target
        for target in variant.get("featureReviewTargets", [])
        if isinstance(target, dict)
        and target.get("tier") == "critical"
        and target.get("mustPass") is True
    }
    if (
        declared.get("threshold") != SEOUL_VISUAL_THRESHOLD
        or set(declared.get("requiredLayerScores", []))
        != SEOUL_REQUIRED_LAYER_SCORES
        or feature_policy.get("criticalDefaultThreshold")
        != SEOUL_VISUAL_THRESHOLD
        or set(critical_targets) != SEOUL_CRITICAL_FEATURES
        or any(
            target.get("minimumScore") != SEOUL_VISUAL_THRESHOLD
            for target in critical_targets.values()
        )
    ):
        raise ValueError(f"{label} must declare the exact 0.86 visual gate")

    layer_scores = acceptance.get("layerScores")
    if (
        acceptance.get("visualAcceptanceThreshold") != SEOUL_VISUAL_THRESHOLD
        or not score_meets_threshold(
            acceptance.get("aiVisionScore"),
            SEOUL_VISUAL_THRESHOLD,
        )
        or not isinstance(layer_scores, dict)
        or not SEOUL_REQUIRED_LAYER_SCORES.issubset(layer_scores)
        or any(
            not score_meets_threshold(
                layer_scores.get(layer),
                SEOUL_VISUAL_THRESHOLD,
            )
            for layer in SEOUL_REQUIRED_LAYER_SCORES
        )
    ):
        raise ValueError(f"{label} visual acceptance is stale or below 0.86")

    feature_reviews = acceptance.get("featureReviews")
    if (
        not isinstance(feature_reviews, list)
        or len(feature_reviews) != len(SEOUL_CRITICAL_FEATURES)
        or any(not isinstance(feature, dict) for feature in feature_reviews)
        or {feature.get("id") for feature in feature_reviews}
        != SEOUL_CRITICAL_FEATURES
    ):
        raise ValueError(f"{label} must review the exact critical feature set")
    if any(
        feature.get("visible") is not True
        or not score_meets_threshold(
            feature.get("score"),
            SEOUL_VISUAL_THRESHOLD,
        )
        for feature in feature_reviews
    ):
        raise ValueError(f"{label} has a failed 0.86 critical feature review")


def verify_brick_variants() -> None:
    base_path = ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json"
    base = verify_spec(base_path)
    verify_production_review_policy(base, base_path)
    variant_gate(base, False, base_path)
    variant_dir = ROOT / "examples" / "showcase" / "variants" / "brick"
    manifest = load(variant_dir / "sculpt-dna-manifest.json")
    for item in manifest.get("variants", []):
        spec_path = repository_file(
            variant_dir,
            item.get("path", ""),
            "Brick production variant",
        )
        variant = verify_spec(spec_path)
        verify_production_review_policy(variant, spec_path)
        verify_complete_latest_review_pipeline(variant, spec_path)
        acceptance = variant.get("variantProvenance", {}).get("visualAcceptance", {})
        for path_field, hash_field in (
            ("renderScreenshot", "renderSha256"),
            ("comparisonImage", "comparisonSha256"),
        ):
            evidence_path = repository_file(
                ROOT,
                acceptance.get(path_field, ""),
                f"{spec_path.name} {path_field}",
            )
            if digest(evidence_path) != acceptance.get(hash_field):
                raise ValueError(
                    f"{spec_path.name} production {path_field} binding is missing or stale"
                )


def verify_seoul_variants() -> None:
    base_path = ROOT / "examples" / "seoul-challenge" / "object-sculpt-spec.json"
    base = verify_spec(base_path)
    verify_production_review_policy(base, base_path)
    variant_gate(base, False, base_path)
    verify_seoul_visual_acceptance(
        base,
        latest_review(base, "optimization-pass"),
        base_path.name,
    )
    base_action_contract = action_ready_contract(base)
    variant_dir = ROOT / "examples" / "showcase" / "variants" / "seoul-production"
    manifest = load(variant_dir / "sculpt-dna-manifest.json")
    variants = manifest.get("variants")
    expected_passes = PRODUCTION_PASS_ORDER
    expected_ids = set(SEOUL_PRODUCTION_VARIANTS)
    if (
        manifest.get("count") != 3
        or manifest.get("poolSize") != 24
        or manifest.get("rootSeed") != SEOUL_ROOT_SEED
        or manifest.get("selectedCandidateIndexes")
        != [
            item["candidateIndex"]
            for item in SEOUL_PRODUCTION_VARIANTS.values()
        ]
        or manifest.get("sourceSpecSha256") != digest(base_path)
        or manifest.get("passGateStatus") != "evidence-backed-production"
        or manifest.get("visualReviewSet", {}).get("variantPipelinesComplete")
        is not True
        or not isinstance(variants, list)
        or len(variants) != 3
        or any(not isinstance(item, dict) for item in variants)
    ):
        raise ValueError("Seoul production curation must select 3 variants from 24")
    expected_paths = {
        f"seoul-palace-hero-v00{index}.json" for index in range(1, 4)
    }
    physical_paths = {
        path.name for path in variant_dir.glob("seoul-palace-hero-v*.json")
    }
    if (
        {item.get("path") for item in variants} != expected_paths
        or physical_paths != expected_paths
        or {item.get("variantId") for item in variants} != expected_ids
    ):
        raise ValueError("Seoul production manifest is missing a curated variant file")
    runtime_payload = load(
        ROOT
        / "examples"
        / "seoul-palace-hero"
        / "seoul-output"
        / "seoul-variant-config.json"
    )
    runtime_config = runtime_payload.get("variants")
    if (
        runtime_payload.get("base", {}).get("seed") != SEOUL_ROOT_SEED
        or not isinstance(runtime_config, list)
        or len(runtime_config) != 3
        or any(not isinstance(item, dict) for item in runtime_config)
        or {item.get("id") for item in runtime_config} != expected_ids
    ):
        raise ValueError("Seoul runtime config must define the exact curated variant IDs")
    hero_manifest = load(
        ROOT / "examples" / "seoul-palace-hero" / "artifact-manifest.json"
    )
    variant_metrics_path = (
        ROOT
        / "examples"
        / "seoul-palace-hero"
        / "evidence"
        / "variant-runtime-metrics.json"
    )
    variant_metrics = load(variant_metrics_path)
    metrics_by_id = {
        item.get("variantId"): item
        for item in variant_metrics.get("variants", [])
        if isinstance(item, dict)
    }
    runtime_stats_by_id = {
        item.get("variantId"): item
        for item in hero_manifest.get("variantRuntimeStats", [])
        if isinstance(item, dict)
    }
    review_set = manifest.get("visualReviewSet", {})
    if (
        variant_metrics.get("schemaVersion") != "2.0"
        or variant_metrics.get("sourceBinding", {}).get("mode")
        != "runtime-fingerprint-v1"
        or variant_metrics.get("runtimeFingerprint")
        != hero_manifest.get("runtimeFingerprint")
        or set(metrics_by_id) != expected_ids
        or set(runtime_stats_by_id) != expected_ids
        or any(
            stats.get("sourceFingerprint")
            != hero_manifest.get("sourceFingerprint")
            for stats in runtime_stats_by_id.values()
        )
    ):
        raise ValueError("Seoul variant performance evidence is stale or incomplete")
    for item in variants:
        spec_path = repository_file(
            variant_dir,
            item.get("path", ""),
            "Seoul production variant",
        )
        variant = verify_spec(spec_path)
        verify_production_review_policy(variant, spec_path)
        latest_reviews = verify_complete_latest_review_pipeline(
            variant, spec_path
        )
        if action_ready_contract(variant) != base_action_contract:
            raise ValueError(
                f"{spec_path.name} action-ready contract diverges from canonical"
            )
        provenance = variant.get("variantProvenance", {})
        candidate_index = item.get("candidateIndex")
        attempt = item.get("attempt")
        pinned = SEOUL_PRODUCTION_VARIANTS[item["variantId"]]
        if (
            not isinstance(candidate_index, int)
            or isinstance(candidate_index, bool)
            or candidate_index != pinned["candidateIndex"]
            or not isinstance(attempt, int)
            or isinstance(attempt, bool)
            or attempt != 1
        ):
            raise ValueError(f"{spec_path.name} has invalid seed provenance")
        expected_variant_seed = deterministic_variant_seed(
            manifest["rootSeed"],
            candidate_index,
            attempt - 1,
        )
        if (
            expected_variant_seed != pinned["sourceSeed"]
            or item.get("variantSeed") != expected_variant_seed
            or provenance.get("variantSeed") != expected_variant_seed
            or provenance.get("rootSeed") != manifest["rootSeed"]
            or provenance.get("candidateIndex") != candidate_index
            or provenance.get("attempt") != attempt
        ):
            raise ValueError(
                f"{spec_path.name} variant seed does not match deterministic provenance"
            )
        pipeline = variant.get("sculptPipeline", {})
        if (
            provenance.get("variantId") != item["variantId"]
        ):
            raise ValueError(f"{spec_path.name} variant ID does not match its manifest")
        runtime = next(
            candidate
            for candidate in runtime_config
            if candidate.get("id") == item["variantId"]
        )
        expected_runtime_seed = runtime_seed_from_variant_seed(
            expected_variant_seed
        )
        if (
            item.get("passGateStatus") != "evidence-backed-production"
            or item.get("completedPasses") != list(expected_passes)
            or pipeline.get("currentPass") != "complete"
            or pipeline.get("passOrder") != list(expected_passes)
            or pipeline.get("completedPasses") != list(expected_passes)
            or set(latest_reviews) != set(expected_passes)
            or any(
                latest_reviews[pass_id].get("action") != "continue"
                or not latest_reviews[pass_id].get("visualEvidence")
                for pass_id in expected_passes
            )
            or variant.get("variantProvenance", {}).get("passGateStatus")
            != "evidence-backed-production"
            or runtime.get("provenance", {}).get("passGateStatus")
            != "evidence-backed-production"
            or runtime.get("provenance", {}).get("sourceVariantSeed")
            != expected_variant_seed
            or runtime.get("provenance", {}).get("candidateIndex")
            != pinned["candidateIndex"]
            or runtime.get("seed") != expected_runtime_seed
            or expected_runtime_seed != pinned["runtimeSeed"]
            or runtime.get("provenance", {}).get("runtimeSeedDerivation")
            != SEOUL_RUNTIME_SEED_DERIVATION
        ):
            raise ValueError(
                f"{spec_path.name} must complete every evidence-backed production pass"
            )
        performance = metrics_by_id[item["variantId"]]
        verify_performance_probe(
            {
                **performance,
                "conditions": variant_metrics.get("conditions"),
                "authority": variant_metrics.get("authority"),
                "runtimeFingerprint": variant_metrics.get(
                    "runtimeFingerprint"
                ),
            },
            hero_manifest["runtimeFingerprint"],
            item["variantId"],
            variant=True,
        )
        measured_runtime = performance.get("runtime", {})
        captured_runtime = runtime_stats_by_id[item["variantId"]]
        optimization = latest_reviews["optimization-pass"]
        supplemental = {
            entry.get("path"): entry.get("sha256")
            for entry in optimization.get("visualEvidence", {}).get(
                "supplementalEvidence", []
            )
            if isinstance(entry, dict)
        }
        if (
            performance.get("allRunsPass") is not True
            or measured_runtime.get("fullFrameWebglCalls")
            != captured_runtime.get("renderCalls")
            or measured_runtime.get("renderedTriangles")
            != captured_runtime.get("renderedTriangles")
            or measured_runtime.get("instanceWeightedTriangles")
            != captured_runtime.get("triangles")
            or measured_runtime.get("sceneDrawables")
            != captured_runtime.get("sceneDrawables")
            or measured_runtime.get("instances")
            != captured_runtime.get("instances")
            or measured_runtime.get("colliders")
            != captured_runtime.get("colliders")
            or supplemental.get(
                "examples/seoul-palace-hero/evidence/variant-runtime-metrics.json"
            )
            != digest(variant_metrics_path)
        ):
            raise ValueError(
                f"{spec_path.name} lacks current passing performance evidence"
            )
        acceptance = variant.get("variantProvenance", {}).get(
            "visualAcceptance", {}
        )
        verify_seoul_visual_acceptance(variant, acceptance, spec_path.name)
        if (
            item.get("visualEvidence") != acceptance
            or acceptance.get("reviewId")
            not in review_set.get("variantReviewIds", [])
        ):
            raise ValueError(
                f"{spec_path.name} visual acceptance is stale or not authoritative"
            )
        for path_field, hash_field in (
            ("referenceScreenshot", "referenceSha256"),
            ("renderScreenshot", "renderSha256"),
            ("comparisonImage", "comparisonSha256"),
        ):
            evidence_path = repository_file(
                ROOT,
                acceptance.get(path_field, ""),
                f"{spec_path.name} {path_field}",
            )
            if digest(evidence_path) != acceptance.get(hash_field):
                raise ValueError(
                    f"{spec_path.name} production {path_field} binding is missing or stale"
                )


def main() -> int:
    verify_spec(ROOT / "examples" / "repolis-tree" / "object-sculpt-spec.json")
    verify_brick_variants()
    verify_seoul_variants()
    verify_no_absolute_evidence_paths()
    verify_showcase_review()
    verify_artifact_manifest(ROOT / "examples" / "repolis-hero")
    verify_artifact_manifest(ROOT / "examples" / "brick-offroad-hero")
    verify_artifact_manifest(ROOT / "examples" / "seoul-palace-hero")
    print("Release gate passed: specs, production evidence, reviews, and manifests verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
