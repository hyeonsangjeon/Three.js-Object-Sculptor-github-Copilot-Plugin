#!/usr/bin/env python3
"""Upgrade ObjectSculptSpec visual reviews to SHA-bound latest-review policy v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from visual_evidence_hashes import (
    LATEST_REVIEW_SELECTION,
    REVIEW_POLICY_VERSION,
    SHA_REQUIRED_BINDING,
    bind_visual_evidence_hashes,
)


def migrate_spec(spec: dict[str, Any], spec_path: Path) -> dict[str, Any]:
    spec["reviewPolicy"] = {
        "version": REVIEW_POLICY_VERSION,
        "authoritativeReview": LATEST_REVIEW_SELECTION,
        "evidenceBinding": SHA_REQUIRED_BINDING,
    }
    for collection_name in ("reviewHistory", "visualEvidence"):
        collection = spec.get(collection_name, [])
        if not isinstance(collection, list):
            raise ValueError(f"{collection_name} must be an array")
        for index, item in enumerate(collection):
            if not isinstance(item, dict):
                continue
            visual = item.get("visualEvidence") if collection_name == "reviewHistory" else item
            if not isinstance(visual, dict):
                continue
            pass_id = item.get("passId") or visual.get("passId") or "visual"
            timestamp = item.get("timestamp") or visual.get("reviewedAt")
            if not isinstance(timestamp, str) or not timestamp:
                raise ValueError(
                    f"{collection_name}[{index}] needs timestamp/reviewedAt before migration"
                )
            visual.setdefault("reviewedAt", timestamp)
            visual.setdefault("reviewId", f"{pass_id}-review-{timestamp}")
            bind_visual_evidence_hashes(visual, spec_path)
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--in-place", action="store_true")
    output.add_argument("--out", type=Path)
    args = parser.parse_args()

    spec_path = args.spec.expanduser().resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("spec must be a JSON object")
    migrate_spec(spec, spec_path)
    output_path = spec_path if args.in_place else args.out.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Migrated review policy: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
