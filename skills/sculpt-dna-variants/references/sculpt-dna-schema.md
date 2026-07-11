# Sculpt DNA Schema

`sculptDNA` is an optional `ObjectSculptSpec` block. New specs contain a disabled block; `sculpt_dna.py init` enables it and derives conservative starter controls.

## Parameter

```json
{
  "id": "body-width",
  "label": "Body width",
  "target": {
    "kind": "component",
    "id": "root",
    "path": "transform.scale.0"
  },
  "operation": "multiply",
  "distribution": "triangular",
  "range": {
    "min": 0.85,
    "max": 1.15
  },
  "precision": 4,
  "semanticEffects": [
    "silhouette",
    "horizontal proportions",
    "collider review"
  ]
}
```

Target kinds are `component`, `material`, and `repetition`. Paths are dotted paths into an existing record; numeric segments address array items.

Operations:

- `set`: sampled value replaces the current value.
- `multiply`: sampled value multiplies the current numeric value.
- `add`: sampled value is added to the current numeric value.

Distributions:

- `uniform`: equal probability across the range.
- `triangular`: favors the range midpoint; recommended for conservative variants.
- `normal`: clipped normal distribution around the midpoint.
- `choice`: selects from `choices` and requires `operation: "set"`.

Parameters with the same non-empty `group` share one normalized sample. Use this for coupled controls such as wheel radius and fender clearance.

The initializer omits geometry-size controls when a component has child attachments, non-center pivots, sockets, or collider proxies. Changing dimensions without updating those dependent action contracts would produce a visually changed but semantically broken variant.

## Constraints

Range:

```json
{
  "id": "safe-roughness",
  "type": "range",
  "target": {
    "kind": "material",
    "id": "paint",
    "path": "roughness.base"
  },
  "min": 0.25,
  "max": 0.8
}
```

Ratio:

```json
{
  "id": "body-aspect",
  "type": "ratio",
  "left": {
    "kind": "component",
    "id": "root",
    "path": "transform.scale.0"
  },
  "right": {
    "kind": "component",
    "id": "root",
    "path": "transform.scale.1"
  },
  "min": 0.8,
  "max": 1.4
}
```

Equality:

```json
{
  "id": "paired-wheel-radius",
  "type": "equals",
  "left": {
    "kind": "component",
    "id": "left-wheel",
    "path": "dimensions.radius"
  },
  "right": {
    "kind": "component",
    "id": "right-wheel",
    "path": "dimensions.radius"
  },
  "tolerance": 0.0001
}
```

Generation retries deterministic samples until every constraint passes or `maxAttemptsPerVariant` is exhausted.

## Protected Invariants

Sculpt DNA v1 protects:

- component IDs
- parent links
- material IDs and component material references
- socket IDs
- fracture groups
- attachment parent/root sockets and `localStart`
- build-pass order
- feature-review target IDs
- repetition-system IDs

The mutable path allowlist intentionally excludes these fields. Add a new component or rig change to the base spec, not to a variant parameter.

## Provenance

Every generated spec gets `variantProvenance` with:

- source and variant IDs
- root and derived variant seeds
- successful sampling attempt
- before/after mutation values
- checked invariants
- whether review evidence was reset

The Three.js factory copies both `sculptDNA` and `variantProvenance` into `root.userData`.

## Coverage Curator

`generate` returns deterministic candidates in seed order. This is useful for batch generation, but a small sample can contain visually similar neighbors.

`curate` uses a deterministic greedy approximation for the presentation problem:

```bash
python3 ../../scripts/sculpt_dna.py curate object-sculpt-spec.json \
  --out-dir curated \
  --count 3 \
  --pool-size 24 \
  --seed 1337
```

The curator:

1. generates a larger pool through the normal constraint and invariant gates
2. normalizes numeric ranges and categorical choices into one parameter vector
3. selects an extreme candidate, then greedily maximizes the minimum distance from already selected variants; it does not claim a global combinatorial optimum
4. renames selected variants into a stable sequential family
5. records `candidateIndex`, `curatedIndex`, `selectionScore`, `coverageScore`, and the selection strategy

Coverage measures design-space separation, not visual quality. Every curated result still requires fresh browser and AI-vision review.
