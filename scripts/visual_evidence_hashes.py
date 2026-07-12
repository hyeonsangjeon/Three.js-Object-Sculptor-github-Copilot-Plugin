#!/usr/bin/env python3
"""Bind local visual-review evidence to immutable SHA-256 digests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_FIELDS = {
    "referenceScreenshot": "referenceSha256",
    "renderScreenshot": "renderSha256",
    "comparisonImage": "comparisonSha256",
}
REQUIRED_LOCAL_FIELDS = ("renderScreenshot", "comparisonImage")
REVIEW_POLICY_VERSION = 2
SHA_REQUIRED_BINDING = "local-sha256-required"
LATEST_REVIEW_SELECTION = "latest-per-pass"
LEGACY_REVIEW_POLICY = {
    "version": 1,
    "authoritativeReview": LATEST_REVIEW_SELECTION,
    "evidenceBinding": "legacy-path-check",
}


def review_policy(spec: dict[str, Any]) -> dict[str, Any]:
    policy = spec.get("reviewPolicy")
    return policy if isinstance(policy, dict) else LEGACY_REVIEW_POLICY


def review_hashes_required(spec: dict[str, Any]) -> bool:
    policy = review_policy(spec)
    return (
        policy.get("version") == REVIEW_POLICY_VERSION
        and policy.get("evidenceBinding") == SHA_REQUIRED_BINDING
    )


def latest_review_for_pass(
    spec: dict[str, Any],
    pass_id: str,
) -> dict[str, Any] | None:
    history = spec.get("reviewHistory", [])
    if not isinstance(history, list):
        return None
    return next(
        (
            entry
            for entry in reversed(history)
            if isinstance(entry, dict) and entry.get("passId") == pass_id
        ),
        None,
    )


def authoritative_reviews(spec: dict[str, Any]) -> dict[str, tuple[int, dict[str, Any]]]:
    history = spec.get("reviewHistory", [])
    if not isinstance(history, list):
        return {}
    latest: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, entry in enumerate(history):
        if not isinstance(entry, dict):
            continue
        pass_id = entry.get("passId")
        if isinstance(pass_id, str) and pass_id:
            latest[pass_id] = (index, entry)
    return latest


def is_remote_or_virtual_path(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme.lower() in {
        "http",
        "https",
        "data",
        "blob",
        "session-artifact",
    }


def resolve_local_evidence_path(
    value: str,
    spec_path: Path | None = None,
) -> Path | None:
    if not value or is_remote_or_virtual_path(value):
        return None
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve() if candidate.is_file() else None
    bases: list[Path] = []
    if spec_path is not None:
        resolved_spec = spec_path.expanduser().resolve()
        bases.extend((resolved_spec.parent, *resolved_spec.parents))
    bases.extend((Path.cwd(), REPO_ROOT))
    seen: set[Path] = set()
    for base in bases:
        resolved = (base / candidate).resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    return None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bind_visual_evidence_hashes(
    visual: dict[str, Any],
    spec_path: Path | None = None,
) -> dict[str, Any]:
    for path_field, hash_field in EVIDENCE_FIELDS.items():
        value = visual.get(path_field)
        binding_field = path_field.replace("Screenshot", "").replace("Image", "") + "Binding"
        if not isinstance(value, str) or not value.strip():
            visual.pop(hash_field, None)
            visual.pop(binding_field, None)
            continue
        if is_remote_or_virtual_path(value):
            visual.pop(hash_field, None)
            visual[binding_field] = "remote-unverified"
            continue
        resolved = resolve_local_evidence_path(value, spec_path)
        if resolved is None:
            raise FileNotFoundError(f"{path_field} does not exist: {value}")
        visual[hash_field] = file_sha256(resolved)
        visual[binding_field] = "local-sha256"
    return visual


def visual_evidence_hash_failures(
    visual: Any,
    spec_path: Path | None = None,
    *,
    require_local: bool = True,
    require_hashes: bool = True,
    require_identity: bool | None = None,
) -> list[str]:
    if not isinstance(visual, dict):
        return ["visualEvidence must be an object"]
    failures: list[str] = []
    if require_identity is None:
        require_identity = require_hashes and require_local
    if require_identity:
        for field in ("reviewId", "reviewedAt"):
            value = visual.get(field)
            if not isinstance(value, str) or not value.strip():
                failures.append(f"{field} is required for production visual evidence")
    for path_field, hash_field in EVIDENCE_FIELDS.items():
        value = visual.get(path_field)
        required = path_field in REQUIRED_LOCAL_FIELDS
        if not isinstance(value, str) or not value.strip():
            if required and require_local:
                failures.append(f"{path_field} is required")
            continue
        if is_remote_or_virtual_path(value):
            if required and require_local:
                failures.append(
                    f"{path_field} must be local SHA-256-bound evidence; "
                    "remote/virtual evidence is record-only"
                )
            continue
        resolved = resolve_local_evidence_path(value, spec_path)
        if resolved is None:
            failures.append(f"{path_field} local file is missing: {value}")
            continue
        expected = visual.get(hash_field)
        if expected is None and not require_hashes:
            continue
        if not isinstance(expected, str) or len(expected) != 64:
            failures.append(f"{hash_field} is required for local {path_field}")
            continue
        actual = file_sha256(resolved)
        if expected.lower() != actual:
            failures.append(
                f"{hash_field} mismatch for {path_field}: "
                f"expected {expected.lower()}, actual {actual}"
            )
    return failures


def review_visual_evidence_failures(
    spec: dict[str, Any],
    visual: Any,
    spec_path: Path | None = None,
    *,
    require_local: bool = True,
) -> list[str]:
    require_hashes = review_hashes_required(spec)
    return visual_evidence_hash_failures(
        visual,
        spec_path,
        require_local=require_local,
        require_hashes=require_hashes,
        require_identity=require_hashes and require_local,
    )
