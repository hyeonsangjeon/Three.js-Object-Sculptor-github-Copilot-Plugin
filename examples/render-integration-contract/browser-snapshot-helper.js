// Demonstration helper only: callers supply measured semantic and frame data.
// This module does not inspect pixels, judge visual quality, or grant AI approval.

const COLOR_SPACE_NAMES = new Map([
  ['', 'NoColorSpace'],
  ['srgb', 'SRGBColorSpace'],
  ['srgb-linear', 'LinearSRGBColorSpace'],
  ['NoColorSpace', 'NoColorSpace'],
  ['SRGBColorSpace', 'SRGBColorSpace'],
  ['LinearSRGBColorSpace', 'LinearSRGBColorSpace'],
]);

export function canonicalColorSpace(value) {
  if (typeof value !== 'string') {
    throw new TypeError('colorSpace must be a string.');
  }
  return COLOR_SPACE_NAMES.get(value) ?? value;
}

function finitePositiveSamples(values, label) {
  if (!Array.isArray(values) || values.length === 0) {
    throw new TypeError(`${label} must contain positive finite number samples.`);
  }
  if (
    values.some(
      (value) => (
        typeof value !== 'number'
        || !Number.isFinite(value)
        || value <= 0
      ),
    )
  ) {
    throw new TypeError(`${label} must contain only positive finite numbers.`);
  }
  return [...values].sort((a, b) => a - b);
}

function nonNegativeInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new TypeError(`${label} must be a non-negative safe integer.`);
  }
  return value;
}

function performanceSnapshot(performance, label) {
  if (
    performance === null
    || typeof performance !== 'object'
    || Array.isArray(performance)
  ) {
    throw new TypeError(`${label} must be captured for this view.`);
  }
  return {
    calls: nonNegativeInteger(performance.calls, `${label}.calls`),
    triangles: nonNegativeInteger(performance.triangles, `${label}.triangles`),
    ...summarizeFrameTimes(performance.frameTimesMs, `${label}.frameTimesMs`),
  };
}

function percentile(samples, fraction) {
  const index = Math.min(
    samples.length - 1,
    Math.max(0, Math.ceil(samples.length * fraction) - 1),
  );
  return samples[index];
}

export function summarizeFrameTimes(frameTimesMs, label = 'frameTimesMs') {
  const samples = finitePositiveSamples(frameTimesMs, label);
  const mean = samples.reduce((sum, value) => sum + value, 0) / samples.length;
  return {
    fps: 1000 / mean,
    frameTimeP50Ms: percentile(samples, 0.5),
    frameTimeP95Ms: percentile(samples, 0.95),
  };
}

export function captureViewPerformance(renderer, frameTimesMs) {
  const renderInfo = renderer?.info?.render;
  if (renderInfo === null || typeof renderInfo !== 'object') {
    throw new TypeError('renderer.info.render is required for view capture.');
  }
  return {
    calls: nonNegativeInteger(renderInfo.calls, 'renderer.info.render.calls'),
    triangles: nonNegativeInteger(
      renderInfo.triangles,
      'renderer.info.render.triangles',
    ),
    frameTimesMs: finitePositiveSamples(frameTimesMs, 'frameTimesMs'),
  };
}

export function snapshotRenderTarget({
  id,
  type,
  colorSpace,
  depthBuffer,
  scale,
  width,
  height,
}) {
  return {
    id,
    type,
    colorSpace: canonicalColorSpace(colorSpace),
    depthBuffer,
    scale,
    width,
    height,
    pixelCount: width * height,
  };
}

export function createRenderIntegrationSnapshot({
  role,
  snapshotId,
  asset,
  renderer,
  toneMapping,
  outputPassCount,
  renderTargets = [],
  layers = [],
  lights = [],
  views = [],
  consoleErrors = 0,
  networkErrors = 0,
}) {
  if (role !== 'standalone' && role !== 'host') {
    throw new RangeError('role must be "standalone" or "host".');
  }
  return {
    schemaVersion: '1.0',
    kind: 'render-runtime-snapshot',
    snapshotId,
    role,
    asset,
    renderer: {
      toneMapping,
      outputColorSpace: canonicalColorSpace(renderer.outputColorSpace),
      exposure: renderer.toneMappingExposure,
      outputPassCount,
      pixelRatio: renderer.getPixelRatio(),
    },
    renderTargets: renderTargets.map((target) => ({
      ...target,
      colorSpace: canonicalColorSpace(target.colorSpace),
    })),
    selectiveRendering: {
      layers,
      lights,
    },
    views: views.map((view, index) => ({
      id: view.id,
      cameraId: view.cameraId,
      blackFrame: view.blackFrame,
      clipped: view.clipped,
      coverage: view.coverage,
      luminance: view.luminance,
      semantics: view.semantics,
      performance: performanceSnapshot(
        view.performance,
        `views[${index}].performance`,
      ),
    })),
    errors: {
      console: consoleErrors,
      network: networkErrors,
    },
  };
}
