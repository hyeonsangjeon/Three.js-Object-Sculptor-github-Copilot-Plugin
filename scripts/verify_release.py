#!/usr/bin/env python3
"""Verify flagship specs, production evidence, reviews, and artifact manifests."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from sculpt_dna import variant_gate
from validate_sculpt_spec import validate_spec


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
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


def verify_artifact_manifest(hero_dir: Path) -> None:
    manifest = load(hero_dir / "artifact-manifest.json")
    for section in ("sourceSha256", "outputSha256"):
        values = manifest.get(section)
        if not isinstance(values, dict) or not values:
            raise ValueError(f"{hero_dir.name} manifest has no {section}")
        for relative, expected in values.items():
            path = (hero_dir / relative).resolve()
            actual = digest(path)
            if actual != expected:
                raise ValueError(
                    f"{hero_dir.name} {section} mismatch for {relative}: "
                    f"expected {expected}, actual {actual}"
                )


def verify_showcase_review() -> None:
    review = load(ROOT / "examples" / "showcase" / "showcase-review.json")
    brick = next(
        (item for item in review.get("families", []) if item.get("id") == "brick-offroad"),
        None,
    )
    if not isinstance(brick, dict):
        raise ValueError("showcase review is missing Brick")
    if brick.get("reviewStatus") != "accepted":
        raise ValueError("Brick showcase review is not accepted")
    for path_field, hash_field in (
        ("reference", "referenceSha256"),
        ("render", "renderSha256"),
        ("comparison", "comparisonSha256"),
    ):
        path = ROOT / brick.get(path_field, "")
        if not path.is_file() or digest(path) != brick.get(hash_field):
            raise ValueError(f"Brick showcase {path_field} binding is missing or stale")
    if not brick.get("reviewId") or not brick.get("reviewedAt"):
        raise ValueError("Brick showcase review identity is missing")
    if not isinstance(brick.get("scores"), dict):
        raise ValueError("Brick showcase review has no fresh scores")


def verify_brick_variants() -> None:
    base_path = ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json"
    base = verify_spec(base_path)
    variant_gate(base, False, base_path)
    variant_dir = ROOT / "examples" / "showcase" / "variants" / "brick"
    manifest = load(variant_dir / "sculpt-dna-manifest.json")
    for item in manifest.get("variants", []):
        spec_path = variant_dir / item["path"]
        variant = verify_spec(spec_path)
        acceptance = variant.get("variantProvenance", {}).get("visualAcceptance", {})
        for path_field, hash_field in (
            ("renderScreenshot", "renderSha256"),
            ("comparisonImage", "comparisonSha256"),
        ):
            evidence_path = ROOT / acceptance.get(path_field, "")
            if not evidence_path.is_file() or digest(evidence_path) != acceptance.get(hash_field):
                raise ValueError(
                    f"{spec_path.name} production {path_field} binding is missing or stale"
                )


def main() -> int:
    verify_spec(ROOT / "examples" / "repolis-tree" / "object-sculpt-spec.json")
    verify_brick_variants()
    verify_showcase_review()
    verify_artifact_manifest(ROOT / "examples" / "repolis-hero")
    verify_artifact_manifest(ROOT / "examples" / "brick-offroad-hero")
    print("Release gate passed: specs, production evidence, reviews, and manifests verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
