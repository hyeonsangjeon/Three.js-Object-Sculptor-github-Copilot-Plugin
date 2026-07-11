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

from sculpt_dna_core import (
    DNA_SCHEMA_VERSION,
    generate_variant,
    make_default_sculpt_dna,
    validate_sculpt_dna_block,
)


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

    variants: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    output_dir = args.out_dir.expanduser().resolve()
    for index in range(1, count + 1):
        variant, provenance = generate_variant(spec, seed, index, dna)
        output_path = (output_dir / f"{provenance['variantId']}.json").resolve()
        try:
            output_path.relative_to(output_dir)
        except ValueError as exc:
            raise ValueError(f"variant output escapes --out-dir: {output_path}") from exc
        variants.append((output_path, variant, provenance))
    manifest_path = output_dir / "sculpt-dna-manifest.json"
    collisions = [path for path, _, _ in variants if path.exists()]
    if manifest_path.exists():
        collisions.append(manifest_path)
    if collisions and not args.force:
        raise ValueError(
            "output files already exist; use --force to overwrite: "
            + ", ".join(str(path) for path in collisions)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schemaVersion": DNA_SCHEMA_VERSION,
        "sourceSpec": source_path.name,
        "sourceSpecSha256": hashlib.sha256(source_bytes).hexdigest(),
        "rootSeed": seed,
        "count": count,
        "variants": [
            {
                "variantId": provenance["variantId"],
                "path": output_path.name,
                "variantSeed": provenance["variantSeed"],
                "attempt": provenance["attempt"],
                "mutations": provenance["mutations"],
                "invariants": provenance["invariants"],
                "reviewEvidenceReset": provenance["reviewEvidenceReset"],
            }
            for output_path, _, provenance in variants
        ],
    }
    with tempfile.TemporaryDirectory(prefix=".sculpt-dna-", dir=output_dir) as staging_dir:
        staging = Path(staging_dir)
        staged_outputs: list[tuple[Path, Path]] = []
        for output_path, variant, _ in variants:
            staged = staging / output_path.name
            staged.write_text(json_payload(variant), encoding="utf-8")
            staged_outputs.append((staged, output_path))
        staged_manifest = staging / manifest_path.name
        staged_manifest.write_text(json_payload(manifest), encoding="utf-8")
        for staged, output_path in staged_outputs:
            staged.replace(output_path)
        staged_manifest.replace(manifest_path)
    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        for output_path, _, _ in variants:
            print(output_path)
        print(manifest_path)
    return 0


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
    generate_parser.set_defaults(handler=command_generate)
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
