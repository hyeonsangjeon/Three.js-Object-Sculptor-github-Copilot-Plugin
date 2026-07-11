import * as THREE from 'three';

export type ProceduralModelOptions = {
  wireframe?: boolean;
  castShadow?: boolean;
  receiveShadow?: boolean;
  textureSize?: number;
  textureAnisotropy?: number;
  qualityPriority?: 'reference-fidelity' | 'balanced';
};

export type ProceduralModelRuntime = {
  nodes: Record<string, THREE.Object3D>;
  meshes: Record<string, THREE.Mesh>;
  sockets: Record<string, THREE.Object3D>;
  colliders: Record<string, unknown>;
  destructionGroups: Record<string, THREE.Object3D[]>;
};

type SculptMaterialSpec = Record<string, any>;

function hashString(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function readLayerNumber(value: unknown, keys: string[], fallback: number): number {
  if (typeof value === 'number') return value;
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    for (const key of keys) {
      if (typeof record[key] === 'number') return record[key] as number;
    }
  }
  return fallback;
}

function hexToRgb(hex: string): [number, number, number] {
  const normalized = /^#[0-9a-f]{3}$/i.test(hex)
    ? '#' + hex.slice(1).split('').map((part) => part + part).join('')
    : hex;
  const value = /^#[0-9a-f]{6}$/i.test(normalized) ? Number.parseInt(normalized.slice(1), 16) : 0x8a7a5f;
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function materialPalette(spec: SculptMaterialSpec): string[] {
  const palette = spec.colorVariation?.palette;
  if (Array.isArray(palette) && palette.length > 0) return palette.filter((value) => typeof value === 'string');
  const secondary = spec.albedo?.secondary;
  const colors = [spec.baseColor ?? spec.color ?? spec.albedo?.dominant, ...(Array.isArray(secondary) ? secondary : [])];
  return colors.filter((value): value is string => typeof value === 'string' && value.startsWith('#'));
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function smoothCurve(value: number): number {
  return value * value * (3 - 2 * value);
}

function periodicHash(x: number, y: number, seed: number, periodX: number, periodY: number): number {
  const wrappedX = ((x % periodX) + periodX) % periodX;
  const wrappedY = ((y % periodY) + periodY) % periodY;
  let value = Math.imul(wrappedX + seed * 17, 374761393) ^ Math.imul(wrappedY + seed * 31, 668265263);
  value = Math.imul(value ^ (value >>> 13), 1274126177);
  return ((value ^ (value >>> 16)) >>> 0) / 4294967295;
}

function periodicValueNoise(u: number, v: number, seed: number, periodX: number, periodY: number): number {
  const x = u * periodX;
  const y = v * periodY;
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const tx = smoothCurve(x - x0);
  const ty = smoothCurve(y - y0);
  const a = periodicHash(x0, y0, seed, periodX, periodY);
  const b = periodicHash(x0 + 1, y0, seed, periodX, periodY);
  const c = periodicHash(x0, y0 + 1, seed, periodX, periodY);
  const d = periodicHash(x0 + 1, y0 + 1, seed, periodX, periodY);
  return THREE.MathUtils.lerp(THREE.MathUtils.lerp(a, b, tx), THREE.MathUtils.lerp(c, d, tx), ty);
}

type SurfaceBand = {
  frequency: number;
  amplitude: number;
  stretchX: number;
  stretchY: number;
  ridge: boolean;
};

function surfaceBands(spec: SculptMaterialSpec): SurfaceBand[] {
  const source = Array.isArray(spec.surfaceFrequencyBands) ? spec.surfaceFrequencyBands : [];
  const parsed = source.flatMap((item: unknown) => {
    if (!item || typeof item !== 'object') return [];
    const band = item as Record<string, unknown>;
    const frequency = typeof band.frequency === 'number' ? band.frequency : 0;
    const amplitude = typeof band.amplitude === 'number' ? band.amplitude : 0;
    if (frequency <= 0 || amplitude <= 0) return [];
    const stretch = Array.isArray(band.stretch) ? band.stretch : [1, 1];
    const description = `${String(band.pattern ?? '')} ${String(band.role ?? '')}`.toLowerCase();
    return [{
      frequency,
      amplitude,
      stretchX: typeof stretch[0] === 'number' ? Math.max(0.1, stretch[0]) : 1,
      stretchY: typeof stretch[1] === 'number' ? Math.max(0.1, stretch[1]) : 1,
      ridge: /(ridge|groove|grain|fiber|striated|crack)/.test(description),
    }];
  });
  return parsed.length > 0 ? parsed : [
    { frequency: 2, amplitude: 0.42, stretchX: 1, stretchY: 1, ridge: false },
    { frequency: 12, amplitude: 0.22, stretchX: 1, stretchY: 1, ridge: false },
    { frequency: 56, amplitude: 0.08, stretchX: 1, stretchY: 1, ridge: false },
  ];
}

function sampleSurface(u: number, v: number, bands: SurfaceBand[], seed: number): number {
  let value = 0;
  let weight = 0;
  for (let index = 0; index < bands.length; index += 1) {
    const band = bands[index];
    const periodX = Math.max(1, Math.round(band.frequency * band.stretchX));
    const periodY = Math.max(1, Math.round(band.frequency * band.stretchY));
    let sample = periodicValueNoise(u, v, seed + index * 1013, periodX, periodY);
    if (band.ridge) sample = 1 - Math.abs(sample * 2 - 1);
    value += sample * band.amplitude;
    weight += band.amplitude;
  }
  return weight > 0 ? clamp01(value / weight) : 0.5;
}

function mixPalette(colors: [number, number, number][], value: number): [number, number, number] {
  if (colors.length === 1) return colors[0];
  const scaled = clamp01(value) * (colors.length - 1);
  const index = Math.min(colors.length - 2, Math.floor(scaled));
  const mix = scaled - index;
  const a = colors[index];
  const b = colors[index + 1];
  return [
    Math.round(THREE.MathUtils.lerp(a[0], b[0], mix)),
    Math.round(THREE.MathUtils.lerp(a[1], b[1], mix)),
    Math.round(THREE.MathUtils.lerp(a[2], b[2], mix)),
  ];
}

function writePixel(data: Uint8ClampedArray, offset: number, red: number, green: number, blue: number): void {
  data[offset] = Math.max(0, Math.min(255, Math.round(red)));
  data[offset + 1] = Math.max(0, Math.min(255, Math.round(green)));
  data[offset + 2] = Math.max(0, Math.min(255, Math.round(blue)));
  data[offset + 3] = 255;
}

function makeCanvas(size: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  return canvas;
}

function createMapTexture(
  canvas: HTMLCanvasElement,
  colorSpace: THREE.ColorSpace,
  spec: SculptMaterialSpec,
  options: ProceduralModelOptions,
): THREE.CanvasTexture {
  const texture = new THREE.CanvasTexture(canvas);
  const projection = spec.textureProjection && typeof spec.textureProjection === 'object' ? spec.textureProjection : {};
  const repeat = Array.isArray(projection.repeat) ? projection.repeat : [2, 2];
  texture.colorSpace = colorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(
    typeof repeat[0] === 'number' ? repeat[0] : 2,
    typeof repeat[1] === 'number' ? repeat[1] : 2,
  );
  texture.anisotropy = Math.max(1, Math.round(options.textureAnisotropy ?? projection.anisotropy ?? 8));
  texture.needsUpdate = true;
  return texture;
}

type ProceduralTextureSet = {
  albedo: THREE.Texture;
  roughness: THREE.Texture;
  height: THREE.Texture;
  normal: THREE.Texture;
  ao: THREE.Texture;
  source: 'reference-pixel-extraction' | 'procedural';
};

function referenceMapUrl(spec: SculptMaterialSpec, channel: string): string | null {
  const reference = spec.referencePbr;
  if (!reference || typeof reference !== 'object') return null;
  if (reference.usable === false) return null;
  const confidence = typeof reference.confidence === 'number'
    ? reference.confidence
    : (typeof reference.estimatedFidelity === 'number' ? reference.estimatedFidelity : 0);
  const threshold = typeof reference.targetThreshold === 'number' ? reference.targetThreshold : 0.7;
  if (confidence < threshold) return null;
  const maps = reference.maps;
  if (!maps || typeof maps !== 'object') return null;
  const map = (maps as Record<string, unknown>)[channel];
  if (!map || typeof map !== 'object') return null;
  const record = map as Record<string, unknown>;
  const url = typeof record.url === 'string' && record.url.trim() ? record.url : record.path;
  return typeof url === 'string' && url.trim() ? url : null;
}

function createLoadedMapTexture(
  url: string,
  colorSpace: THREE.ColorSpace,
  spec: SculptMaterialSpec,
  options: ProceduralModelOptions,
): THREE.Texture {
  const texture = new THREE.TextureLoader().load(url);
  const projection = spec.textureProjection && typeof spec.textureProjection === 'object' ? spec.textureProjection : {};
  const repeat = Array.isArray(projection.repeat) ? projection.repeat : [1, 1];
  texture.colorSpace = colorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(
    typeof repeat[0] === 'number' ? repeat[0] : 1,
    typeof repeat[1] === 'number' ? repeat[1] : 1,
  );
  texture.anisotropy = Math.max(1, Math.round(options.textureAnisotropy ?? projection.anisotropy ?? 8));
  texture.needsUpdate = true;
  return texture;
}

function makeReferenceTextureSet(spec: SculptMaterialSpec, options: ProceduralModelOptions): ProceduralTextureSet | null {
  const albedo = referenceMapUrl(spec, 'albedo');
  const roughness = referenceMapUrl(spec, 'roughness');
  const height = referenceMapUrl(spec, 'height');
  const normal = referenceMapUrl(spec, 'normal');
  const ao = referenceMapUrl(spec, 'ao');
  if (!albedo || !roughness || !height || !normal || !ao) return null;
  return {
    albedo: createLoadedMapTexture(albedo, THREE.SRGBColorSpace, spec, options),
    roughness: createLoadedMapTexture(roughness, THREE.NoColorSpace, spec, options),
    height: createLoadedMapTexture(height, THREE.NoColorSpace, spec, options),
    normal: createLoadedMapTexture(normal, THREE.NoColorSpace, spec, options),
    ao: createLoadedMapTexture(ao, THREE.NoColorSpace, spec, options),
    source: 'reference-pixel-extraction',
  };
}

function makeProceduralTextureSet(
  id: string,
  spec: SculptMaterialSpec,
  options: ProceduralModelOptions,
): ProceduralTextureSet | null {
  if (typeof document === 'undefined') return null;
  const qualityFirst = (options.qualityPriority ?? 'reference-fidelity') === 'reference-fidelity';
  const requested = options.textureSize ?? spec.textureResolution;
  const requestedSize = typeof requested === 'number' && Number.isFinite(requested)
    ? requested
    : (qualityFirst ? 1024 : 512);
  const size = Math.max(256, Math.min(2048, 2 ** Math.round(Math.log2(requestedSize))));
  const canvases = {
    albedo: makeCanvas(size),
    roughness: makeCanvas(size),
    height: makeCanvas(size),
    normal: makeCanvas(size),
    ao: makeCanvas(size),
  };
  const contexts = {
    albedo: canvases.albedo.getContext('2d'),
    roughness: canvases.roughness.getContext('2d'),
    height: canvases.height.getContext('2d'),
    normal: canvases.normal.getContext('2d'),
    ao: canvases.ao.getContext('2d'),
  };
  if (!contexts.albedo || !contexts.roughness || !contexts.height || !contexts.normal || !contexts.ao) return null;
  const images = {
    albedo: contexts.albedo.createImageData(size, size),
    roughness: contexts.roughness.createImageData(size, size),
    height: contexts.height.createImageData(size, size),
    normal: contexts.normal.createImageData(size, size),
    ao: contexts.ao.createImageData(size, size),
  };
  const seed = hashString(id);
  const bands = surfaceBands(spec);
  const heightField = new Float32Array(size * size);
  const roughnessField = new Float32Array(size * size);
  const palette = materialPalette(spec);
  const fallback = typeof spec.baseColor === 'string' ? spec.baseColor : '#8A7A5F';
  const colors = (palette.length >= 2 ? palette : [fallback, '#6E614B', '#A08F70']).map(hexToRgb);
  const baseRoughness = clamp01(readLayerNumber(spec.roughness, ['base'], 0.76));
  const roughnessVariation = clamp01(readLayerNumber(spec.roughness, ['variation'], 0.18));
  const colorAmplitude = clamp01(readLayerNumber(spec.colorVariation, ['amplitude', 'variation'], 0.18));
  const heightCorrelation = clamp01(readLayerNumber(spec.colorVariation, ['heightCorrelation'], 0.3));
  for (let y = 0; y < size; y += 1) {
    const v = y / size;
    for (let x = 0; x < size; x += 1) {
      const u = x / size;
      const index = y * size + x;
      const height = sampleSurface(u, v, bands, seed + 101);
      const roughNoise = sampleSurface(u, v, bands, seed + 7001);
      const colorNoise = sampleSurface(u, v, bands, seed + 15013);
      heightField[index] = height;
      roughnessField[index] = clamp01(baseRoughness + (roughNoise - 0.5) * roughnessVariation * 2);
      const paletteValue = clamp01(
        0.5 + (colorNoise - 0.5) * colorAmplitude * 2 + (height - 0.5) * heightCorrelation
      );
      const color = mixPalette(colors, paletteValue);
      writePixel(images.albedo.data, index * 4, color[0], color[1], color[2]);
    }
  }
  const normalStrength = Math.max(0.05, readLayerNumber(spec.normal, ['strength', 'amplitude'], 0.35));
  const aoStrength = clamp01(readLayerNumber(spec.ambientOcclusion, ['cavityStrength', 'strength'], 0.35));
  for (let y = 0; y < size; y += 1) {
    const up = ((y - 1 + size) % size) * size;
    const down = ((y + 1) % size) * size;
    for (let x = 0; x < size; x += 1) {
      const left = (x - 1 + size) % size;
      const right = (x + 1) % size;
      const index = y * size + x;
      const center = heightField[index];
      const dx = (heightField[y * size + right] - heightField[y * size + left]) * normalStrength * 6;
      const dy = (heightField[down + x] - heightField[up + x]) * normalStrength * 6;
      const inverseLength = 1 / Math.sqrt(dx * dx + dy * dy + 1);
      const normalX = -dx * inverseLength;
      const normalY = -dy * inverseLength;
      const normalZ = inverseLength;
      const neighborAverage = (
        heightField[y * size + left] + heightField[y * size + right]
        + heightField[up + x] + heightField[down + x]
      ) * 0.25;
      const cavity = Math.max(0, neighborAverage - center);
      const ao = clamp01(1 - aoStrength * (cavity * 12 + (1 - center) * 0.16));
      const offset = index * 4;
      const heightByte = center * 255;
      const roughnessByte = roughnessField[index] * 255;
      writePixel(images.height.data, offset, heightByte, heightByte, heightByte);
      writePixel(images.roughness.data, offset, roughnessByte, roughnessByte, roughnessByte);
      writePixel(
        images.normal.data, offset,
        (normalX * 0.5 + 0.5) * 255,
        (normalY * 0.5 + 0.5) * 255,
        (normalZ * 0.5 + 0.5) * 255,
      );
      writePixel(images.ao.data, offset, ao * 255, ao * 255, ao * 255);
    }
  }
  contexts.albedo.putImageData(images.albedo, 0, 0);
  contexts.roughness.putImageData(images.roughness, 0, 0);
  contexts.height.putImageData(images.height, 0, 0);
  contexts.normal.putImageData(images.normal, 0, 0);
  contexts.ao.putImageData(images.ao, 0, 0);
  return {
    albedo: createMapTexture(canvases.albedo, THREE.SRGBColorSpace, spec, options),
    roughness: createMapTexture(canvases.roughness, THREE.NoColorSpace, spec, options),
    height: createMapTexture(canvases.height, THREE.NoColorSpace, spec, options),
    normal: createMapTexture(canvases.normal, THREE.NoColorSpace, spec, options),
    ao: createMapTexture(canvases.ao, THREE.NoColorSpace, spec, options),
    source: 'procedural',
  };
}

function createSculptMaterial(id: string, spec: SculptMaterialSpec, options: ProceduralModelOptions): THREE.MeshPhysicalMaterial {
  const textures = makeReferenceTextureSet(spec, options) ?? makeProceduralTextureSet(id, spec, options);
  const emissiveColor = spec.emissive?.color;
  const material = new THREE.MeshPhysicalMaterial({
    color: textures ? 0xffffff : new THREE.Color(typeof spec.baseColor === 'string' ? spec.baseColor : '#8A7A5F'),
    emissive: new THREE.Color(typeof emissiveColor === 'string' ? emissiveColor : '#000000'),
    emissiveIntensity: Math.max(0, readLayerNumber(spec.emissive, ['intensity', 'base'], 0)),
    roughness: textures ? 1 : clamp01(readLayerNumber(spec.roughness, ['base'], 0.76)),
    metalness: clamp01(readLayerNumber(spec.metalness, ['base'], 0.0)),
    clearcoat: clamp01(readLayerNumber(spec.clearcoat, ['base', 'amount'], 0)),
    clearcoatRoughness: clamp01(readLayerNumber(spec.clearcoatRoughness, ['base'], 0.25)),
    transmission: clamp01(readLayerNumber(spec.transmission, ['base', 'amount'], 0)),
    opacity: clamp01(readLayerNumber(spec.opacity, ['base'], 1)),
    transparent: readLayerNumber(spec.transmission, ['base', 'amount'], 0) > 0 || readLayerNumber(spec.opacity, ['base'], 1) < 1,
    alphaTest: Math.max(0, readLayerNumber(spec.alpha, ['cutoff', 'alphaTest'], 0)),
    wireframe: options.wireframe ?? false,
    side: spec.doubleSided === true ? THREE.DoubleSide : THREE.FrontSide,
  });
  if (textures) {
    material.map = textures.albedo;
    material.roughnessMap = textures.roughness;
    material.normalMap = textures.normal;
    material.normalScale.setScalar(Math.max(0.05, readLayerNumber(spec.normal, ['strength', 'amplitude'], 0.35)));
    material.aoMap = textures.ao;
    material.aoMap.channel = 0;
    material.aoMapIntensity = readLayerNumber(spec.ambientOcclusion, ['cavityStrength', 'strength'], 0.35);
    const bumpScale = Math.max(0, readLayerNumber(spec.bump, ['amplitude', 'strength'], 0));
    if (bumpScale > 0) {
      material.bumpMap = textures.height;
      material.bumpScale = bumpScale;
    }
    const displacementScale = Math.max(0, readLayerNumber(spec.displacement, ['amplitude', 'strength'], 0));
    if (displacementScale > 0) {
      material.displacementMap = textures.height;
      material.displacementScale = displacementScale;
      material.displacementBias = -displacementScale * 0.5;
    }
  }
  material.envMapIntensity = readLayerNumber(spec, ['envMapIntensity'], 0.8);
  material.userData.sculptMaterial = spec;
  material.userData.proceduralMapsIndependent = true;
  material.userData.pbrTextureSource = textures?.source ?? 'flat-fallback';
  material.userData.referencePbr = spec.referencePbr ?? null;
  material.needsUpdate = true;
  return material;
}

type AttachmentEndpoint = {
  start: THREE.Vector3;
  midpoint: THREE.Vector3;
  quaternion: THREE.Quaternion;
  length: number;
  baseRadius: number;
  endRadius: number;
};

function readVector3(value: unknown, fallback: [number, number, number]): THREE.Vector3 {
  if (Array.isArray(value) && value.length === 3 && value.every((item) => typeof item === 'number')) {
    return new THREE.Vector3(value[0], value[1], value[2]);
  }
  return new THREE.Vector3(fallback[0], fallback[1], fallback[2]);
}

function readNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function makeAttachmentEndpoint(attachment: unknown): AttachmentEndpoint | null {
  if (!attachment || typeof attachment !== 'object') return null;
  const record = attachment as Record<string, unknown>;
  const start = readVector3(record.localStart, [0, 0, 0]);
  const end = readVector3(record.localEnd, [0, 1, 0]);
  const delta = end.clone().sub(start);
  const length = delta.length();
  if (length <= 0.0001) return null;
  const direction = delta.clone().normalize();
  const quaternion = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction);
  const baseRadius = Math.max(0.005, readNumber(record.baseRadius, 0.06));
  const endRadius = Math.max(0.003, readNumber(record.endRadius, baseRadius * 0.55));
  return {
    start,
    midpoint: delta.multiplyScalar(0.5),
    quaternion,
    length,
    baseRadius,
    endRadius,
  };
}

// Generated from ObjectSculptSpec target: Repolis Tree
// Sculpt build pass: blockout
// This factory is intentionally pass-gated. Finish browser screenshot review before unlocking deeper passes.
export function createRepolisTreeModel(options: ProceduralModelOptions = {}): THREE.Group {
  const root = new THREE.Group();
  root.name = "Repolis Tree";

  const materialMap: Record<string, THREE.Material> = {};
  materialMap["bark"] = createSculptMaterial(
    "bark",
    {"id": "bark", "name": "Warm carved bark", "qualityTier": "hero", "type": "physical", "shaderModel": "MeshPhysicalMaterial", "baseColor": "#4A2B18", "color": "#4A2B18", "albedo": {"dominant": "#4A2B18", "secondary": ["#2B170F", "#6F4324", "#9A6333"], "samplingNotes": "Preserve warm brown midtones; do not sample the darkest baked shadows as base albedo."}, "colorVariation": {"palette": ["#2B170F", "#4A2B18", "#6F4324", "#9A6333"], "pattern": "vertical bark plates and warm ridge tops", "amplitude": 0.24, "heightCorrelation": 0.48}, "textureResolution": 2048, "textureProjection": {"mode": "cylindrical", "repeat": [2.0, 5.0], "anisotropy": 8, "texelDensityIntent": "0.25 world-unit bark plates remain consistent across trunk and branch taper."}, "surfaceFrequencyBands": [{"id": "macro", "frequency": 1.8, "amplitude": 0.34, "role": "broad trunk value and root-flare breakup"}, {"id": "meso", "frequency": 14.0, "amplitude": 0.2, "role": "longitudinal plates and carved channels"}, {"id": "micro", "frequency": 72.0, "amplitude": 0.055, "role": "fine pore and highlight breakup"}], "roughness": {"base": 0.68, "variation": 0.16, "map": "independent-bark-roughness-field", "localResponse": "rough cavities, smoother warm ridge tops, slightly polished energy-channel edges"}, "metalness": {"base": 0.0, "variation": 0.0}, "normal": {"pattern": "independent vertical bark height field", "strength": 0.58, "scale": 28.0, "space": "tangent"}, "bump": {"pattern": "fine bark pores", "amplitude": 0.045, "scale": 64.0}, "displacement": {"pattern": "low-frequency root and plate relief", "amplitude": 0.06, "scale": 4.0, "silhouetteAffects": true}, "ambientOcclusion": {"cavityStrength": 0.42, "contactShadowBias": 0.5, "notes": "Concentrate AO inside branch sockets, root contacts, and carved grooves."}, "wear": {"edgeWear": 0.1, "scratches": ["sparse branch-aligned shallow marks"], "chips": []}, "dirt": {"amount": 0.12, "cavityBias": 0.7, "color": "#1B100B"}, "emissive": {"color": "#6B2A0A", "intensity": 0.14}, "clearcoat": {"base": 0.04}, "opacity": {"base": 1.0}, "localOverrides": [{"id": "root-warmth", "region": "lowest 1.5 units", "changes": "raise albedo warmth and lower roughness by 0.08 near gold core", "strength": 0.45, "evidenceRefs": ["root-ground"]}, {"id": "fork-cavities", "region": "first and second branch forks", "changes": "deepen AO and darken albedo without reaching black", "strength": 0.5, "evidenceRefs": ["trunk-fork"]}], "shaderNotes": ["Keep bark and gold emission separate.", "Use warm fill light so shaded bark remains above near-black.", "Use triplanar fallback at branch forks to avoid cylindrical seams."], "notes": "The prior dark-tree failure is explicitly rejected: bark must remain readable under neutral lighting."},
    options
  );
  materialMap["gold-energy"] = createSculptMaterial(
    "gold-energy",
    {"id": "gold-energy", "name": "Golden code energy", "qualityTier": "hero", "type": "physical-emissive", "shaderModel": "MeshPhysicalMaterial plus bloom-ready emissive output", "baseColor": "#D27A20", "color": "#D27A20", "albedo": {"dominant": "#D27A20", "secondary": ["#FFB23F", "#FFD477", "#FFF2B0"], "samplingNotes": "Core approaches warm white; edges remain orange-gold."}, "colorVariation": {"palette": ["#D27A20", "#FFB23F", "#FFD477", "#FFF2B0"], "pattern": "root-to-tip pulse gradient", "amplitude": 0.32, "heightCorrelation": 0.2}, "textureResolution": 1024, "textureProjection": {"mode": "curve-distance", "repeat": [1.0, 6.0], "anisotropy": 8, "texelDensityIntent": "pulse spacing remains stable along each spline."}, "surfaceFrequencyBands": [{"id": "macro", "frequency": 1.0, "amplitude": 0.28, "role": "root-to-tip intensity envelope"}, {"id": "meso", "frequency": 8.0, "amplitude": 0.12, "role": "flow pulses and glyph grouping"}, {"id": "micro", "frequency": 48.0, "amplitude": 0.035, "role": "subtle edge scintillation"}], "roughness": {"base": 0.28, "variation": 0.08, "map": "independent-energy-roughness-field", "localResponse": "slightly smoother bright core"}, "metalness": {"base": 0.0, "variation": 0.0}, "normal": {"pattern": "very shallow independent flow ripples", "strength": 0.08, "scale": 20.0, "space": "tangent"}, "bump": {"pattern": "none", "amplitude": 0.0, "scale": 1.0}, "displacement": {"pattern": "none", "amplitude": 0.0, "scale": 1.0, "silhouetteAffects": false}, "ambientOcclusion": {"cavityStrength": 0.04, "contactShadowBias": 0.05, "notes": "Energy is self-luminous; avoid dirty AO."}, "wear": {"edgeWear": 0.0, "scratches": [], "chips": []}, "dirt": {"amount": 0.0, "cavityBias": 0.0, "color": "#5A2605"}, "emissive": {"color": "#FFD477", "intensity": 4.2}, "clearcoat": {"base": 0.18}, "opacity": {"base": 1.0}, "localOverrides": [{"id": "root-core", "region": "root energy origin", "changes": "raise emission to warm white and broaden halo", "strength": 0.9, "evidenceRefs": ["root-ground"]}, {"id": "tip-fade", "region": "outer branch tips", "changes": "reduce emission by 35 percent and narrow path width", "strength": 0.55, "evidenceRefs": ["upper-canopy"]}], "shaderNotes": ["Use additive bloom only after tone mapping is stable.", "Clamp bloom so branch and bark edges remain readable.", "Animate pulse in material state rather than changing geometry."], "notes": "Identity-defining effect material."},
    options
  );
  materialMap["amber-leaf"] = createSculptMaterial(
    "amber-leaf",
    {"id": "amber-leaf", "name": "Amber luminous leaves", "qualityTier": "hero", "type": "thin-translucent", "shaderModel": "MeshPhysicalMaterial with alpha cards or thin extruded leaves", "baseColor": "#F2A545", "color": "#F2A545", "albedo": {"dominant": "#F2A545", "secondary": ["#D87927", "#FFC867", "#FFF0B4"], "samplingNotes": "Warm amber dominates the crown with pale gold tips."}, "colorVariation": {"palette": ["#D87927", "#F2A545", "#FFC867", "#FFF0B4"], "pattern": "cluster and height-based hue variation", "amplitude": 0.28, "heightCorrelation": 0.18}, "textureResolution": 1024, "textureProjection": {"mode": "planar-per-leaf", "repeat": [1.0, 1.0], "anisotropy": 8, "texelDensityIntent": "one leaf texture per card with deterministic atlas rotation."}, "surfaceFrequencyBands": [{"id": "macro", "frequency": 1.4, "amplitude": 0.22, "role": "cluster-level brightness variation"}, {"id": "meso", "frequency": 10.0, "amplitude": 0.1, "role": "central vein and lobe variation"}, {"id": "micro", "frequency": 52.0, "amplitude": 0.025, "role": "subtle thin-surface highlight breakup"}], "roughness": {"base": 0.48, "variation": 0.14, "map": "independent-leaf-roughness-field", "localResponse": "smoother central vein and brighter thin edges"}, "metalness": {"base": 0.0, "variation": 0.0}, "normal": {"pattern": "central vein and shallow side veins", "strength": 0.24, "scale": 18.0, "space": "tangent"}, "bump": {"pattern": "leaf vein microrelief", "amplitude": 0.012, "scale": 32.0}, "displacement": {"pattern": "slight leaf curl", "amplitude": 0.018, "scale": 2.0, "silhouetteAffects": true}, "ambientOcclusion": {"cavityStrength": 0.12, "contactShadowBias": 0.18, "notes": "Cluster AO only; leaf faces remain luminous."}, "wear": {"edgeWear": 0.0, "scratches": [], "chips": []}, "dirt": {"amount": 0.0, "cavityBias": 0.0, "color": "#6E2B12"}, "emissive": {"color": "#FFC867", "intensity": 1.8}, "transmission": {"base": 0.08}, "opacity": {"base": 0.92}, "alpha": {"cutoff": 0.35}, "doubleSided": true, "localOverrides": [{"id": "pale-tip", "region": "upper and outer leaf tips", "changes": "shift toward pale gold and raise emission", "strength": 0.35, "evidenceRefs": ["upper-canopy"]}], "shaderNotes": ["Use deterministic instancing.", "Avoid one opaque canopy mesh.", "Limit overdraw with alpha cutoff and LOD."], "notes": "Approximately 75 percent of luminous foliage."},
    options
  );
  materialMap["cyan-leaf"] = createSculptMaterial(
    "cyan-leaf",
    {"id": "cyan-leaf", "name": "Cyan constellation leaves", "qualityTier": "hero", "type": "thin-emissive", "shaderModel": "MeshPhysicalMaterial with emissive thin cards and point-node companions", "baseColor": "#38CDE0", "color": "#38CDE0", "albedo": {"dominant": "#38CDE0", "secondary": ["#1A8FA8", "#5EF7FF", "#B6FFFF"], "samplingNotes": "Cyan remains a sparse accent rather than replacing amber."}, "colorVariation": {"palette": ["#1A8FA8", "#38CDE0", "#5EF7FF", "#B6FFFF"], "pattern": "constellation-group variation", "amplitude": 0.3, "heightCorrelation": 0.2}, "textureResolution": 1024, "textureProjection": {"mode": "planar-per-leaf", "repeat": [1.0, 1.0], "anisotropy": 8, "texelDensityIntent": "one leaf texture per card with deterministic atlas rotation."}, "surfaceFrequencyBands": [{"id": "macro", "frequency": 1.2, "amplitude": 0.2, "role": "constellation-group intensity"}, {"id": "meso", "frequency": 9.0, "amplitude": 0.09, "role": "leaf vein and node variation"}, {"id": "micro", "frequency": 48.0, "amplitude": 0.02, "role": "edge scintillation"}], "roughness": {"base": 0.38, "variation": 0.1, "map": "independent-cyan-leaf-roughness-field", "localResponse": "slightly smoother node-facing surfaces"}, "metalness": {"base": 0.0, "variation": 0.0}, "normal": {"pattern": "central vein", "strength": 0.18, "scale": 18.0, "space": "tangent"}, "bump": {"pattern": "fine vein", "amplitude": 0.008, "scale": 30.0}, "displacement": {"pattern": "slight leaf curl", "amplitude": 0.014, "scale": 2.0, "silhouetteAffects": true}, "ambientOcclusion": {"cavityStrength": 0.08, "contactShadowBias": 0.12, "notes": "Keep cyan accents bright and clean."}, "wear": {"edgeWear": 0.0, "scratches": [], "chips": []}, "dirt": {"amount": 0.0, "cavityBias": 0.0, "color": "#07333A"}, "emissive": {"color": "#5EF7FF", "intensity": 2.4}, "transmission": {"base": 0.1}, "opacity": {"base": 0.94}, "alpha": {"cutoff": 0.35}, "doubleSided": true, "localOverrides": [{"id": "constellation-node", "region": "selected cyan leaf clusters", "changes": "replace leaf card with brighter sphere node and thin connecting segment", "strength": 0.3, "evidenceRefs": ["left-canopy", "right-canopy"]}], "shaderNotes": ["Keep cyan coverage under one quarter of luminous foliage.", "Use a separate seed from amber leaves.", "Group nodes into semantic constellations rather than uniform random scatter."], "notes": "Sparse identity accent."},
    options
  );

  const nodes: Record<string, THREE.Object3D> = { root };
  const meshes: Record<string, THREE.Mesh> = {};
  const sockets: Record<string, THREE.Object3D> = {};
  const colliders: Record<string, unknown> = {};
  const destructionGroups: Record<string, THREE.Object3D[]> = {};

  const attachment_root_0 = null;
  const endpoint_root_0 = makeAttachmentEndpoint(attachment_root_0);
  const node_root_0 = new THREE.Group();
  node_root_0.name = "Repolis trunk core__pivot";
  if (endpoint_root_0) {
    node_root_0.position.copy(endpoint_root_0.start);
    node_root_0.rotation.set(0, 0, 0);
    node_root_0.scale.set(1, 1, 1);
  } else {
    node_root_0.position.set(0.0, 3.6, 0.0);
    node_root_0.rotation.set(0.0, 0.0, 0.0);
    node_root_0.scale.set(1, 1, 1);
  }
  node_root_0.userData.sculptComponent = {"id": "root", "name": "Repolis trunk core", "level": "macro", "role": "body", "importance": 1.0, "confidence": 0.9, "primitive": "cylinder", "geometryDescriptor": {"topologyIntent": "tapered trunk with enough radial and height segments for root flare and carved energy channels", "edgeTreatment": {"type": "organic bevel", "bevelRadius": 0.08, "segments": 3}, "deformationStack": ["lower flare", "subtle rightward bend", "asymmetric longitudinal ridges"], "uvStrategy": "cylindrical projection with world-scale bark continuity", "normalStrategy": "smooth vertex normals plus independent bark normal map"}, "parent": null, "attachment": null, "dimensions": {"width": 1.8, "height": 7.2, "depth": 1.6, "units": "world", "confidence": 0.86}, "transform": {"position": [0, 3.6, 0], "rotation": [0, 0, 0]}, "actionProfile": {"animationRole": "root", "pivot": {"mode": "base", "localPosition": [0, -3.6, 0], "axis": [0, 1, 0], "confidence": 0.95}, "transformChannels": {"translate": true, "rotate": true, "scale": true, "visibility": true, "materialState": true}, "sockets": [{"id": "left-fork", "localPosition": [-0.25, 0.6, 0], "localRotation": [0, 0, 0]}, {"id": "right-fork", "localPosition": [0.25, 0.6, 0], "localRotation": [0, 0, 0]}, {"id": "center-spire", "localPosition": [0, 0.8, 0], "localRotation": [0, 0, 0]}, {"id": "root-left", "localPosition": [-0.5, -3.1, 0.1], "localRotation": [0, 0, 0]}, {"id": "root-right", "localPosition": [0.5, -3.1, 0.1], "localRotation": [0, 0, 0]}, {"id": "energy-core", "localPosition": [0, -3.0, 0.42], "localRotation": [0, 0, 0]}], "collider": {"type": "capsule", "offset": [0, 0, 0], "scale": [1.2, 3.6, 1.1], "isTrigger": false}, "constraints": ["root pivot remains at ground contact"], "destruction": {"breakable": false, "fractureGroup": "trunk-core", "seamRefs": ["first-fork"], "detachableFragments": [], "breakImpulse": 0, "debrisMaterial": "bark"}}, "material": "bark", "materialLayers": ["bark", "gold-energy"], "deformations": ["root flare expands lower 18 percent", "centerline bends 0.25 units toward +X"], "joints": ["left-fork", "right-fork", "center-spire"], "seams": ["first-fork", "root-energy-channel"], "localFeatures": [{"id": "root-flare", "type": "raised ridge", "placement": "lowest 1.4 units", "size": "4.2 unit total span", "geometryEffect": "silhouette-visible buttresses", "materialEffect": "gold contact glow", "confidence": 0.82}, {"id": "gold-sap-channels", "type": "recessed emissive groove", "placement": "front-facing trunk and forks", "size": "0.04-0.12 unit width", "geometryEffect": "shallow inset curves", "materialEffect": "gold-energy overlay", "confidence": 0.9}, {"id": "code-glyph-grooves", "type": "carved line", "placement": "selected trunk and branch tangents", "size": "small abstract marks", "geometryEffect": "decal or shallow groove", "materialEffect": "low-intensity gold edge", "confidence": 0.7}], "surfaceDetail": {"macroRoughness": 0.34, "microRoughness": 0.62, "bumpAmplitude": 0.08, "normalPattern": "vertical bark plates with fork-following flow", "displacementPattern": "low-frequency root and ridge breakup", "occlusionPattern": "dark branch sockets and deep bark fissures", "edgeWearPattern": "warm polished ridge tops", "notes": "Bark must retain warm midtones beneath emission."}, "evidenceRefs": ["full-object", "trunk-fork", "root-ground"], "details": ["hero trunk", "separate bark and emission systems"], "fidelityTier": "blockout"};
  node_root_0.userData.actionProfile = {"animationRole": "root", "pivot": {"mode": "base", "localPosition": [0, -3.6, 0], "axis": [0, 1, 0], "confidence": 0.95}, "transformChannels": {"translate": true, "rotate": true, "scale": true, "visibility": true, "materialState": true}, "sockets": [{"id": "left-fork", "localPosition": [-0.25, 0.6, 0], "localRotation": [0, 0, 0]}, {"id": "right-fork", "localPosition": [0.25, 0.6, 0], "localRotation": [0, 0, 0]}, {"id": "center-spire", "localPosition": [0, 0.8, 0], "localRotation": [0, 0, 0]}, {"id": "root-left", "localPosition": [-0.5, -3.1, 0.1], "localRotation": [0, 0, 0]}, {"id": "root-right", "localPosition": [0.5, -3.1, 0.1], "localRotation": [0, 0, 0]}, {"id": "energy-core", "localPosition": [0, -3.0, 0.42], "localRotation": [0, 0, 0]}], "collider": {"type": "capsule", "offset": [0, 0, 0], "scale": [1.2, 3.6, 1.1], "isTrigger": false}, "constraints": ["root pivot remains at ground contact"], "destruction": {"breakable": false, "fractureGroup": "trunk-core", "seamRefs": ["first-fork"], "detachableFragments": [], "breakImpulse": 0, "debrisMaterial": "bark"}};
  (nodes["root"] ?? root).add(node_root_0);
  nodes["root"] = node_root_0;
  const mesh_root_0Geometry = endpoint_root_0
    ? new THREE.CylinderGeometry(endpoint_root_0.endRadius, endpoint_root_0.baseRadius, endpoint_root_0.length, 32, 12)
    : new THREE.CylinderGeometry(0.5, 0.5, 1, 48, 16);
  const mesh_root_0 = new THREE.Mesh(
    mesh_root_0Geometry,
    materialMap["bark"] ?? new THREE.MeshStandardMaterial({ color: 0x888888 })
  );
  mesh_root_0.name = "Repolis trunk core";
  if (endpoint_root_0) {
    mesh_root_0.position.copy(endpoint_root_0.midpoint);
    mesh_root_0.quaternion.copy(endpoint_root_0.quaternion);
  } else {
    mesh_root_0.scale.set(1.8, 7.2, 1.6);
  }
  mesh_root_0.castShadow = options.castShadow ?? true;
  mesh_root_0.receiveShadow = options.receiveShadow ?? true;
  mesh_root_0.userData.sculptComponent = {"id": "root", "name": "Repolis trunk core", "level": "macro", "role": "body", "importance": 1.0, "confidence": 0.9, "primitive": "cylinder", "geometryDescriptor": {"topologyIntent": "tapered trunk with enough radial and height segments for root flare and carved energy channels", "edgeTreatment": {"type": "organic bevel", "bevelRadius": 0.08, "segments": 3}, "deformationStack": ["lower flare", "subtle rightward bend", "asymmetric longitudinal ridges"], "uvStrategy": "cylindrical projection with world-scale bark continuity", "normalStrategy": "smooth vertex normals plus independent bark normal map"}, "parent": null, "attachment": null, "dimensions": {"width": 1.8, "height": 7.2, "depth": 1.6, "units": "world", "confidence": 0.86}, "transform": {"position": [0, 3.6, 0], "rotation": [0, 0, 0]}, "actionProfile": {"animationRole": "root", "pivot": {"mode": "base", "localPosition": [0, -3.6, 0], "axis": [0, 1, 0], "confidence": 0.95}, "transformChannels": {"translate": true, "rotate": true, "scale": true, "visibility": true, "materialState": true}, "sockets": [{"id": "left-fork", "localPosition": [-0.25, 0.6, 0], "localRotation": [0, 0, 0]}, {"id": "right-fork", "localPosition": [0.25, 0.6, 0], "localRotation": [0, 0, 0]}, {"id": "center-spire", "localPosition": [0, 0.8, 0], "localRotation": [0, 0, 0]}, {"id": "root-left", "localPosition": [-0.5, -3.1, 0.1], "localRotation": [0, 0, 0]}, {"id": "root-right", "localPosition": [0.5, -3.1, 0.1], "localRotation": [0, 0, 0]}, {"id": "energy-core", "localPosition": [0, -3.0, 0.42], "localRotation": [0, 0, 0]}], "collider": {"type": "capsule", "offset": [0, 0, 0], "scale": [1.2, 3.6, 1.1], "isTrigger": false}, "constraints": ["root pivot remains at ground contact"], "destruction": {"breakable": false, "fractureGroup": "trunk-core", "seamRefs": ["first-fork"], "detachableFragments": [], "breakImpulse": 0, "debrisMaterial": "bark"}}, "material": "bark", "materialLayers": ["bark", "gold-energy"], "deformations": ["root flare expands lower 18 percent", "centerline bends 0.25 units toward +X"], "joints": ["left-fork", "right-fork", "center-spire"], "seams": ["first-fork", "root-energy-channel"], "localFeatures": [{"id": "root-flare", "type": "raised ridge", "placement": "lowest 1.4 units", "size": "4.2 unit total span", "geometryEffect": "silhouette-visible buttresses", "materialEffect": "gold contact glow", "confidence": 0.82}, {"id": "gold-sap-channels", "type": "recessed emissive groove", "placement": "front-facing trunk and forks", "size": "0.04-0.12 unit width", "geometryEffect": "shallow inset curves", "materialEffect": "gold-energy overlay", "confidence": 0.9}, {"id": "code-glyph-grooves", "type": "carved line", "placement": "selected trunk and branch tangents", "size": "small abstract marks", "geometryEffect": "decal or shallow groove", "materialEffect": "low-intensity gold edge", "confidence": 0.7}], "surfaceDetail": {"macroRoughness": 0.34, "microRoughness": 0.62, "bumpAmplitude": 0.08, "normalPattern": "vertical bark plates with fork-following flow", "displacementPattern": "low-frequency root and ridge breakup", "occlusionPattern": "dark branch sockets and deep bark fissures", "edgeWearPattern": "warm polished ridge tops", "notes": "Bark must retain warm midtones beneath emission."}, "evidenceRefs": ["full-object", "trunk-fork", "root-ground"], "details": ["hero trunk", "separate bark and emission systems"], "fidelityTier": "blockout"};
  node_root_0.add(mesh_root_0);
  meshes["root"] = mesh_root_0;
  colliders["root"] = {"type": "capsule", "offset": [0, 0, 0], "scale": [1.2, 3.6, 1.1], "isTrigger": false};
  destructionGroups["trunk-core"] ??= [];
  destructionGroups["trunk-core"].push(node_root_0);
  const socket_root_left_fork_0 = new THREE.Object3D();
  socket_root_left_fork_0.name = "left-fork";
  socket_root_left_fork_0.position.set(-0.25, 0.6, 0.0);
  socket_root_left_fork_0.rotation.set(0.0, 0.0, 0.0);
  socket_root_left_fork_0.userData.socket = {"id": "left-fork", "localPosition": [-0.25, 0.6, 0], "localRotation": [0, 0, 0]};
  node_root_0.add(socket_root_left_fork_0);
  sockets["root:left-fork"] = socket_root_left_fork_0;
  const socket_root_right_fork_1 = new THREE.Object3D();
  socket_root_right_fork_1.name = "right-fork";
  socket_root_right_fork_1.position.set(0.25, 0.6, 0.0);
  socket_root_right_fork_1.rotation.set(0.0, 0.0, 0.0);
  socket_root_right_fork_1.userData.socket = {"id": "right-fork", "localPosition": [0.25, 0.6, 0], "localRotation": [0, 0, 0]};
  node_root_0.add(socket_root_right_fork_1);
  sockets["root:right-fork"] = socket_root_right_fork_1;
  const socket_root_center_spire_2 = new THREE.Object3D();
  socket_root_center_spire_2.name = "center-spire";
  socket_root_center_spire_2.position.set(0.0, 0.8, 0.0);
  socket_root_center_spire_2.rotation.set(0.0, 0.0, 0.0);
  socket_root_center_spire_2.userData.socket = {"id": "center-spire", "localPosition": [0, 0.8, 0], "localRotation": [0, 0, 0]};
  node_root_0.add(socket_root_center_spire_2);
  sockets["root:center-spire"] = socket_root_center_spire_2;
  const socket_root_root_left_3 = new THREE.Object3D();
  socket_root_root_left_3.name = "root-left";
  socket_root_root_left_3.position.set(-0.5, -3.1, 0.1);
  socket_root_root_left_3.rotation.set(0.0, 0.0, 0.0);
  socket_root_root_left_3.userData.socket = {"id": "root-left", "localPosition": [-0.5, -3.1, 0.1], "localRotation": [0, 0, 0]};
  node_root_0.add(socket_root_root_left_3);
  sockets["root:root-left"] = socket_root_root_left_3;
  const socket_root_root_right_4 = new THREE.Object3D();
  socket_root_root_right_4.name = "root-right";
  socket_root_root_right_4.position.set(0.5, -3.1, 0.1);
  socket_root_root_right_4.rotation.set(0.0, 0.0, 0.0);
  socket_root_root_right_4.userData.socket = {"id": "root-right", "localPosition": [0.5, -3.1, 0.1], "localRotation": [0, 0, 0]};
  node_root_0.add(socket_root_root_right_4);
  sockets["root:root-right"] = socket_root_root_right_4;
  const socket_root_energy_core_5 = new THREE.Object3D();
  socket_root_energy_core_5.name = "energy-core";
  socket_root_energy_core_5.position.set(0.0, -3.0, 0.42);
  socket_root_energy_core_5.rotation.set(0.0, 0.0, 0.0);
  socket_root_energy_core_5.userData.socket = {"id": "energy-core", "localPosition": [0, -3.0, 0.42], "localRotation": [0, 0, 0]};
  node_root_0.add(socket_root_energy_core_5);
  sockets["root:energy-core"] = socket_root_energy_core_5;

  const attachment_crown_left_1 = {"parentId": "root", "parentSocket": "left-fork", "localStart": [-0.25, 0.6, 0], "localEnd": [-3.7, 5.2, -0.1], "contactType": "overlap", "overlap": 0.25, "gapTolerance": 0.05, "evidenceRefs": ["left-canopy"]};
  const endpoint_crown_left_1 = makeAttachmentEndpoint(attachment_crown_left_1);
  const node_crown_left_1 = new THREE.Group();
  node_crown_left_1.name = "Left crown mass__pivot";
  if (endpoint_crown_left_1) {
    node_crown_left_1.position.copy(endpoint_crown_left_1.start);
    node_crown_left_1.rotation.set(0, 0, 0);
    node_crown_left_1.scale.set(1, 1, 1);
  } else {
    node_crown_left_1.position.set(-3.5, 5.0, -0.2);
    node_crown_left_1.rotation.set(0.0, 0.0, -0.08);
    node_crown_left_1.scale.set(1, 1, 1);
  }
  node_crown_left_1.userData.sculptComponent = {"id": "crown-left", "name": "Left crown mass", "level": "macro", "role": "crown", "importance": 0.9, "confidence": 0.8, "primitive": "ellipsoid", "geometryDescriptor": {"topologyIntent": "temporary perforated blockout mass later replaced by instanced leaves", "edgeTreatment": {"type": "soft", "bevelRadius": 0.2, "segments": 2}, "deformationStack": ["flatten lower edge", "extend outer-left lobe"], "uvStrategy": "object-space procedural", "normalStrategy": "smooth"}, "parent": "root", "attachment": {"parentId": "root", "parentSocket": "left-fork", "localStart": [-0.25, 0.6, 0], "localEnd": [-3.7, 5.2, -0.1], "contactType": "overlap", "overlap": 0.25, "gapTolerance": 0.05, "evidenceRefs": ["left-canopy"]}, "dimensions": {"width": 8.5, "height": 4.8, "depth": 3.2, "units": "world", "confidence": 0.78}, "transform": {"position": [-3.5, 5.0, -0.2], "rotation": [0, 0, -0.08]}, "actionProfile": {"animationRole": "deformable", "pivot": {"mode": "socket", "localPosition": [-0.25, 0.6, 0], "axis": [0, 0, 1], "confidence": 0.78}, "transformChannels": {"rotate": true, "bend": true, "visibility": true, "materialState": true}, "sockets": [], "collider": {"type": "sphere", "offset": [-3.25, 4.4, -0.2], "scale": [4.2, 2.4, 1.6], "isTrigger": false}, "constraints": ["sway under 4 degrees"], "destruction": {"breakable": false, "fractureGroup": "left-crown", "seamRefs": [], "detachableFragments": [], "breakImpulse": 0, "debrisMaterial": "amber-leaf"}}, "material": "amber-leaf", "materialLayers": ["amber-leaf", "cyan-leaf"], "deformations": ["three overlapping crown lobes", "irregular perforated edge"], "joints": ["left-fork"], "seams": [], "localFeatures": [{"id": "left-cyan-constellation", "type": "raised light nodes", "placement": "outer upper-left crown", "size": "grouped 0.05-0.12 unit points", "geometryEffect": "instanced nodes and thin links", "materialEffect": "cyan emission", "confidence": 0.82}, {"id": "left-hanging-lights", "type": "hanging strand", "placement": "lower outer-left branches", "size": "0.4-1.2 unit drops", "geometryEffect": "thin curves with point nodes", "materialEffect": "warm gold emission", "confidence": 0.75}], "surfaceDetail": {"macroRoughness": 0.1, "microRoughness": 0.35, "bumpAmplitude": 0.01, "normalPattern": "leaf veins", "displacementPattern": "", "occlusionPattern": "cluster self-shadow", "edgeWearPattern": "", "notes": "Blockout material remains translucent enough to show branch gaps."}, "evidenceRefs": ["full-object", "left-canopy", "upper-canopy"], "details": ["dominant horizontal crown extension"], "fidelityTier": "blockout"};
  node_crown_left_1.userData.actionProfile = {"animationRole": "deformable", "pivot": {"mode": "socket", "localPosition": [-0.25, 0.6, 0], "axis": [0, 0, 1], "confidence": 0.78}, "transformChannels": {"rotate": true, "bend": true, "visibility": true, "materialState": true}, "sockets": [], "collider": {"type": "sphere", "offset": [-3.25, 4.4, -0.2], "scale": [4.2, 2.4, 1.6], "isTrigger": false}, "constraints": ["sway under 4 degrees"], "destruction": {"breakable": false, "fractureGroup": "left-crown", "seamRefs": [], "detachableFragments": [], "breakImpulse": 0, "debrisMaterial": "amber-leaf"}};
  (nodes["root"] ?? root).add(node_crown_left_1);
  nodes["crown-left"] = node_crown_left_1;
  const mesh_crown_left_1Geometry = new THREE.SphereGeometry(0.5, 64, 40);
  const mesh_crown_left_1 = new THREE.Mesh(
    mesh_crown_left_1Geometry,
    materialMap["amber-leaf"] ?? new THREE.MeshStandardMaterial({ color: 0x888888 })
  );
  mesh_crown_left_1.name = "Left crown mass";
  if (endpoint_crown_left_1) {
    mesh_crown_left_1.position.set(-3.5, 5.0, -0.2);
    mesh_crown_left_1.position.sub(endpoint_crown_left_1.start);
    mesh_crown_left_1.rotation.set(0.0, 0.0, -0.08);
  }
  mesh_crown_left_1.scale.set(8.5, 4.8, 3.2);
  mesh_crown_left_1.castShadow = options.castShadow ?? true;
  mesh_crown_left_1.receiveShadow = options.receiveShadow ?? true;
  mesh_crown_left_1.userData.sculptComponent = {"id": "crown-left", "name": "Left crown mass", "level": "macro", "role": "crown", "importance": 0.9, "confidence": 0.8, "primitive": "ellipsoid", "geometryDescriptor": {"topologyIntent": "temporary perforated blockout mass later replaced by instanced leaves", "edgeTreatment": {"type": "soft", "bevelRadius": 0.2, "segments": 2}, "deformationStack": ["flatten lower edge", "extend outer-left lobe"], "uvStrategy": "object-space procedural", "normalStrategy": "smooth"}, "parent": "root", "attachment": {"parentId": "root", "parentSocket": "left-fork", "localStart": [-0.25, 0.6, 0], "localEnd": [-3.7, 5.2, -0.1], "contactType": "overlap", "overlap": 0.25, "gapTolerance": 0.05, "evidenceRefs": ["left-canopy"]}, "dimensions": {"width": 8.5, "height": 4.8, "depth": 3.2, "units": "world", "confidence": 0.78}, "transform": {"position": [-3.5, 5.0, -0.2], "rotation": [0, 0, -0.08]}, "actionProfile": {"animationRole": "deformable", "pivot": {"mode": "socket", "localPosition": [-0.25, 0.6, 0], "axis": [0, 0, 1], "confidence": 0.78}, "transformChannels": {"rotate": true, "bend": true, "visibility": true, "materialState": true}, "sockets": [], "collider": {"type": "sphere", "offset": [-3.25, 4.4, -0.2], "scale": [4.2, 2.4, 1.6], "isTrigger": false}, "constraints": ["sway under 4 degrees"], "destruction": {"breakable": false, "fractureGroup": "left-crown", "seamRefs": [], "detachableFragments": [], "breakImpulse": 0, "debrisMaterial": "amber-leaf"}}, "material": "amber-leaf", "materialLayers": ["amber-leaf", "cyan-leaf"], "deformations": ["three overlapping crown lobes", "irregular perforated edge"], "joints": ["left-fork"], "seams": [], "localFeatures": [{"id": "left-cyan-constellation", "type": "raised light nodes", "placement": "outer upper-left crown", "size": "grouped 0.05-0.12 unit points", "geometryEffect": "instanced nodes and thin links", "materialEffect": "cyan emission", "confidence": 0.82}, {"id": "left-hanging-lights", "type": "hanging strand", "placement": "lower outer-left branches", "size": "0.4-1.2 unit drops", "geometryEffect": "thin curves with point nodes", "materialEffect": "warm gold emission", "confidence": 0.75}], "surfaceDetail": {"macroRoughness": 0.1, "microRoughness": 0.35, "bumpAmplitude": 0.01, "normalPattern": "leaf veins", "displacementPattern": "", "occlusionPattern": "cluster self-shadow", "edgeWearPattern": "", "notes": "Blockout material remains translucent enough to show branch gaps."}, "evidenceRefs": ["full-object", "left-canopy", "upper-canopy"], "details": ["dominant horizontal crown extension"], "fidelityTier": "blockout"};
  node_crown_left_1.add(mesh_crown_left_1);
  meshes["crown-left"] = mesh_crown_left_1;
  colliders["crown-left"] = {"type": "sphere", "offset": [-3.25, 4.4, -0.2], "scale": [4.2, 2.4, 1.6], "isTrigger": false};
  destructionGroups["left-crown"] ??= [];
  destructionGroups["left-crown"].push(node_crown_left_1);

  const attachment_crown_right_2 = {"parentId": "root", "parentSocket": "right-fork", "localStart": [0.25, 0.6, 0], "localEnd": [3.5, 5.4, 0.1], "contactType": "overlap", "overlap": 0.25, "gapTolerance": 0.05, "evidenceRefs": ["right-canopy"]};
  const endpoint_crown_right_2 = makeAttachmentEndpoint(attachment_crown_right_2);
  const node_crown_right_2 = new THREE.Group();
  node_crown_right_2.name = "Right crown mass__pivot";
  if (endpoint_crown_right_2) {
    node_crown_right_2.position.copy(endpoint_crown_right_2.start);
    node_crown_right_2.rotation.set(0, 0, 0);
    node_crown_right_2.scale.set(1, 1, 1);
  } else {
    node_crown_right_2.position.set(3.4, 5.1, 0.0);
    node_crown_right_2.rotation.set(0.0, 0.0, 0.06);
    node_crown_right_2.scale.set(1, 1, 1);
  }
  node_crown_right_2.userData.sculptComponent = {"id": "crown-right", "name": "Right crown mass", "level": "macro", "role": "crown", "importance": 0.9, "confidence": 0.8, "primitive": "ellipsoid", "geometryDescriptor": {"topologyIntent": "temporary perforated blockout mass later replaced by instanced leaves", "edgeTreatment": {"type": "soft", "bevelRadius": 0.2, "segments": 2}, "deformationStack": ["raise upper-right lobe", "tighten outer edge"], "uvStrategy": "object-space procedural", "normalStrategy": "smooth"}, "parent": "root", "attachment": {"parentId": "root", "parentSocket": "right-fork", "localStart": [0.25, 0.6, 0], "localEnd": [3.5, 5.4, 0.1], "contactType": "overlap", "overlap": 0.25, "gapTolerance": 0.05, "evidenceRefs": ["right-canopy"]}, "dimensions": {"width": 7.8, "height": 5.0, "depth": 3.3, "units": "world", "confidence": 0.78}, "transform": {"position": [3.4, 5.1, 0], "rotation": [0, 0, 0.06]}, "actionProfile": {"animationRole": "deformable", "pivot": {"mode": "socket", "localPosition": [0.25, 0.6, 0], "axis": [0, 0, 1], "confidence": 0.78}, "transformChannels": {"rotate": true, "bend": true, "visibility": true, "materialState": true}, "sockets": [], "collider": {"type": "sphere", "offset": [3.15, 4.5, 0], "scale": [3.9, 2.5, 1.65], "isTrigger": false}, "constraints": ["sway under 4 degrees"], "destruction": {"breakable": false, "fractureGroup": "right-crown", "seamRefs": [], "detachableFragments": [], "breakImpulse": 0, "debrisMaterial": "amber-leaf"}}, "material": "amber-leaf", "materialLayers": ["amber-leaf", "cyan-leaf"], "deformations": ["upright upper lobe", "asymmetric outer perforations"], "joints": ["right-fork"], "seams": [], "localFeatures": [{"id": "right-cyan-leaf-patch", "type": "local color cluster", "placement": "upper-right tips", "size": "roughly 20 percent of right crown leaves", "geometryEffect": "instanced cards", "materialEffect": "cyan emission", "confidence": 0.82}, {"id": "right-gold-edge", "type": "emissive ridge", "placement": "inner right bough edges", "size": "narrow branch-following paths", "geometryEffect": "curve sweep", "materialEffect": "gold emission", "confidence": 0.8}], "surfaceDetail": {"macroRoughness": 0.1, "microRoughness": 0.35, "bumpAmplitude": 0.01, "normalPattern": "leaf veins", "displacementPattern": "", "occlusionPattern": "cluster self-shadow", "edgeWearPattern": "", "notes": "Keep right crown slightly more compact than left."}, "evidenceRefs": ["full-object", "right-canopy", "upper-canopy"], "details": ["upright and compact crown balance"], "fidelityTier": "blockout"};
  node_crown_right_2.userData.actionProfile = {"animationRole": "deformable", "pivot": {"mode": "socket", "localPosition": [0.25, 0.6, 0], "axis": [0, 0, 1], "confidence": 0.78}, "transformChannels": {"rotate": true, "bend": true, "visibility": true, "materialState": true}, "sockets": [], "collider": {"type": "sphere", "offset": [3.15, 4.5, 0], "scale": [3.9, 2.5, 1.65], "isTrigger": false}, "constraints": ["sway under 4 degrees"], "destruction": {"breakable": false, "fractureGroup": "right-crown", "seamRefs": [], "detachableFragments": [], "breakImpulse": 0, "debrisMaterial": "amber-leaf"}};
  (nodes["root"] ?? root).add(node_crown_right_2);
  nodes["crown-right"] = node_crown_right_2;
  const mesh_crown_right_2Geometry = new THREE.SphereGeometry(0.5, 64, 40);
  const mesh_crown_right_2 = new THREE.Mesh(
    mesh_crown_right_2Geometry,
    materialMap["amber-leaf"] ?? new THREE.MeshStandardMaterial({ color: 0x888888 })
  );
  mesh_crown_right_2.name = "Right crown mass";
  if (endpoint_crown_right_2) {
    mesh_crown_right_2.position.set(3.4, 5.1, 0.0);
    mesh_crown_right_2.position.sub(endpoint_crown_right_2.start);
    mesh_crown_right_2.rotation.set(0.0, 0.0, 0.06);
  }
  mesh_crown_right_2.scale.set(7.8, 5.0, 3.3);
  mesh_crown_right_2.castShadow = options.castShadow ?? true;
  mesh_crown_right_2.receiveShadow = options.receiveShadow ?? true;
  mesh_crown_right_2.userData.sculptComponent = {"id": "crown-right", "name": "Right crown mass", "level": "macro", "role": "crown", "importance": 0.9, "confidence": 0.8, "primitive": "ellipsoid", "geometryDescriptor": {"topologyIntent": "temporary perforated blockout mass later replaced by instanced leaves", "edgeTreatment": {"type": "soft", "bevelRadius": 0.2, "segments": 2}, "deformationStack": ["raise upper-right lobe", "tighten outer edge"], "uvStrategy": "object-space procedural", "normalStrategy": "smooth"}, "parent": "root", "attachment": {"parentId": "root", "parentSocket": "right-fork", "localStart": [0.25, 0.6, 0], "localEnd": [3.5, 5.4, 0.1], "contactType": "overlap", "overlap": 0.25, "gapTolerance": 0.05, "evidenceRefs": ["right-canopy"]}, "dimensions": {"width": 7.8, "height": 5.0, "depth": 3.3, "units": "world", "confidence": 0.78}, "transform": {"position": [3.4, 5.1, 0], "rotation": [0, 0, 0.06]}, "actionProfile": {"animationRole": "deformable", "pivot": {"mode": "socket", "localPosition": [0.25, 0.6, 0], "axis": [0, 0, 1], "confidence": 0.78}, "transformChannels": {"rotate": true, "bend": true, "visibility": true, "materialState": true}, "sockets": [], "collider": {"type": "sphere", "offset": [3.15, 4.5, 0], "scale": [3.9, 2.5, 1.65], "isTrigger": false}, "constraints": ["sway under 4 degrees"], "destruction": {"breakable": false, "fractureGroup": "right-crown", "seamRefs": [], "detachableFragments": [], "breakImpulse": 0, "debrisMaterial": "amber-leaf"}}, "material": "amber-leaf", "materialLayers": ["amber-leaf", "cyan-leaf"], "deformations": ["upright upper lobe", "asymmetric outer perforations"], "joints": ["right-fork"], "seams": [], "localFeatures": [{"id": "right-cyan-leaf-patch", "type": "local color cluster", "placement": "upper-right tips", "size": "roughly 20 percent of right crown leaves", "geometryEffect": "instanced cards", "materialEffect": "cyan emission", "confidence": 0.82}, {"id": "right-gold-edge", "type": "emissive ridge", "placement": "inner right bough edges", "size": "narrow branch-following paths", "geometryEffect": "curve sweep", "materialEffect": "gold emission", "confidence": 0.8}], "surfaceDetail": {"macroRoughness": 0.1, "microRoughness": 0.35, "bumpAmplitude": 0.01, "normalPattern": "leaf veins", "displacementPattern": "", "occlusionPattern": "cluster self-shadow", "edgeWearPattern": "", "notes": "Keep right crown slightly more compact than left."}, "evidenceRefs": ["full-object", "right-canopy", "upper-canopy"], "details": ["upright and compact crown balance"], "fidelityTier": "blockout"};
  node_crown_right_2.add(mesh_crown_right_2);
  meshes["crown-right"] = mesh_crown_right_2;
  colliders["crown-right"] = {"type": "sphere", "offset": [3.15, 4.5, 0], "scale": [3.9, 2.5, 1.65], "isTrigger": false};
  destructionGroups["right-crown"] ??= [];
  destructionGroups["right-crown"].push(node_crown_right_2);

  root.userData.sculptRuntime = { nodes, meshes, sockets, colliders, destructionGroups } satisfies ProceduralModelRuntime;
  root.userData.lookDevTargets = {"qualityPriority": "balanced", "materialPass": {"albedoPaletteRequired": true, "roughnessVariationRequired": true, "normalOrBumpRequired": true, "localOverridesRequired": true, "minimumTextureResolution": 1024, "preferredTextureResolution": 2048, "independentMapChannels": ["albedo", "roughness", "height", "normal", "ambient-occlusion"], "requiredSurfaceFrequencyBands": ["macro", "meso", "micro"], "geometryReliefRequiredWhenSilhouetteAffected": true, "referencePbrExtraction": {"requiredWhenSourceImagePresent": false, "targetThreshold": 0.7, "stopOnLowConfidence": true, "script": "../../scripts/extract_reference_pbr.py", "acceptedLimitation": "The stylized source bakes bloom, emission, and scene lighting into the pixels. Use procedural bark and emissive materials; treat any extraction only as palette evidence."}, "mustAvoid": ["single flat albedo per material", "uniform roughness", "albedo texture reused as roughness/height/normal/AO", "single-frequency random noise", "plastic-looking smooth bark, stone, cloth, foliage, or aged material", "local color/detail described only in prose without material masks", "claiming exact PBR recovery when confidence is below the target threshold"]}, "lightingPass": {"requiredTerms": ["key light", "fill light", "rim or environment light", "exposure", "tone mapping", "background", "contact shadow"], "mustAvoid": ["ambient-only lighting", "flat value range", "missing contact shadow", "reference lighting copied without separating material readability"]}, "screenshotReview": ["Compare albedo palette and local color zones.", "Compare roughness/normal/bump response under light.", "Compare cavity dirt, edge wear, stains, moss, scratches, or other local masks.", "Compare key/fill/rim structure, exposure, tone mapping, background, and contact shadows.", "Capture a neutral-light render to verify material readability without reference lighting.", "Capture a grazing-light close-up to expose flat normals, uniform roughness, tiling, and plastic highlights.", "Capture a reference-matched render from the same camera framing as the source."]};
  root.userData.sculptDNA = {"schemaVersion": "1.0", "enabled": true, "strategy": "constraint-aware semantic variation", "parameters": [{"id": "bark-roughness", "label": "bark roughness", "target": {"kind": "material", "id": "bark", "path": "roughness.base"}, "operation": "set", "distribution": "triangular", "range": {"min": 0.56, "max": 0.8}, "precision": 4, "semanticEffects": ["highlight width", "surface age", "material readability"]}, {"id": "bark-dominant-palette", "label": "bark dominant palette color", "target": {"kind": "material", "id": "bark", "path": "colorVariation.palette.0"}, "operation": "set", "distribution": "choice", "choices": ["#2B170F", "#4A2B18", "#6F4324", "#9A6333"], "semanticEffects": ["palette family", "local albedo variation"]}, {"id": "gold-energy-roughness", "label": "gold-energy roughness", "target": {"kind": "material", "id": "gold-energy", "path": "roughness.base"}, "operation": "set", "distribution": "triangular", "range": {"min": 0.16, "max": 0.4}, "precision": 4, "semanticEffects": ["highlight width", "surface age", "material readability"]}, {"id": "gold-energy-dominant-palette", "label": "gold-energy dominant palette color", "target": {"kind": "material", "id": "gold-energy", "path": "colorVariation.palette.0"}, "operation": "set", "distribution": "choice", "choices": ["#D27A20", "#FFB23F", "#FFD477", "#FFF2B0"], "semanticEffects": ["palette family", "local albedo variation"]}, {"id": "amber-leaf-roughness", "label": "amber-leaf roughness", "target": {"kind": "material", "id": "amber-leaf", "path": "roughness.base"}, "operation": "set", "distribution": "triangular", "range": {"min": 0.36, "max": 0.6}, "precision": 4, "semanticEffects": ["highlight width", "surface age", "material readability"]}, {"id": "amber-leaf-dominant-palette", "label": "amber-leaf dominant palette color", "target": {"kind": "material", "id": "amber-leaf", "path": "colorVariation.palette.0"}, "operation": "set", "distribution": "choice", "choices": ["#D87927", "#F2A545", "#FFC867", "#FFF0B4"], "semanticEffects": ["palette family", "local albedo variation"]}, {"id": "cyan-leaf-roughness", "label": "cyan-leaf roughness", "target": {"kind": "material", "id": "cyan-leaf", "path": "roughness.base"}, "operation": "set", "distribution": "triangular", "range": {"min": 0.26, "max": 0.5}, "precision": 4, "semanticEffects": ["highlight width", "surface age", "material readability"]}, {"id": "cyan-leaf-dominant-palette", "label": "cyan-leaf dominant palette color", "target": {"kind": "material", "id": "cyan-leaf", "path": "colorVariation.palette.0"}, "operation": "set", "distribution": "choice", "choices": ["#1A8FA8", "#38CDE0", "#5EF7FF", "#B6FFFF"], "semanticEffects": ["palette family", "local albedo variation"]}, {"id": "amber-leaf-clusters-count", "label": "amber-leaf-clusters repetition count", "target": {"kind": "repetition", "id": "amber-leaf-clusters", "path": "count"}, "operation": "set", "distribution": "triangular", "range": {"min": 416, "max": 624}, "precision": 0, "semanticEffects": ["repetition density", "draw-call and triangle budget"]}, {"id": "cyan-leaf-accents-count", "label": "cyan-leaf-accents repetition count", "target": {"kind": "repetition", "id": "cyan-leaf-accents", "path": "count"}, "operation": "set", "distribution": "triangular", "range": {"min": 90, "max": 134}, "precision": 0, "semanticEffects": ["repetition density", "draw-call and triangle budget"]}, {"id": "constellation-nodes-count", "label": "constellation-nodes repetition count", "target": {"kind": "repetition", "id": "constellation-nodes", "path": "count"}, "operation": "set", "distribution": "triangular", "range": {"min": 26, "max": 38}, "precision": 0, "semanticEffects": ["repetition density", "draw-call and triangle budget"]}, {"id": "hanging-light-strands-count", "label": "hanging-light-strands repetition count", "target": {"kind": "repetition", "id": "hanging-light-strands", "path": "count"}, "operation": "set", "distribution": "triangular", "range": {"min": 14, "max": 22}, "precision": 0, "semanticEffects": ["repetition density", "draw-call and triangle budget"]}], "constraints": [], "invariants": ["component-ids", "parent-links", "material-refs", "socket-ids", "fracture-groups", "attachment-roots", "build-pass-order", "feature-review-targets"], "variantPolicy": {"defaultCount": 4, "defaultSeed": 1337, "maxAttemptsPerVariant": 64, "resetReviewEvidence": true}, "authoringRule": "These controls are conservative starters. Rename them in object language, add coupling groups for dependent proportions, and add ratio/range constraints before generating a production family."};
  root.userData.variantProvenance = null;
  root.userData.actionReadiness = {
    note: 'Use root.userData.sculptRuntime.nodes for transforms, sockets for attachments, colliders for physics proxies, and destructionGroups for breakable sets.',
  };
  return root;
}

export function createRepolisTreeLookDevLights(
  mode: 'neutral' | 'grazing' | 'reference' = 'neutral',
): THREE.Group {
  const lights = new THREE.Group();
  lights.name = "Repolis Tree look-dev lights";
  const hemi = new THREE.HemisphereLight(
    mode === 'reference' ? 0xfff0d6 : 0xf2f4ff,
    0x363b42,
    mode === 'grazing' ? 0.28 : mode === 'reference' ? 0.72 : 0.85,
  );
  lights.add(hemi);
  const key = new THREE.DirectionalLight(
    mode === 'reference' ? 0xffcf8a : 0xfff4e8,
    mode === 'grazing' ? 4.2 : mode === 'reference' ? 2.6 : 2.15,
  );
  if (mode === 'grazing') key.position.set(7.5, 1.1, 4.0);
  else if (mode === 'reference') key.position.set(-4.5, 7.5, 5.0);
  else key.position.set(-4.0, 6.0, 5.5);
  key.castShadow = true;
  key.shadow.mapSize.set(4096, 4096);
  key.shadow.bias = -0.00025;
  key.shadow.normalBias = 0.018;
  lights.add(key);
  const fill = new THREE.DirectionalLight(0xa8c4ff, mode === 'grazing' ? 0.12 : 0.42);
  fill.position.set(4.0, 3.0, 3.5);
  lights.add(fill);
  const rim = new THREE.DirectionalLight(0xfff1c4, mode === 'grazing' ? 0.28 : 0.85);
  rim.position.set(0.5, 4.5, -6.0);
  lights.add(rim);
  lights.userData.reviewMode = mode;
  lights.userData.lightingFromPhoto = ["Key light: warm gold emissive contribution from root and branch channels, strongest near the trunk center; use emission for glow but not as the only bark illumination.", "Fill light: soft cool-blue hemisphere fill from the night sky at low intensity so shaded bark remains warm brown instead of black.", "Rim/environment light: cyan-blue back and side rim from the star field to separate outer leaves and branch tips.", "Exposure and tone mapping: ACES Filmic tone mapping with exposure near 1.0; tune bloom threshold above bark values and below gold/cyan emission peaks.", "Background: deep navy-to-indigo gradient or environment map with restrained stars; keep background luminance below the tree crown.", "Contact shadow: soft ground shadow and local AO under the root flare, branch sockets, and overlapping leaf clusters."];
  lights.userData.lookDevTargets = {"qualityPriority": "balanced", "materialPass": {"albedoPaletteRequired": true, "roughnessVariationRequired": true, "normalOrBumpRequired": true, "localOverridesRequired": true, "minimumTextureResolution": 1024, "preferredTextureResolution": 2048, "independentMapChannels": ["albedo", "roughness", "height", "normal", "ambient-occlusion"], "requiredSurfaceFrequencyBands": ["macro", "meso", "micro"], "geometryReliefRequiredWhenSilhouetteAffected": true, "referencePbrExtraction": {"requiredWhenSourceImagePresent": false, "targetThreshold": 0.7, "stopOnLowConfidence": true, "script": "../../scripts/extract_reference_pbr.py", "acceptedLimitation": "The stylized source bakes bloom, emission, and scene lighting into the pixels. Use procedural bark and emissive materials; treat any extraction only as palette evidence."}, "mustAvoid": ["single flat albedo per material", "uniform roughness", "albedo texture reused as roughness/height/normal/AO", "single-frequency random noise", "plastic-looking smooth bark, stone, cloth, foliage, or aged material", "local color/detail described only in prose without material masks", "claiming exact PBR recovery when confidence is below the target threshold"]}, "lightingPass": {"requiredTerms": ["key light", "fill light", "rim or environment light", "exposure", "tone mapping", "background", "contact shadow"], "mustAvoid": ["ambient-only lighting", "flat value range", "missing contact shadow", "reference lighting copied without separating material readability"]}, "screenshotReview": ["Compare albedo palette and local color zones.", "Compare roughness/normal/bump response under light.", "Compare cavity dirt, edge wear, stains, moss, scratches, or other local masks.", "Compare key/fill/rim structure, exposure, tone mapping, background, and contact shadows.", "Capture a neutral-light render to verify material readability without reference lighting.", "Capture a grazing-light close-up to expose flat normals, uniform roughness, tiling, and plastic highlights.", "Capture a reference-matched render from the same camera framing as the source."]};
  return lights;
}
