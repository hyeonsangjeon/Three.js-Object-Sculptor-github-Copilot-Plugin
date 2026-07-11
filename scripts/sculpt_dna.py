#!/usr/bin/env python3
"""Initialize, validate, and generate deterministic Sculpt DNA variant specs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from sculpt_pass_orchestrator import completed_passes, pass_order
from sculpt_dna_core import (
    DNA_SCHEMA_VERSION,
    curate_variants,
    generate_variant,
    make_default_sculpt_dna,
    validate_sculpt_dna_block,
)

REQUIRED_BASE_PASSES = [
    "blockout",
    "structural-pass",
    "form-refinement",
    "material-pass",
    "surface-pass",
]


def parse_spec(source: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(source.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("spec must be a JSON object")
    return payload


def load_spec(path: Path) -> dict[str, Any]:
    return parse_spec(path.read_bytes())


def json_payload(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def write_output(path: Path, value: Any, force: bool) -> None:
    if path.exists() and not force:
        raise ValueError(f"{path} already exists; use --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_payload(value), encoding="utf-8")

def resolve_evidence_path(value: str, spec_path: Path) -> Path | None:
    if value.startswith(("http://", "https://", "data:", "session-artifact:")):
        return None
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    for base in (Path.cwd(), *spec_path.resolve().parents):
        resolved = (base / candidate).resolve()
        if resolved.is_file():
            return resolved
    return None


def validate_production_evidence(
    spec: dict[str, Any],
    spec_path: Path,
) -> None:
    history = spec.get("reviewHistory", [])
    missing: list[str] = []
    for pass_id in REQUIRED_BASE_PASSES:
        entry = next(
            (
                item
                for item in history
                if isinstance(item, dict)
                and item.get("passId") == pass_id
                and item.get("action") == "continue"
            ),
            None,
        )
        visual = entry.get("visualEvidence") if isinstance(entry, dict) else None
        for field in ("renderScreenshot", "comparisonImage"):
            value = visual.get(field) if isinstance(visual, dict) else None
            if not isinstance(value, str) or resolve_evidence_path(value, spec_path) is None:
                missing.append(f"{pass_id}.{field}")
    if missing:
        raise ValueError(
            "production variant generation requires existing local visual evidence files: "
            + ", ".join(missing)
        )


def variant_gate(
    spec: dict[str, Any],
    preview: bool,
    spec_path: Path | None = None,
) -> tuple[list[str], list[str]]:
    pipeline = spec.get("sculptPipeline")
    cached = (
        pipeline.get("completedPasses", [])
        if isinstance(pipeline, dict) and isinstance(pipeline.get("completedPasses"), list)
        else []
    )
    cached_ids = [str(item) for item in cached]
    completed_ids = completed_passes(spec, pass_order(spec))
    if cached_ids != completed_ids and not preview:
        raise ValueError(
            "sculptPipeline.completedPasses is out of sync with evidence-backed reviewHistory; "
            "run sculpt_pass_orchestrator.py sync before production variant generation"
        )
    missing = [pass_id for pass_id in REQUIRED_BASE_PASSES if pass_id not in completed_ids]
    if missing and not preview:
        raise ValueError(
            "base sculpt must complete through surface-pass before variant generation; "
            "missing: "
            + ", ".join(missing)
            + ". Use --preview only for non-promotable design exploration."
        )
    if not preview and not missing:
        if spec_path is None:
            raise ValueError(
                "production variant generation requires the source spec path "
                "to verify visual evidence files"
            )
        validate_production_evidence(spec, spec_path)
    return completed_ids, missing


def mark_preview_mode(
    variants: list[tuple[dict[str, Any], dict[str, Any]]],
    preview: bool,
) -> None:
    for variant, provenance in variants:
        provenance["previewMode"] = preview
        provenance["passGateStatus"] = (
            "pending-per-variant-visual-review"
            if preview
            else "base-sculpt-gate-complete"
        )
        variant["variantProvenance"] = provenance


def command_init(args: argparse.Namespace) -> int:
    source_path = args.spec.expanduser().resolve()
    source_bytes = source_path.read_bytes()
    spec = parse_spec(source_bytes)
    spec["sculptDNA"] = make_default_sculpt_dna(spec)
    if args.in_place:
        source_path.write_text(json_payload(spec), encoding="utf-8")
        print(source_path)
    elif args.out:
        output = args.out.expanduser().resolve()
        write_output(output, spec, args.force)
        print(output)
    else:
        print(json_payload(spec), end="")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    spec = load_spec(args.spec.expanduser().resolve())
    errors, warnings = validate_sculpt_dna_block(spec)
    result = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "schemaVersion": (
                spec.get("sculptDNA", {}).get("schemaVersion")
                if isinstance(spec.get("sculptDNA"), dict)
                else None
            ),
            "enabled": (
                spec.get("sculptDNA", {}).get("enabled")
                if isinstance(spec.get("sculptDNA"), dict)
                else None
            ),
            "parameters": (
                len(spec.get("sculptDNA", {}).get("parameters", []))
                if isinstance(spec.get("sculptDNA"), dict)
                and isinstance(spec.get("sculptDNA", {}).get("parameters"), list)
                else 0
            ),
        },
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("PASS" if result["ok"] else "FAIL")
        for warning in warnings:
            print(f"warning: {warning}")
        for error in errors:
            print(f"error: {error}")
    return 0 if result["ok"] else 1


def write_variant_family(
    *,
    source_path: Path,
    source_bytes: bytes,
    output_dir: Path,
    variants_payload: list[tuple[dict[str, Any], dict[str, Any]]],
    root_seed: int,
    force: bool,
    print_json: bool,
    manifest_extra: dict[str, Any] | None = None,
) -> int:
    output_variants: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    for variant, provenance in variants_payload:
        output_path = (output_dir / f"{provenance['variantId']}.json").resolve()
        try:
            output_path.relative_to(output_dir)
        except ValueError as exc:
            raise ValueError(f"variant output escapes --out-dir: {output_path}") from exc
        output_variants.append((output_path, variant, provenance))
    manifest_path = output_dir / "sculpt-dna-manifest.json"
    collisions = [path for path, _, _ in output_variants if path.exists()]
    if manifest_path.exists():
        collisions.append(manifest_path)
    if collisions and not force:
        raise ValueError(
            "output files already exist; use --force to overwrite: "
            + ", ".join(str(path) for path in collisions)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schemaVersion": DNA_SCHEMA_VERSION,
        "sourceSpec": source_path.name,
        "sourceSpecSha256": hashlib.sha256(source_bytes).hexdigest(),
        "rootSeed": root_seed,
        "count": len(output_variants),
        "variants": [
            {
                "variantId": provenance["variantId"],
                "path": output_path.name,
                "variantSeed": provenance["variantSeed"],
                "attempt": provenance["attempt"],
                "mutations": provenance["mutations"],
                "invariants": provenance["invariants"],
                "reviewEvidenceReset": provenance["reviewEvidenceReset"],
                **{
                    key: provenance[key]
                    for key in (
                        "samplingMode",
                        "candidateIndex",
                        "curatedIndex",
                        "selectionScore",
                        "previewMode",
                        "passGateStatus",
                    )
                    if key in provenance
                },
            }
            for output_path, _, provenance in output_variants
        ],
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    with tempfile.TemporaryDirectory(prefix=".sculpt-dna-", dir=output_dir) as staging_dir:
        staging = Path(staging_dir)
        staged_outputs: list[tuple[Path, Path]] = []
        for output_path, variant, _ in output_variants:
            staged = staging / output_path.name
            staged.write_text(json_payload(variant), encoding="utf-8")
            staged_outputs.append((staged, output_path))
        staged_manifest = staging / manifest_path.name
        staged_manifest.write_text(json_payload(manifest), encoding="utf-8")
        for staged, output_path in staged_outputs:
            staged.replace(output_path)
        staged_manifest.replace(manifest_path)
    if print_json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        for output_path, _, _ in output_variants:
            print(output_path)
        print(manifest_path)
    return 0


def command_generate(args: argparse.Namespace) -> int:
    source_path = args.spec.expanduser().resolve()
    source_bytes = source_path.read_bytes()
    spec = parse_spec(source_bytes)
    dna = spec.get("sculptDNA")
    if not isinstance(dna, dict):
        raise ValueError("spec has no sculptDNA block; run sculpt_dna.py init first")
    policy = dna.get("variantPolicy") if isinstance(dna.get("variantPolicy"), dict) else {}
    count = args.count if args.count is not None else policy.get("defaultCount", 4)
    seed = args.seed if args.seed is not None else policy.get("defaultSeed", 1337)
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 100:
        raise ValueError("variant count must be an integer from 1 to 100")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("variant seed must be an integer")
    completed, missing = variant_gate(spec, args.preview, source_path)
    variants_payload = [
        generate_variant(spec, seed, index, dna)
        for index in range(1, count + 1)
    ]
    mark_preview_mode(variants_payload, args.preview)
    return write_variant_family(
        source_path=source_path,
        source_bytes=source_bytes,
        output_dir=args.out_dir.expanduser().resolve(),
        variants_payload=variants_payload,
        root_seed=seed,
        force=args.force,
        print_json=args.json,
        manifest_extra={
            "previewMode": args.preview,
            "passGateStatus": (
                "pending-per-variant-visual-review"
                if args.preview
                else "base-sculpt-gate-complete"
            ),
            "baseCompletedPasses": completed,
            "missingBasePasses": missing,
        },
    )


def command_curate(args: argparse.Namespace) -> int:
    source_path = args.spec.expanduser().resolve()
    source_bytes = source_path.read_bytes()
    spec = parse_spec(source_bytes)
    dna = spec.get("sculptDNA")
    if not isinstance(dna, dict):
        raise ValueError("spec has no sculptDNA block; run sculpt_dna.py init first")
    policy = dna.get("variantPolicy") if isinstance(dna.get("variantPolicy"), dict) else {}
    count = args.count if args.count is not None else policy.get("defaultCount", 4)
    seed = args.seed if args.seed is not None else policy.get("defaultSeed", 1337)
    pool_size = (
        args.pool_size
        if args.pool_size is not None
        else min(max(count * 8, 16), 500)
    )
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("variant seed must be an integer")
    completed, missing = variant_gate(spec, args.preview, source_path)
    curated, report = curate_variants(spec, seed, count, pool_size, dna)
    mark_preview_mode(curated, args.preview)
    report.update(
        {
            "previewMode": args.preview,
            "passGateStatus": (
                "pending-per-variant-visual-review"
                if args.preview
                else "base-sculpt-gate-complete"
            ),
            "baseCompletedPasses": completed,
            "missingBasePasses": missing,
        }
    )
    return write_variant_family(
        source_path=source_path,
        source_bytes=source_bytes,
        output_dir=args.out_dir.expanduser().resolve(),
        variants_payload=curated,
        root_seed=seed,
        force=args.force,
        print_json=args.json,
        manifest_extra=report,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Derive conservative starter controls and attach them to an ObjectSculptSpec",
    )
    init_parser.add_argument("spec", type=Path)
    destination = init_parser.add_mutually_exclusive_group()
    destination.add_argument("--out", type=Path)
    destination.add_argument("--in-place", action="store_true")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(handler=command_init)

    validate_parser = subparsers.add_parser("validate", help="Validate Sculpt DNA schema and base constraints")
    validate_parser.add_argument("spec", type=Path)
    validate_parser.add_argument("--json", action="store_true")
    validate_parser.set_defaults(handler=command_validate)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate deterministic variant ObjectSculptSpec files",
    )
    generate_parser.add_argument("spec", type=Path)
    generate_parser.add_argument("--out-dir", type=Path, required=True)
    generate_parser.add_argument("--count", type=int)
    generate_parser.add_argument("--seed", type=int)
    generate_parser.add_argument("--force", action="store_true")
    generate_parser.add_argument("--json", action="store_true")
    generate_parser.add_argument(
        "--preview",
        action="store_true",
        help="Allow non-promotable variants before the base sculpt completes surface-pass",
    )
    generate_parser.set_defaults(handler=command_generate)

    curate_parser = subparsers.add_parser(
        "curate",
        help="Greedily select a broadly separated deterministic family from a safe candidate pool",
    )
    curate_parser.add_argument("spec", type=Path)
    curate_parser.add_argument("--out-dir", type=Path, required=True)
    curate_parser.add_argument("--count", type=int)
    curate_parser.add_argument("--pool-size", type=int)
    curate_parser.add_argument("--seed", type=int)
    curate_parser.add_argument("--force", action="store_true")
    curate_parser.add_argument("--json", action="store_true")
    curate_parser.add_argument(
        "--preview",
        action="store_true",
        help="Allow a non-promotable preview family before the base sculpt completes surface-pass",
    )
    curate_parser.set_defaults(handler=command_curate)
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ValueError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
