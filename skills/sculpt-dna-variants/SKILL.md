---
name: sculpt-dna-variants
description: Use when the user wants to turn an ObjectSculptSpec or procedural Three.js object into a controlled family of deterministic variants while preserving topology, attachments, action-ready hierarchy, and visual quality gates.
---

# Sculpt DNA Variants

Use this skill after or alongside `object-to-threejs-procedural` when the user wants a reusable asset family, product configurator, game-prop set, seeded environment variation, or semantic design exploration rather than one fixed reconstruction.

## Required Base Sculpt Contract

Do not start with random variants. Before Sculpt DNA generation, complete or verify the base sculpt workflow:

1. Validate the reference and estimate its reconstruction complexity.
2. Decompose the target into silhouette, structural components, materials, and surface details.
3. Build it in locked stages: `blockout` -> `structural-pass` -> `form-refinement` -> `material-pass` -> `surface-pass`.
4. Render browser screenshots after each visual pass and use AI-vision comparison feedback to self-correct the spec or code.
5. Create stable pivots, sockets, colliders, parent-child hierarchy, and destruction groups so the model remains ready for animation, transformation, physics, or destruction.
6. Generate variants only after the base `ObjectSculptSpec` and its semantic systems are meaningful.

If the base model has not completed this contract, invoke or follow `object-to-threejs-procedural` first. Sculpt DNA extends a validated procedural object; it does not replace reconstruction, staged sculpting, or visual review.

## Core Promise

Sculpt DNA exposes a small, named design space without turning the object into random noise:

1. Choose semantic parameters such as body width, branch spread, wheel radius, repetition count, palette family, or surface age.
2. Bind every parameter to an existing numeric or palette field in `ObjectSculptSpec`.
3. Constrain related parameters with range, ratio, equality, or shared-sample groups.
4. Preserve component IDs, parent links, material references, sockets, fracture groups, attachment roots, build-pass order, and semantic review targets.
5. Generate deterministic variant specs from a root seed.
6. Reset inherited screenshot and review evidence because a changed object must earn visual acceptance again.
7. Use Coverage Curator's deterministic greedy heuristic to select a broadly separated small family instead of showing near-duplicate random samples.

Do not market uncontrolled randomization as procedural design. A good Sculpt DNA parameter has a name a designer understands, a bounded range, a visible purpose, and an invariant explaining what it must not break.

## Helper Commands

Scripts are relative to this skill directory:

- `python3 ../../scripts/sculpt_dna.py init object-sculpt-spec.json --in-place` derives conservative starter controls from the root transform, material roughness/palette, and repetition counts.
- `python3 ../../scripts/sculpt_dna.py validate object-sculpt-spec.json --json` validates parameter targets, distributions, constraints, invariants, and policy.
- `python3 ../../scripts/sculpt_dna.py generate object-sculpt-spec.json --out-dir variants --count 8 --seed 1337` writes deterministic variant specs plus `sculpt-dna-manifest.json`.
- `python3 ../../scripts/sculpt_dna.py curate object-sculpt-spec.json --out-dir curated --count 3 --pool-size 24 --seed 1337` generates a larger safe pool, then selects the most diverse representative family.
- Add `--preview` only for non-promotable contact sheets before the base sculpt reaches `surface-pass`; preview provenance remains blocked pending per-variant visual review.
- `python3 ../../scripts/validate_sculpt_spec.py variants/<variant>.json` validates each variant against the complete ObjectSculptSpec contract.
- `python3 ../../scripts/generate_threejs_factory.py variants/<variant>.json --out src/createVariantModel.ts` generates the currently unlocked pass for a selected variant.

## Required Workflow

1. Validate the base spec with `validate_sculpt_spec.py`.
2. Initialize Sculpt DNA.
3. Replace generic parameter names with object-specific language and remove controls that do not create a useful visible delta.
4. Review `references/sculpt-dna-schema.md` and add constraints for coupled proportions.
5. Run both Sculpt DNA validation and full spec validation.
6. Generate a safe candidate pool.
7. Use Coverage Curator when the user needs a small contact sheet, README demo, or representative design family.
8. Inspect the manifest to confirm seeds, mutations, invariant checks, selected candidate indexes, and coverage score.
9. Render selected variants from consistent viewpoints.
10. Re-run the normal screenshot comparison and AI-vision gates for every promoted variant.

Production `generate` and `curate` commands must reject a base spec that has not completed `blockout` through `surface-pass`. `--preview` is the explicit exception for early design exploration and README contact sheets; never describe preview variants as accepted or production-ready.

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
- A curated family records its candidate pool, selected indexes, normalized parameter-distance strategy, and coverage score.

If valid samples cannot be produced within `maxAttemptsPerVariant`, refine the ranges or constraints. Do not silently relax the invariant contract.
