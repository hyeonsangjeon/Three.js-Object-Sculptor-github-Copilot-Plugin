# Visual Regression Matrix

`visual_regression_matrix.py` builds a deterministic review plan and gate report
for one base `ObjectSculptSpec` plus every curated variant in a Sculpt DNA
manifest. It does not render pixels or replace AI vision. It verifies that each
required asset/viewpoint cell points to the latest review for its declared pass,
that the exact local render and comparison files still match their SHA-256
bindings, and that global, required-layer, and selected semantic scores pass.

## Manifest configuration

The optional `visualRegressionMatrix` block is additive to
`sculpt-dna-manifest.json`:

```json
{
  "visualRegressionMatrix": {
    "schemaVersion": "1.0",
    "viewpoints": [
      {
        "id": "front",
        "passId": "blockout",
        "cameraView": "front",
        "renderPathTemplate": "evidence/{assetId}/{viewpointId}-render.png",
        "comparisonPathTemplate": "evidence/{assetId}/{viewpointId}-comparison.png",
        "featureIds": [
          "overall-silhouette"
        ]
      },
      {
        "id": "surface-detail",
        "passId": "surface-pass",
        "cameraView": "surface-detail",
        "renderPathTemplate": "evidence/{assetId}/{viewpointId}-render.png",
        "comparisonPathTemplate": "evidence/{assetId}/{viewpointId}-comparison.png",
        "featureIds": [
          "reference-material-system"
        ]
      }
    ]
  }
}
```

Viewpoint IDs are sorted lexicographically. The base asset is always first and
uses the reserved ID `base`; variants follow in ascending `variantId` order.
Templates may use only `{assetId}`, `{assetRole}`, `{passId}`,
`{variantIndex}`, and `{viewpointId}`. They must produce repository-relative
paths. When a template is omitted, an existing authoritative review path is
recorded as expected; a missing review gets the deterministic
`visual-regression/<asset>/<view>-{render|comparison}.png` plan.

`featureIds` selects the semantic reviews required for that viewpoint. When it
is omitted, the CLI selects the critical or `mustPass` targets assigned to the
viewpoint's pass. Required layer IDs always come from the asset's existing
`selfCorrectLoop.visualAcceptance.requiredLayerScores`; the matrix cannot lower
that policy.

For a one-off matrix, omit the manifest block and repeat
`--viewpoint VIEWPOINT_ID=PASS_ID`. `--render-template`,
`--comparison-template`, and `--feature-id` apply to CLI-defined viewpoints.

## Command

```bash
python3 scripts/visual_regression_matrix.py \
  object-sculpt-spec.json \
  variants/sculpt-dna-manifest.json \
  --out variants/visual-regression-report.json \
  --summary
```

JSON is written to stdout unless `--out` is provided. `--summary` writes a
stable human-readable summary to stderr without contaminating JSON output.

Exit codes:

- `0`: every matrix cell is `passing`
- `1`: the matrix is valid, but one or more cells are `missing`, `stale`, or
  `failing`
- `2`: input JSON, schema, paths, IDs, templates, or viewpoint configuration
  are invalid

## Report schema 1.0

The report has `kind: "sculpt-dna-visual-regression-matrix"` and
`schemaVersion: "1.0"`. It records:

- immutable input SHA-256 digests
- explicit AI-vision authority and diagnostic-only pixel-metric policy
- deterministic ordering policy
- normalized viewpoints and assets
- one cell for every base/variant and viewpoint pair
- expected and recorded render/comparison paths and hashes
- latest authoritative review identity, action, score, and threshold
- required layer and selected semantic feature results
- typed issues and stable summary counts

Input and asset paths inside this checkout are emitted relative to the
repository root; paths outside it remain absolute. Report bytes therefore do
not depend on the process working directory.

Cell states are:

- `missing`: a spec, latest review, named camera, local image, binding, required
  layer, or semantic review is absent
- `stale`: the base source binding, expected path, camera, or local SHA-256 no
  longer matches current inputs
- `passing`: current SHA-bound evidence and every AI-vision gate pass
- `failing`: current evidence exists, but promotion, pass action, global score,
  layer score, semantic score, visibility, or an existing production pass gate
  fails

Summary keys always use `total`, `missing`, `stale`, `passing`, `failing`.
Cells prefer `missing`, then `stale`, then `failing` when several issue types
apply, while retaining every issue for diagnosis.

## Compatibility and migration

This is an additive manifest/report schema. It changes no
`ObjectSculptSpec`, Sculpt DNA, review, production, release, or evidence field.
Existing manifests remain valid for generation and release. To opt into a
repeatable matrix, add `visualRegressionMatrix` to a curated manifest or pass
viewpoints on the command line. Do not copy old review evidence into generated
variants; render and review each promoted variant from every configured
viewpoint.

AI vision remains the final visual authority. Pixel differences, SSIM, or other
render metrics may assist diagnosis, but they cannot create a passing cell.
