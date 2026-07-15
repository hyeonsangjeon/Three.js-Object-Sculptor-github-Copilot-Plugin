# Render Integration Contract v1

Use this gate after optimization and after placing the procedural asset in its
real host application. It detects renderer, post-processing, layer, camera,
occlusion, exposure, and performance drift that a standalone turntable cannot
prove absent.

The gate consumes JSON snapshots. It does not launch a browser, render an image,
or replace screenshot comparison and AI-vision review.

## Command

From the plugin repository root:

```bash
python3 scripts/render_integration_contract.py \
  render-integration-contract.json \
  standalone-snapshot.json \
  host-snapshot.json \
  --out integration-report.json \
  --summary
```

From this skill directory, use `../../scripts/render_integration_contract.py`.

Exit codes:

- `0`: every required integration check passes
- `1`: valid report with one or more `missing`, `stale`, or `failing` checks
- `2`: malformed, unsafe, non-finite, unsupported-schema, or inconsistent input

JSON goes to stdout unless `--out` is provided. `--summary` adds a bounded
human-readable summary to stderr.

## Authority boundary

Every report contains:

```json
{
  "authority": {
    "finalVisualAuthority": "ai-vision",
    "runtimeMetrics": "diagnostic-gates-only",
    "runtimeMetricsCanApproveVisualQuality": false,
    "integrationPassIsVisualApproval": false
  }
}
```

Coverage and luminance can reject unsafe integration telemetry. They cannot
manufacture an AI visual pass. A production asset needs both current visual
acceptance evidence and a passing host integration report.

## Contract document

Required envelope:

| Field | Type | Meaning |
| --- | --- | --- |
| `schemaVersion` | string | Exactly `"1.0"` |
| `kind` | string | Exactly `"render-integration-contract"` |
| `contractId` | ID | Stable contract identity |
| `asset` | object | Asset/profile identity and immutable bindings |
| `renderer` | object | Output transform, exposure, pass-count, and DPR policy |
| `renderTargets` | array | Required render-target policies |
| `selectiveRendering` | object | Required selective layers and lights |
| `views` | array | Required named host/standalone viewpoints |
| `angleConsistency` | object | Cross-camera visual diagnostic limits |
| `townExposure` | object | Standalone/host town invariance policy |
| `performance` | object | Per-view budgets and camera-direction spread limits |
| `errors` | object | Console/network error budgets |

IDs match `^[a-z0-9][a-z0-9._-]*$`. Collections are keyed by `id` and reject
duplicates.

### Asset identity and bindings

```json
{
  "asset": {
    "assetId": "repolis-tree",
    "profileId": "repolis-living-archive",
    "source": {
      "path": "examples/repolis-tree/object-sculpt-spec.json",
      "sha256": "<64 hexadecimal characters>"
    },
    "factory": {
      "path": "examples/repolis-hero/repolis-output/createRepolisHero.js",
      "sha256": "<64 hexadecimal characters>"
    }
  }
}
```

Snapshot `assetId` and `profileId` must match the contract. An identity mismatch
is invalid input, not a normal failed check. Missing bindings become `missing`;
safe but different paths or hashes become `stale`.

Binding paths are metadata. They must be canonical repository-relative POSIX
paths. Absolute POSIX/Windows paths, `..`, URLs, virtual schemes, backslashes,
empty paths, and non-canonical repeated separators are rejected. The CLI does
not open files named by binding metadata; it compares the declared path and
SHA-256.

### Renderer policy

```json
{
  "renderer": {
    "toneMapping": "ACESFilmicToneMapping",
    "outputColorSpace": "SRGBColorSpace",
    "standaloneExposure": 1.0,
    "maxHostExposureDelta": 0.05,
    "outputPassCount": 1,
    "maxPixelRatio": 2.0
  }
}
```

- `toneMapping` and `outputColorSpace` must match in both snapshots.
- standalone `exposure` must equal `standaloneExposure`.
- `abs(host.exposure - standalone.exposure)` must not exceed
  `maxHostExposureDelta`.
- `outputPassCount` is exact. Count the complete output pipeline, including
  nested composers. A host-added second `OutputPass` fails
  `tone-mapping-count`.
- `pixelRatio` must not exceed `maxPixelRatio`.

### Render targets

Each declared target requires:

| Field | Type | Rule |
| --- | --- | --- |
| `id` | ID | Stable target identity |
| `type` | string | Exact renderer type name |
| `colorSpace` | string | Exact target texture color space |
| `depthBuffer` | boolean | Exact depth allocation policy |
| `minScale` / `maxScale` | finite number > 0 | Allowed viewport-relative scale |
| `maxPixels` | integer > 0 | Maximum `width * height` |

Snapshot targets additionally expose `scale`, `width`, `height`, and
`pixelCount`. If all dimensions are present, `pixelCount` must equal
`width * height`. This catches DPR/render-target multiplication even when the
CSS canvas size is unchanged.

Extra undeclared host targets are allowed and unchecked. Required target IDs
must be present in both snapshots.

### Selective layers

Each layer policy contains:

- `id`
- Three.js-compatible `index` from 0 through 31
- `owner`
- `requiredMembers`
- `forbiddenMembers`

Snapshot layers expose `members`. Required members are a subset check; extra
members are allowed unless named by `forbiddenMembers`. For selective bloom,
put the emissive hero system in `requiredMembers` and town/background systems
in `forbiddenMembers`.

### Selective lights

Each light policy contains:

- `id`
- `owner`
- `requiredLayers`
- `forbiddenLayers`
- normalized `maxTownSpill` from 0 through 1

Snapshot lights expose their active `layers` and measured/estimated
`townSpill`. A town-owned sun can remain an undeclared host light. A declared
hero light must keep its owner/layers and stay within the town-spill threshold.

### Views and semantic systems

Every view requires an `id`, `cameraId`, and at least one `requiredSystems`
entry. View and semantic policies can declare:

- `minCoverage` / `maxCoverage`
- `minP50Luminance` / `maxP50Luminance`
- `minP90Luminance` / `maxP90Luminance`
- semantic-only `mustBeVisible`

Coverage and luminance are normalized from 0 through 1. Use one documented
measurement method for both snapshots. Examples:

- asset or system mask pixels divided by viewport pixels
- P50/P90 relative luminance from the masked pixels after the same output stage
- occlusion proxy projected bounds divided by viewport pixels

Whenever both percentiles are present, P50 must not exceed P90. Frame telemetry
similarly requires P50 frame time to be no greater than P95.

An occlusion proxy need not render visibly. Record it as:

```json
{
  "id": "hero-occlusion-proxy",
  "mustBeVisible": false,
  "maxCoverage": 0.12
}
```

Record angle-sensitive emissive systems with `mustBeVisible: true`, a minimum
coverage, and minimum luminance for every required fixed camera.

### Angle consistency

```json
{
  "angleConsistency": {
    "viewIds": ["front", "quarter", "back"],
    "minCoverageToMedian": 0.88,
    "maxP90LuminanceSpread": 0.1,
    "forbidBlackFrames": true,
    "forbidClipping": true
  }
}
```

For each snapshot:

```text
coverage ratio = minimum(view coverage) / median(view coverage)
P90 spread = maximum(view P90 luminance) - minimum(view P90 luminance)
```

If the coverage median is zero, the ratio is zero. Computed values are rounded
to 12 decimal places in the report. Black-frame and clipping flags are explicit
snapshot booleans; the CLI does not infer them or synthesize them from pixel
metrics.

### Town exposure invariance

`townExposure.semanticSystemId` must be required by every listed view.

For each view:

```text
delta = abs(host town P50 luminance - standalone town P50 luminance)
```

The maximum delta must not exceed `maxP50LuminanceDelta`. This separates an
intentional host-wide exposure tolerance from hero light spill into town.

### Performance

Required policy:

```json
{
  "performance": {
    "maxCalls": 180,
    "maxTriangles": 900000,
    "minFps": 50.0,
    "maxFrameTimeP50Ms": 18.0,
    "maxFrameTimeP95Ms": 25.0,
    "maxDirectionCallsSpread": 20,
    "maxDirectionTrianglesSpread": 100000,
    "maxDirectionFrameTimeP95SpreadMs": 4.0
  }
}
```

Every required view supplies calls, triangles, FPS, and P50/P95 frame time.
Direction spread is `max - min` over `angleConsistency.viewIds`. Capture the
same warm-up, sample count, viewport, and throttling policy for standalone and
host snapshots.

### Error counts

`errors.maxConsoleErrors` and `errors.maxNetworkErrors` are non-negative
integers. Snapshots expose `errors.console` and `errors.network`. Count only
errors observed during the declared capture window, and document filtering in
the host probe rather than silently changing the JSON after capture.

## Snapshot document

Required envelope:

```json
{
  "schemaVersion": "1.0",
  "kind": "render-runtime-snapshot",
  "snapshotId": "repolis-host",
  "role": "host",
  "asset": {
    "assetId": "repolis-tree",
    "profileId": "repolis-living-archive",
    "source": {
      "path": "examples/repolis-tree/object-sculpt-spec.json",
      "sha256": "<64 hexadecimal characters>"
    },
    "factory": {
      "path": "examples/repolis-hero/repolis-output/createRepolisHero.js",
      "sha256": "<64 hexadecimal characters>"
    }
  },
  "renderer": {},
  "renderTargets": [],
  "selectiveRendering": {
    "layers": [],
    "lights": []
  },
  "views": [],
  "errors": {
    "console": 0,
    "network": 0
  }
}
```

The standalone positional input must have role `standalone`; the host input
must have role `host`. Missing diagnostic sections/fields produce report
checks with status `missing`. Present values with invalid types are exit-2
input errors. In particular, JSON booleans are never accepted as numbers.

Each view has:

```json
{
  "id": "front",
  "cameraId": "repolis-front",
  "blackFrame": false,
  "clipped": false,
  "coverage": 0.43,
  "luminance": {
    "p50": 0.37,
    "p90": 0.75
  },
  "semantics": [
    {
      "id": "hero-emissive",
      "visible": true,
      "coverage": 0.065,
      "luminance": {
        "p50": 0.48,
        "p90": 0.73
      }
    }
  ],
  "performance": {
    "calls": 150,
    "triangles": 760000,
    "fps": 54.0,
    "frameTimeP50Ms": 16.0,
    "frameTimeP95Ms": 21.5
  }
}
```

## Browser probe guidance

The committed
[`browser-snapshot-helper.js`](../../../examples/render-integration-contract/browser-snapshot-helper.js)
is dependency-free. It accepts normalized, app-owned measurements instead of
coupling to one framework:

Three.js 0.180 runtime color-space values are canonicalized before snapshot
serialization:

| Runtime value | Snapshot value |
| --- | --- |
| `srgb` | `SRGBColorSpace` |
| `srgb-linear` | `LinearSRGBColorSpace` |
| empty string (`THREE.NoColorSpace`) | `NoColorSpace` |

```js
import {
  captureViewPerformance,
  createRenderIntegrationSnapshot,
  snapshotRenderTarget,
} from './browser-snapshot-helper.js';

const namedViewDiagnostics = [];
for (const view of requiredViews) {
  setCameraView(view.id);
  renderSettledFrame();
  const frameTimesMs = await captureFrameTimes();
  namedViewDiagnostics.push({
    ...measureViewAndSemantics(view),
    id: view.id,
    cameraId: view.cameraId,
    performance: captureViewPerformance(renderer, frameTimesMs),
  });
}

window.__RENDER_INTEGRATION_SNAPSHOT__ = createRenderIntegrationSnapshot({
  role: 'host',
  snapshotId: 'repolis-host',
  asset: {
    assetId: 'repolis-tree',
    profileId: 'repolis-living-archive',
    source: { path: sourcePath, sha256: sourceSha256 },
    factory: { path: factoryPath, sha256: factorySha256 },
  },
  renderer,
  toneMapping: 'ACESFilmicToneMapping',
  outputPassCount: composer.passes.filter(
    (pass) => pass.constructor.name === 'OutputPass',
  ).length,
  renderTargets: [
    snapshotRenderTarget({
      id: 'hero-bloom',
      type: 'HalfFloatType',
      colorSpace: bloomTarget.texture.colorSpace,
      depthBuffer: bloomTarget.depthBuffer,
      scale: bloomScale,
      width: bloomTarget.width,
      height: bloomTarget.height,
    }),
  ],
  layers: layerDiagnostics,
  lights: lightDiagnostics,
  views: namedViewDiagnostics,
  consoleErrors,
  networkErrors,
});
```

Export the hook with the browser tooling already present in the host project,
for example:

```js
JSON.stringify(window.__RENDER_INTEGRATION_SNAPSHOT__, null, 2);
```

The helper expects each named view to provide semantic diagnostics and raw frame
time samples through its own `performance` capture. Capture one view at a time
after renderer state, camera matrices, layer masks, and render targets settle.
`captureViewPerformance()` copies that view's current
`renderer.info.render.calls` and `triangles`; the helper rejects a view without
its own capture instead of reusing the renderer's latest counters. Frame
samples must already be JavaScript numbers that are finite and greater than
zero. Nulls, booleans, strings, zero, and negative values are rejected without
coercion.

Do not install a browser runtime just for this gate. Use the application's
existing debug hooks or the GitHub Copilot in-app Browser. The contract consumes
the resulting JSON files.

## Report and ordering

Reports use:

- `schemaVersion: "1.0"`
- `kind: "render-integration-contract-report"`
- input display paths and file SHA-256 hashes
- normalized contract/asset/profile identity
- explicit policy and authority declarations
- stable checks
- summary keys ordered `total`, `missing`, `stale`, `passing`, `failing`

Each input is read once as bytes. Its report SHA-256 and parsed JSON are derived
from that same immutable buffer, so the digest always binds the exact bytes
that produced the checks.

Check status:

- `missing`: required entity or telemetry absent
- `stale`: source/factory path or SHA differs
- `passing`: declared policy satisfied
- `failing`: present telemetry violates policy

Fixed check family order:

1. bindings
2. renderer
3. render targets
4. selective layers
5. selective lights
6. views/cameras
7. semantic systems
8. angle consistency
9. town exposure
10. performance
11. console/network errors

Important stable codes include:

| Code | Meaning |
| --- | --- |
| `source-binding`, `factory-binding` | Missing or stale immutable binding |
| `tone-mapping`, `output-color-space` | Renderer output policy drift |
| `exposure-baseline`, `exposure-delta` | Exposure mismatch |
| `tone-mapping-count` | Repeated or missing output transform |
| `pixel-ratio` | DPR exceeds the contract |
| `render-target-*` | Target type/color/depth/scale/pixel violation |
| `layer-*`, `light-*` | Selective ownership or membership violation |
| `town-light-spill` | Hero light affects town beyond policy |
| `camera-binding`, `view-coverage` | Required camera/view mismatch |
| `semantic-*` | Required system visibility/coverage/luminance mismatch |
| `black-frame`, `view-clipping` | Explicit banned frame state |
| `angle-coverage-consistency` | Minimum coverage collapsed at one angle |
| `angle-luminance-spread` | P90 luminance varies too much by angle |
| `town-exposure-invariance` | Host town luminance drifted from standalone |
| `draw-calls`, `triangles`, `fps`, `frame-time-*` | Per-view budget violation |
| `camera-direction-*` | Direction-dependent cost spread violation |
| `console-errors`, `network-errors` | Runtime error budget violation |

## Determinism and schema evolution

The report never copies arbitrary input maps. Collections are sorted by ID,
computed values use fixed precision, and paths are normalized independently of
the current working directory. Repeated runs with the same absolute input files
must produce byte-identical JSON.

Unknown additive fields in a v1 document are allowed and ignored. Unsupported
schema versions are rejected. A future schema must not reinterpret a v1 field;
new behavior requires an additive field or a new explicit schema version.
Integer values must stay within JavaScript's interoperable JSON-safe range
`[-9007199254740991, 9007199254740991]`.

The full passing demonstration and golden report live in
`examples/render-integration-contract/`. Its runtime metrics are labeled
deterministic demonstration data and are not claims of live browser
measurement.
