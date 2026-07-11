---
name: sculpt-dna-variants
description: Use when the user wants to turn an ObjectSculptSpec or procedural Three.js object into a controlled family of deterministic variants while preserving topology, attachments, action-ready hierarchy, and visual quality gates.
---

# Sculpt DNA Variants

Use this skill after or alongside `object-to-threejs-procedural` when the user wants a reusable asset family, product configurator, game-prop set, seeded environment variation, or semantic design exploration rather than one fixed reconstruction.

## Core Promise

Sculpt DNA exposes a small, named design space without turning the object into random noise:

1. Choose semantic parameters such as body width, branch spread, wheel radius, repetition count, palette family, or surface age.
2. Bind every parameter to an existing numeric or palette field in `ObjectSculptSpec`.
3. Constrain related parameters with range, ratio, equality, or shared-sample groups.
4. Preserve component IDs, parent links, material references, sockets, fracture groups, attachment roots, build-pass order, and semantic review targets.
5. Generate deterministic variant specs from a root seed.
6. Reset inherited screenshot and review evidence because a changed object must earn visual acceptance again.

Do not market uncontrolled randomization as procedural design. A good Sculpt DNA parameter has a name a designer understands, a bounded range, a visible purpose, and an invariant explaining what it must not break.

## Helper Commands

Scripts are relative to this skill directory:

- `python3 ../../scripts/sculpt_dna.py init object-sculpt-spec.json --in-place` derives conservative starter controls from the root transform, material roughness/palette, and repetition counts.
- `python3 ../../scripts/sculpt_dna.py validate object-sculpt-spec.json --json` validates parameter targets, distributions, constraints, invariants, and policy.
- `python3 ../../scripts/sculpt_dna.py generate object-sculpt-spec.json --out-dir variants --count 8 --seed 1337` writes deterministic variant specs plus `sculpt-dna-manifest.json`.
- `python3 ../../scripts/validate_sculpt_spec.py variants/<variant>.json` validates each variant against the complete ObjectSculptSpec contract.
- `python3 ../../scripts/generate_threejs_factory.py variants/<variant>.json --out src/createVariantModel.ts` generates the currently unlocked pass for a selected variant.

## Required Workflow

1. Validate the base spec with `validate_sculpt_spec.py`.
2. Initialize Sculpt DNA.
3. Replace generic parameter names with object-specific language and remove controls that do not create a useful visible delta.
4. Review `references/sculpt-dna-schema.md` and add constraints for coupled proportions.
5. Run both Sculpt DNA validation and full spec validation.
6. Generate a small contact set first, normally four to eight variants.
7. Inspect the manifest to confirm seeds, mutations, and invariant checks.
8. Render selected variants from consistent viewpoints.
9. Re-run the normal screenshot comparison and AI-vision gates for every promoted variant.

## Authoring Rules

- Prefer one semantic parameter over many low-level parameters that describe the same design decision.
- Do not auto-generate geometry-size controls when child attachments, semantic pivots, sockets, or collider proxies would need coupled updates. Author an explicit derived-control contract first.
- Use `group` when several parameters should move through their ranges together.
- Use ratio constraints for proportions that define object identity.
- Vary `attachment.localEnd`, radii, or overlap for attached parts; never move their root socket or `localStart`.
- Keep mutation ranges conservative until a visual family review proves larger ranges are safe.
- Treat material variation as PBR variation, not only hue shifting.
- Keep deterministic seeds in source control when reproducible art direction matters.
- Do not inherit a base model's `reviewHistory` or `visualEvidence`; Sculpt DNA resets both by design.

## Acceptance Gate

A generated variant is acceptable only when:

- Sculpt DNA schema validation passes.
- All declared constraints pass.
- Every semantic invariant reports unchanged.
- Full ObjectSculptSpec validation passes.
- The generated factory contains `root.userData.sculptDNA` and `root.userData.variantProvenance`.
- Fresh visual evidence meets the same silhouette, component, material, lighting, and critical-feature thresholds as the base object.

If valid samples cannot be produced within `maxAttemptsPerVariant`, refine the ranges or constraints. Do not silently relax the invariant contract.
