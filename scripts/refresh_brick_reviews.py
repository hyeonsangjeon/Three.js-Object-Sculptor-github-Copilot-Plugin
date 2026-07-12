#!/usr/bin/env python3
"""Refresh Brick review identities and hashes after an explicit visual inspection."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

from visual_evidence_hashes import bind_visual_evidence_hashes


ROOT = Path(__file__).resolve().parents[1]
BASE_SPEC = ROOT / "examples" / "brick-offroad" / "object-sculpt-spec.json"
VARIANT_DIR = ROOT / "examples" / "showcase" / "variants" / "brick"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def refresh_visual(
    visual: dict[str, Any],
    spec_path: Path,
    review_id: str,
    reviewed_at: str,
) -> None:
    visual["reviewId"] = review_id
    visual["reviewedAt"] = reviewed_at
    bind_visual_evidence_hashes(visual, spec_path)


def refresh_spec(path: Path, reviewed_at: str) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    target_id = spec["targetId"]
    acceptance = spec.get("variantProvenance", {}).get("visualAcceptance")
    shared_review_id = (
        f"{target_id}-fresh-review-{reviewed_at}" if isinstance(acceptance, dict) else None
    )
    for item in spec.get("reviewHistory", []):
        item["timestamp"] = reviewed_at
        visual = item.get("visualEvidence")
        if isinstance(visual, dict):
            review_id = shared_review_id or f"{item['passId']}-review-{reviewed_at}"
            refresh_visual(visual, path, review_id, reviewed_at)
    for item in spec.get("visualEvidence", []):
        item["timestamp"] = reviewed_at
        review_id = shared_review_id or f"{item['passId']}-review-{reviewed_at}"
        refresh_visual(item, path, review_id, reviewed_at)
    if isinstance(acceptance, dict):
        refresh_visual(acceptance, path, shared_review_id, reviewed_at)
        for item in spec.get("reviewHistory", []):
            visual = item.get("visualEvidence")
            if isinstance(visual, dict):
                for field in (
                    "reviewId",
                    "reviewedAt",
                    "referenceSha256",
                    "referenceBinding",
                    "renderSha256",
                    "renderBinding",
                    "comparisonSha256",
                    "comparisonBinding",
                ):
                    visual[field] = acceptance[field]
        for visual in spec.get("visualEvidence", []):
            for field in (
                "reviewId",
                "reviewedAt",
                "referenceSha256",
                "referenceBinding",
                "renderSha256",
                "renderBinding",
                "comparisonSha256",
                "comparisonBinding",
            ):
                visual[field] = acceptance[field]
    write_json(path, spec)
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-at", required=True, help="ISO-8601 inspection timestamp")
    args = parser.parse_args()

    refresh_spec(BASE_SPEC, args.reviewed_at)
    variants = [
        refresh_spec(path, args.reviewed_at)
        for path in sorted(VARIANT_DIR.glob("brick-offroad-v*.json"))
    ]
    manifest_path = VARIANT_DIR / "sculpt-dna-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sourceSpecSha256"] = sha256(BASE_SPEC.read_bytes()).hexdigest()
    acceptance_by_id = {
        spec["targetId"]: spec["variantProvenance"]["visualAcceptance"]
        for spec in variants
    }
    for item in manifest["variants"]:
        item["visualEvidence"] = deepcopy(acceptance_by_id[item["variantId"]])
    manifest["visualReviewSet"] = {
        "reviewedAt": args.reviewed_at,
        "authority": "fresh AI vision review of exact current render/comparison hashes",
        "variantReviewIds": [
            acceptance_by_id[item["variantId"]]["reviewId"]
            for item in manifest["variants"]
        ],
    }
    write_json(manifest_path, manifest)
    print(f"Refreshed Brick review evidence at {args.reviewed_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
