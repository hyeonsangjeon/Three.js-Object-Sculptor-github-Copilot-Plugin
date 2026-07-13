import * as THREE from 'three';

export const SEOUL_TEXTURE_SIZE = 1024;

const PROFILES = Object.freeze({
  roof: {
    base: [34, 45, 42],
    accent: [62, 76, 68],
    roughness: 184,
    roughnessRange: 36,
    heightScale: 0.72,
    aoStrength: 0.34,
    pattern: 'roof',
  },
  court: {
    base: [190, 178, 151],
    accent: [222, 213, 189],
    roughness: 205,
    roughnessRange: 24,
    heightScale: 0.34,
    aoStrength: 0.18,
    pattern: 'sand',
  },
  timber: {
    base: [64, 35, 31],
    accent: [111, 55, 45],
    roughness: 173,
    roughnessRange: 31,
    heightScale: 0.48,
    aoStrength: 0.28,
    pattern: 'grain',
  },
  stone: {
    base: [174, 169, 153],
    accent: [215, 207, 187],
    roughness: 211,
    roughnessRange: 22,
    heightScale: 0.42,
    aoStrength: 0.24,
    pattern: 'stone',
  },
  mountain: {
    base: [52, 70, 59],
    accent: [103, 112, 91],
    roughness: 222,
    roughnessRange: 21,
    heightScale: 0.78,
    aoStrength: 0.42,
    pattern: 'mountain',
  },
  vegetation: {
    base: [40, 69, 47],
    accent: [79, 104, 62],
    roughness: 220,
    roughnessRange: 20,
    heightScale: 0.58,
    aoStrength: 0.38,
    pattern: 'foliage',
  },
  city: {
    base: [126, 136, 134],
    accent: [184, 188, 180],
    roughness: 194,
    roughnessRange: 27,
    heightScale: 0.26,
    aoStrength: 0.2,
    pattern: 'city',
  },
});

function clamp01(value) {
  return Math.min(1, Math.max(0, value));
}

function hash2(x, y, seed) {
  let value = Math.imul(x + seed, 374761393) + Math.imul(y - seed, 668265263);
  value = Math.imul(value ^ value >>> 13, 1274126177);
  return ((value ^ value >>> 16) >>> 0) / 4294967295;
}

function materialField(profile, x, y, seed, size) {
  const u = x / size;
  const v = y / size;
  const macro = 0.5 + 0.25 * Math.sin(u * Math.PI * 5.2 + seed * 0.001)
    + 0.25 * Math.cos(v * Math.PI * 4.4 - seed * 0.0007);
  const meso = 0.5 + 0.25 * Math.sin((u + v) * Math.PI * 31)
    + 0.25 * Math.cos((u - v) * Math.PI * 23);
  const micro = hash2(x, y, seed);
  let authored = 0.5;
  if (profile.pattern === 'roof') {
    authored = 0.5 + 0.28 * Math.sin(u * Math.PI * 48)
      + 0.18 * Math.cos(v * Math.PI * 22);
  } else if (profile.pattern === 'sand') {
    authored = 0.35 * macro + 0.25 * meso + 0.4 * micro;
  } else if (profile.pattern === 'grain') {
    authored = 0.5 + 0.35 * Math.sin(v * Math.PI * 70 + Math.sin(u * Math.PI * 8));
  } else if (profile.pattern === 'stone') {
    authored = 0.55 * meso + 0.45 * (micro > 0.84 ? 1 : micro * 0.45);
  } else if (profile.pattern === 'mountain') {
    authored = 0.48 * macro + 0.32 * meso + 0.2 * micro;
  } else if (profile.pattern === 'foliage') {
    authored = 0.35 * macro + 0.4 * meso + 0.25 * Math.abs(micro - 0.5) * 2;
  } else if (profile.pattern === 'city') {
    const grid = (Math.sin(u * Math.PI * 32) > 0 ? 0.62 : 0.38)
      * (Math.cos(v * Math.PI * 28) > 0 ? 1 : 0.72);
    authored = 0.35 * macro + 0.45 * grid + 0.2 * micro;
  }
  const height = clamp01(
    (0.32 * macro + 0.28 * meso + 0.4 * authored) * profile.heightScale
      + (1 - profile.heightScale) * 0.5,
  );
  const dirt = clamp01(0.55 * (1 - macro) + 0.45 * (1 - authored));
  return {
    colorMix: clamp01(0.12 + height * 0.62 + micro * 0.16),
    height,
    roughness: clamp01((profile.roughness + (micro - 0.5) * profile.roughnessRange) / 255),
    ao: clamp01(1 - dirt * profile.aoStrength),
  };
}

function dataTexture(data, size, format, name, channel, colorSpace = THREE.NoColorSpace) {
  const texture = new THREE.DataTexture(data, size, size, format, THREE.UnsignedByteType);
  texture.name = name;
  texture.colorSpace = colorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.channel = 0;
  texture.unpackAlignment = 1;
  texture.userData = {
    generated: true,
    resolution: size,
    semanticChannel: channel,
    independentBuffer: true,
  };
  texture.needsUpdate = true;
  return texture;
}

function createMapSet(id, profile, seed, size) {
  const pixelCount = size * size;
  const albedo = new Uint8Array(pixelCount * 4);
  const roughness = new Uint8Array(pixelCount * 4);
  const height = new Uint8Array(pixelCount);
  const normal = new Uint8Array(pixelCount * 4);
  const ao = new Uint8Array(pixelCount);

  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const pixel = y * size + x;
      const field = materialField(profile, x, y, seed, size);
      for (let channel = 0; channel < 3; channel += 1) {
        albedo[pixel * 4 + channel] = Math.round(
          profile.base[channel]
            + (profile.accent[channel] - profile.base[channel]) * field.colorMix,
        );
      }
      albedo[pixel * 4 + 3] = 255;
      const roughnessValue = Math.round(field.roughness * 255);
      roughness[pixel * 4] = roughnessValue;
      roughness[pixel * 4 + 1] = roughnessValue;
      roughness[pixel * 4 + 2] = roughnessValue;
      roughness[pixel * 4 + 3] = 255;
      height[pixel] = Math.round(field.height * 255);
      ao[pixel] = Math.round(field.ao * 255);
    }
  }

  const strength = profile.heightScale * 2.2;
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const pixel = y * size + x;
      const left = height[y * size + (x + size - 1) % size] / 255;
      const right = height[y * size + (x + 1) % size] / 255;
      const down = height[((y + size - 1) % size) * size + x] / 255;
      const up = height[((y + 1) % size) * size + x] / 255;
      const nx = (left - right) * strength;
      const ny = (down - up) * strength;
      const nz = 1;
      const length = Math.hypot(nx, ny, nz);
      normal[pixel * 4] = Math.round((nx / length * 0.5 + 0.5) * 255);
      normal[pixel * 4 + 1] = Math.round((ny / length * 0.5 + 0.5) * 255);
      normal[pixel * 4 + 2] = Math.round((nz / length * 0.5 + 0.5) * 255);
      normal[pixel * 4 + 3] = 255;
    }
  }

  return {
    albedo: dataTexture(albedo, size, THREE.RGBAFormat, `${id}-albedo`, 'albedo', THREE.SRGBColorSpace),
    roughness: dataTexture(roughness, size, THREE.RGBAFormat, `${id}-roughness`, 'roughness'),
    height: dataTexture(height, size, THREE.RedFormat, `${id}-height`, 'height'),
    normal: dataTexture(normal, size, THREE.RGBAFormat, `${id}-normal`, 'normal'),
    ao: dataTexture(ao, size, THREE.RedFormat, `${id}-ao`, 'ao'),
  };
}

export function createSeoulProceduralMaps(seed, size = SEOUL_TEXTURE_SIZE) {
  const mapSets = {};
  const textures = [];
  Object.entries(PROFILES).forEach(([id, profile], index) => {
    const set = createMapSet(id, profile, seed + index * 104729, size);
    mapSets[id] = set;
    textures.push(...Object.values(set));
  });
  return {
    mapSets,
    textures,
    metadata: {
      deterministic: true,
      size,
      materialCount: Object.keys(mapSets).length,
      textureCount: textures.length,
      independentChannels: ['albedo', 'roughness', 'height', 'normal', 'ao'],
      frequencyBands: ['macro', 'meso', 'micro'],
    },
  };
}

export function applySeoulPbrMaps(
  material,
  maps,
  repeat,
  { normalScale = 0.42, bumpScale = 0.028, aoIntensity = 0.86 } = {},
) {
  Object.values(maps).forEach((texture) => {
    const configuredRepeat = texture.userData.uvRepeat;
    if (
      configuredRepeat
      && (configuredRepeat[0] !== repeat[0] || configuredRepeat[1] !== repeat[1])
    ) {
      throw new Error(
        `${texture.name} is shared by materials with conflicting UV repeats.`,
      );
    }
    if (!configuredRepeat) {
      texture.repeat.set(...repeat);
      texture.userData.uvRepeat = [...repeat];
    }
  });
  material.color.set(0xffffff);
  material.map = maps.albedo;
  material.roughnessMap = maps.roughness;
  material.bumpMap = maps.height;
  material.bumpScale = bumpScale;
  material.normalMap = maps.normal;
  material.normalScale.set(normalScale, normalScale);
  material.aoMap = maps.ao;
  material.aoMapIntensity = aoIntensity;
  material.needsUpdate = true;
}
