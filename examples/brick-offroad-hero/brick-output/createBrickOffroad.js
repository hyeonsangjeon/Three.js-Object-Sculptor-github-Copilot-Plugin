import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import variantConfig from './brick-variant-config.json' with { type: 'json' };

export const BRICK_STAGES = [
  'blockout',
  'structural-pass',
  'form-refinement',
  'material-pass',
  'surface-pass',
  'full',
];

export const BRICK_BASE_CONFIG = variantConfig[0];
export const BRICK_VARIANTS = variantConfig.slice(1);

const STAGE_LEVEL = Object.fromEntries(
  BRICK_STAGES.map((stage, index) => [stage, index]),
);

function hashString(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function hash2d(x, y, seed) {
  let value = Math.imul(x + seed * 19, 374761393)
    ^ Math.imul(y + seed * 29, 668265263);
  value = Math.imul(value ^ value >>> 13, 1274126177);
  return ((value ^ value >>> 16) >>> 0) / 4294967295;
}

function smoothstep(value) {
  return value * value * (3 - 2 * value);
}

function valueNoise(x, y, seed) {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const tx = smoothstep(x - x0);
  const ty = smoothstep(y - y0);
  const a = hash2d(x0, y0, seed);
  const b = hash2d(x0 + 1, y0, seed);
  const c = hash2d(x0, y0 + 1, seed);
  const d = hash2d(x0 + 1, y0 + 1, seed);
  return THREE.MathUtils.lerp(
    THREE.MathUtils.lerp(a, b, tx),
    THREE.MathUtils.lerp(c, d, tx),
    ty,
  );
}

function fractalNoise(x, y, seed) {
  let value = 0;
  let amplitude = 0.56;
  let frequency = 1;
  let total = 0;
  for (let octave = 0; octave < 4; octave += 1) {
    value += valueNoise(x * frequency, y * frequency, seed + octave * 113) * amplitude;
    total += amplitude;
    amplitude *= 0.5;
    frequency *= 2.11;
  }
  return value / total;
}

function createDataTexture(data, size, colorSpace = THREE.NoColorSpace) {
  const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(2.2, 2.2);
  texture.colorSpace = colorSpace;
  texture.anisotropy = 8;
  texture.needsUpdate = true;
  return texture;
}

function createSurfaceTextures(seed, color, kind, wear, dirtAmount, size = 512) {
  const base = new THREE.Color(color);
  const wearStrength = THREE.MathUtils.clamp(wear, 0, 1);
  const dirtStrength = THREE.MathUtils.clamp(dirtAmount, 0, 1);
  const pixels = size * size;
  const albedo = new Uint8Array(pixels * 4);
  const roughness = new Uint8Array(pixels * 4);
  const normal = new Uint8Array(pixels * 4);
  const ao = new Uint8Array(pixels * 4);
  const heightField = new Float32Array(pixels);
  const write = (target, offset, red, green, blue) => {
    target[offset] = Math.max(0, Math.min(255, Math.round(red)));
    target[offset + 1] = Math.max(0, Math.min(255, Math.round(green)));
    target[offset + 2] = Math.max(0, Math.min(255, Math.round(blue)));
    target[offset + 3] = 255;
  };

  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const index = y * size + x;
      const offset = index * 4;
      const u = x / size;
      const v = y / size;
      const macro = fractalNoise(u * 2.4, v * 2.2, seed + 17);
      const meso = fractalNoise(u * 13.0, v * 12.0, seed + 71);
      const micro = fractalNoise(u * 64.0, v * 59.0, seed + 149);
      const roughField = fractalNoise(u * 19.0, v * 17.0, seed + 307);
      const cavityField = fractalNoise(u * 8.0, v * 11.0, seed + 503);
      const scratch = Math.pow(
        Math.max(0, Math.sin((u * 71 + meso * 5.2) * Math.PI)),
        kind === 'rubber' ? 8 : 18,
      );
      const relief = THREE.MathUtils.clamp(
        0.42 + (macro - 0.5) * 0.22 + (meso - 0.5) * 0.12
          + (micro - 0.5) * 0.035
          - scratch * (0.015 + wearStrength * 0.09),
        0,
        1,
      );
      heightField[index] = relief;
      const dirt = Math.max(0, 0.56 - cavityField)
        * ((kind === 'paint' ? 0.08 : 0.05)
          + dirtStrength * 1.8
          + wearStrength * 0.2);
      const colorLift = 0.84 + macro * 0.18 + meso * 0.035
        - dirt
        - scratch * wearStrength * 0.18;
      write(
        albedo,
        offset,
        base.r * 255 * colorLift,
        base.g * 255 * colorLift,
        base.b * 255 * colorLift,
      );
      const rough = THREE.MathUtils.clamp(
        (kind === 'rubber' ? 0.73 : kind === 'metal' ? 0.36 : 0.52)
          + (roughField - 0.5) * 0.24
          + micro * 0.06
          + scratch * wearStrength * 0.12,
        0,
        1,
      );
      write(roughness, offset, rough * 255, rough * 255, rough * 255);
      const occlusion = THREE.MathUtils.clamp(
        0.78 + cavityField * 0.22 - dirt * 0.5,
        0,
        1,
      );
      write(ao, offset, occlusion * 255, occlusion * 255, occlusion * 255);
    }
  }

  for (let y = 0; y < size; y += 1) {
    const up = ((y - 1 + size) % size) * size;
    const down = ((y + 1) % size) * size;
    for (let x = 0; x < size; x += 1) {
      const left = (x - 1 + size) % size;
      const right = (x + 1) % size;
      const index = y * size + x;
      const dx = (heightField[y * size + right] - heightField[y * size + left]) * 2.8;
      const dy = (heightField[down + x] - heightField[up + x]) * 2.8;
      const vector = new THREE.Vector3(-dx, -dy, 1).normalize();
      write(
        normal,
        index * 4,
        (vector.x * 0.5 + 0.5) * 255,
        (vector.y * 0.5 + 0.5) * 255,
        (vector.z * 0.5 + 0.5) * 255,
      );
    }
  }

  return {
    albedo: createDataTexture(albedo, size, THREE.SRGBColorSpace),
    roughness: createDataTexture(roughness, size),
    normal: createDataTexture(normal, size),
    ao: createDataTexture(ao, size),
  };
}

function addSecondaryUvs(geometry) {
  const uv = geometry.getAttribute('uv');
  if (uv && !geometry.getAttribute('uv1')) geometry.setAttribute('uv1', uv.clone());
  if (uv && !geometry.getAttribute('uv2')) geometry.setAttribute('uv2', uv.clone());
  return geometry;
}

function createMaterials(seed, variant, detailed) {
  const textureSets = [];
  const create = (id, color, options = {}) => {
    const textures = detailed
      ? createSurfaceTextures(
        seed + hashString(id),
        color,
        options.kind ?? 'paint',
        variant.wear,
        variant.dirtAmount,
      )
      : null;
    if (textures) textureSets.push(textures);
    const parameters = {
      name: id,
      color: textures ? 0xffffff : color,
      map: textures?.albedo ?? null,
      roughness: options.roughness ?? variant.bodyRoughness,
      roughnessMap: textures?.roughness ?? null,
      metalness: options.metalness ?? 0,
      normalMap: textures?.normal ?? null,
      normalScale: new THREE.Vector2(options.normalScale ?? 0.24, options.normalScale ?? 0.24),
      aoMap: textures?.ao ?? null,
      aoMapIntensity: options.ao ?? 0.45,
      transparent: options.transparent ?? false,
      opacity: options.opacity ?? 1,
      side: options.side ?? THREE.FrontSide,
      emissive: options.emissive ?? 0x000000,
      emissiveIntensity: options.emissiveIntensity ?? 0,
    };
    if (options.physical) {
      parameters.transmission = options.transmission ?? 0;
      parameters.thickness = options.thickness ?? 0.08;
      parameters.ior = options.ior ?? 1.48;
    }
    const MaterialType = options.physical
      ? THREE.MeshPhysicalMaterial
      : THREE.MeshStandardMaterial;
    const material = new MaterialType(parameters);
    material.userData.channelIds = textures
      ? {
        albedo: `${id}-albedo`,
        roughness: `${id}-roughness`,
        heightField: `${id}-height-field-derived`,
        normal: `${id}-normal`,
        ambientOcclusion: `${id}-ao`,
      }
      : {};
    material.userData.surfaceWear = variant.wear;
    material.userData.surfaceDirtAmount = variant.dirtAmount;
    return material;
  };

  const materials = {
    body: create('olive-body', variant.body, { roughness: variant.bodyRoughness }),
    bodyDark: create('olive-shadow-panels', variant.bodyDark, { roughness: 0.66 }),
    roof: create('light-roof', variant.roof, { roughness: variant.roofRoughness }),
    trim: create('black-structural-trim', variant.trim, {
      roughness: variant.trimRoughness,
    }),
    rubber: create('tire-rubber', variant.rubber, {
      kind: 'rubber',
      roughness: variant.rubberRoughness,
      normalScale: 0.36,
    }),
    metal: create('dark-metal', '#343a38', {
      kind: 'metal',
      roughness: 0.38,
      metalness: 0.82,
    }),
    brightMetal: create('recovery-metal', '#8b8d88', {
      kind: 'metal',
      roughness: 0.28,
      metalness: 0.94,
    }),
    accent: create('warm-recovery-accent', variant.accent, {
      roughness: variant.accentRoughness,
      metalness: 0.16,
    }),
    dust: create('seam-dirt', variant.dust, { roughness: 0.92 }),
    glass: create('smoky-glass', variant.glass, {
      physical: true,
      roughness: variant.glassRoughness,
      metalness: 0.05,
      transparent: true,
      opacity: 0.68,
      transmission: 0.12,
      thickness: 0.07,
      side: THREE.DoubleSide,
    }),
    lamp: create('warm-lamp', variant.lamp, {
      roughness: variant.lampRoughness,
      transparent: true,
      opacity: 0.92,
      emissive: new THREE.Color('#ff9b42'),
      emissiveIntensity: 2.0,
    }),
    redLamp: create('rear-lamp', '#9e2d22', {
      roughness: 0.26,
      emissive: new THREE.Color('#8c1b13'),
      emissiveIntensity: 1.1,
    }),
  };
  return { materials, textureSets };
}

function resolveVariant(value) {
  if (typeof value === 'string') {
    if (value === 'base' || value === BRICK_BASE_CONFIG.id) {
      return BRICK_BASE_CONFIG;
    }
    return BRICK_VARIANTS.find((variant) => variant.id === value) ?? BRICK_VARIANTS[0];
  }
  const index = Number.isFinite(value) ? Number(value) : 0;
  return BRICK_VARIANTS[
    ((Math.trunc(index) % BRICK_VARIANTS.length) + BRICK_VARIANTS.length)
      % BRICK_VARIANTS.length
  ];
}

export function createBrickOffroad(options = {}) {
  const started = performance.now();
  const seed = options.seed ?? 20260712;
  const variant = resolveVariant(options.variant ?? 0);
  const stage = BRICK_STAGES.includes(options.stage) ? options.stage : 'full';
  const stageLevel = STAGE_LEVEL[stage];
  const detailedMaterials = stageLevel >= STAGE_LEVEL['material-pass'];
  const { materials, textureSets } = createMaterials(seed, variant, detailedMaterials);
  const root = new THREE.Group();
  root.name = 'brick-offroad-root';

  const runtime = {
    nodes: {},
    meshes: {},
    sockets: {},
    colliders: {},
    destructionGroups: {},
    wheelPivots: [],
    steeringPivots: [],
    suspensionAnchors: [],
  };
  const resources = {
    geometries: new Set(),
    materials: new Set(Object.values(materials)),
    textures: new Set(),
    instancedMeshes: new Set(),
  };
  for (const set of textureSets) {
    for (const texture of Object.values(set)) resources.textures.add(texture);
  }
  runtime.resources = resources;

  const registerNode = (id, node, parent = root) => {
    node.name = id;
    node.userData.sculptId = id;
    parent.add(node);
    runtime.nodes[id] = node;
    return node;
  };
  const registerMesh = (id, mesh, parent = root, destructionGroup = 'body-shell') => {
    mesh.name = id;
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    addSecondaryUvs(mesh.geometry);
    resources.geometries.add(mesh.geometry);
    if (mesh.isInstancedMesh) resources.instancedMeshes.add(mesh);
    parent.add(mesh);
    runtime.meshes[id] = mesh;
    runtime.destructionGroups[destructionGroup] ??= [];
    runtime.destructionGroups[destructionGroup].push(mesh);
    return mesh;
  };
  const group = (id, parent = root) => registerNode(id, new THREE.Group(), parent);
  const roundedBox = (id, dimensions, material, parent, position, radius = 0.08) => {
    const geometry = new RoundedBoxGeometry(
      dimensions[0],
      dimensions[1],
      dimensions[2],
      3,
      Math.min(radius, ...dimensions.map((value) => value * 0.22)),
    );
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(...position);
    return registerMesh(id, mesh, parent);
  };
  const box = (id, dimensions, material, parent, position) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...dimensions), material);
    mesh.position.set(...position);
    return registerMesh(id, mesh, parent);
  };
  const cylinder = (
    id,
    radius,
    length,
    material,
    parent,
    position,
    rotation = [0, 0, 0],
    radialSegments = 16,
  ) => {
    const mesh = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, length, radialSegments),
      material,
    );
    mesh.position.set(...position);
    mesh.rotation.set(...rotation);
    return registerMesh(id, mesh, parent);
  };
  const socket = (id, parent, position) => {
    const node = new THREE.Object3D();
    node.position.set(...position);
    node.name = id;
    node.userData.socketId = id;
    parent.add(node);
    runtime.sockets[id] = node;
    return node;
  };
  const collider = (id, parentId, type, center, size) => {
    runtime.colliders[id] = {
      id,
      parentId,
      type,
      center: [...center],
      size: [...size],
      isTrigger: false,
    };
  };
  const cylinderBetween = (id, start, end, radius, material, parent) => {
    const startVector = new THREE.Vector3(...start);
    const endVector = new THREE.Vector3(...end);
    const direction = endVector.clone().sub(startVector);
    const mesh = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, direction.length(), 12),
      material,
    );
    mesh.position.copy(startVector).add(endVector).multiplyScalar(0.5);
    mesh.quaternion.setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      direction.clone().normalize(),
    );
    return registerMesh(id, mesh, parent, 'structural-trim');
  };

  const chassis = group('chassis');
  roundedBox('chassis-frame', [6.25, 0.42, 2.45], materials.trim, chassis, [0, 1.16, 0], 0.1);
  roundedBox('lower-body', [5.75, 0.72, 2.55], materials.bodyDark, chassis, [0.05, 1.52, 0], 0.14);
  collider('chassis-collider', 'chassis', 'box', [0, 1.35, 0], [6.25, 1.1, 2.55]);

  const hoodPivot = group('hood-pivot', chassis);
  hoodPivot.position.set(-1.2, 2.05, 0);
  roundedBox('hood-main', [2.6, 0.5, 2.42], materials.body, hoodPivot, [-1.35, 0, 0], 0.16);
  socket('hood-hinge-socket', hoodPivot, [-0.05, 0.05, 0]);

  const cabin = group('cabin', chassis);
  const utility = group('rear-utility-body', chassis);
  if (stageLevel < STAGE_LEVEL['form-refinement']) {
    roundedBox('cabin-blockout', [2.25, 1.6, 2.32], materials.body, cabin, [0.05, 2.52, 0], 0.13);
    roundedBox('utility-blockout', [2.0, 1.25, 2.45], materials.body, utility, [2.05, 2.25, 0], 0.12);
  } else {
    roundedBox('cabin-lower-shell', [2.25, 0.78, 2.32], materials.body, cabin, [0.05, 2.1, 0], 0.1);
    roundedBox('utility-lower-shell', [2.0, 0.82, 2.45], materials.body, utility, [2.05, 2.0, 0], 0.1);
    for (const side of [-1, 1]) {
      box(
        `cabin-rear-pillar-${side}`,
        [0.18, 1.12, 0.16],
        materials.trim,
        cabin,
        [1.02, 2.75, side * 1.12],
      );
      box(
        `utility-rear-pillar-${side}`,
        [0.18, 0.9, 0.16],
        materials.trim,
        utility,
        [2.9, 2.62, side * 1.17],
      );
    }
  }

  const wheelLayout = [
    ['front-left', -2.22, 1],
    ['front-right', -2.22, -1],
    ['rear-left', 2.12, 1],
    ['rear-right', 2.12, -1],
  ];
  const wheelRadius = 0.79;
  const trackZ = 1.48;
  if (variant.treadCount % wheelLayout.length !== 0) {
    throw new Error(
      `Variant ${variant.id} treadCount must divide evenly across four wheels.`,
    );
  }
  for (const [wheelIndex, [id, x, side]] of wheelLayout.entries()) {
    const suspension = group(`${id}-suspension-anchor`, chassis);
    suspension.position.set(x, 1.25, side * 1.06);
    runtime.suspensionAnchors.push(suspension);
    const steering = id.startsWith('front')
      ? group(`${id}-steering-pivot`, suspension)
      : suspension;
    if (steering !== suspension) runtime.steeringPivots.push(steering);
    const wheelPivot = group(`${id}-wheel-pivot`, steering);
    wheelPivot.position.set(0, -0.42, side * (trackZ - 1.06));
    runtime.wheelPivots.push(wheelPivot);

    const tireGeometry = new THREE.TorusGeometry(0.57, 0.22, 14, 40);
    const tire = new THREE.Mesh(tireGeometry, materials.rubber);
    registerMesh(`${id}-tire`, tire, wheelPivot, 'wheel-system');
    const hub = cylinder(
      `${id}-hub`,
      0.31,
      0.26,
      materials.metal,
      wheelPivot,
      [0, 0, 0],
      [Math.PI / 2, 0, 0],
      24,
    );
    hub.position.z = side * 0.02;
    cylinder(
      `${id}-hub-cap`,
      0.1,
      0.29,
      materials.brightMetal,
      wheelPivot,
      [0, 0, side * 0.03],
      [Math.PI / 2, 0, 0],
      16,
    );

    if (stageLevel >= STAGE_LEVEL['form-refinement']) {
      const spokeGeometry = new THREE.BoxGeometry(0.34, 0.065, 0.28);
      const spokes = new THREE.InstancedMesh(spokeGeometry, materials.trim, 8);
      const matrix = new THREE.Matrix4();
      const quaternion = new THREE.Quaternion();
      const scale = new THREE.Vector3(1, 1, 1);
      for (let index = 0; index < 8; index += 1) {
        const angle = index / 8 * Math.PI * 2;
        quaternion.setFromEuler(new THREE.Euler(0, 0, angle));
        matrix.compose(
          new THREE.Vector3(Math.cos(angle) * 0.17, Math.sin(angle) * 0.17, side * 0.02),
          quaternion,
          scale,
        );
        spokes.setMatrixAt(index, matrix);
      }
      spokes.instanceMatrix.needsUpdate = true;
      registerMesh(`${id}-hub-spokes`, spokes, wheelPivot, 'wheel-system');
    }

    if (stageLevel >= STAGE_LEVEL['surface-pass']) {
      const treadCount = variant.treadCount / wheelLayout.length;
      const treadGeometry = new RoundedBoxGeometry(0.24, 0.34, 0.18, 2, 0.035);
      const treads = new THREE.InstancedMesh(treadGeometry, materials.rubber, treadCount);
      const matrix = new THREE.Matrix4();
      const quaternion = new THREE.Quaternion();
      const scale = new THREE.Vector3(1, 1, 1);
      for (let index = 0; index < treadCount; index += 1) {
        const angle = index / treadCount * Math.PI * 2;
        quaternion.setFromEuler(new THREE.Euler(0, 0, angle));
        matrix.compose(
          new THREE.Vector3(Math.cos(angle) * wheelRadius, Math.sin(angle) * wheelRadius, 0),
          quaternion,
          scale,
        );
        treads.setMatrixAt(index, matrix);
      }
      treads.instanceMatrix.needsUpdate = true;
      registerMesh(`${id}-tread-blocks`, treads, wheelPivot, 'wheel-system');
    }
  }

  if (stageLevel >= STAGE_LEVEL['structural-pass']) {
    cylinder('front-axle', 0.09, 2.72, materials.metal, chassis, [-2.22, 0.85, 0], [Math.PI / 2, 0, 0]);
    cylinder('rear-axle', 0.1, 2.72, materials.metal, chassis, [2.12, 0.85, 0], [Math.PI / 2, 0, 0]);
    cylinderBetween('front-left-shock', [-2.22, 0.86, 1.16], [-2.05, 1.46, 0.96], 0.055, materials.accent, chassis);
    cylinderBetween('front-right-shock', [-2.22, 0.86, -1.16], [-2.05, 1.46, -0.96], 0.055, materials.accent, chassis);
    cylinderBetween('rear-left-shock', [2.12, 0.86, 1.16], [1.95, 1.46, 0.96], 0.055, materials.accent, chassis);
    cylinderBetween('rear-right-shock', [2.12, 0.86, -1.16], [1.95, 1.46, -0.96], 0.055, materials.accent, chassis);

    for (const [id, x, side] of wheelLayout) {
      const arch = new THREE.Mesh(
        new THREE.TorusGeometry(0.86, 0.105, 8, 28, Math.PI),
        materials.body,
      );
      arch.position.set(x, 1.58, side * 1.3);
      arch.rotation.y = side > 0 ? 0 : Math.PI;
      registerMesh(`${id}-fender-arch`, arch, chassis, 'body-shell');
      roundedBox(
        `${id}-fender-shoulder`,
        [1.85, 0.3, 0.17],
        materials.body,
        chassis,
        [x, 1.64, side * 1.27],
        0.07,
      );
    }

    const frontAssembly = group('front-bumper-pivot', chassis);
    frontAssembly.position.set(-3.1, 1.0, 0);
    roundedBox('front-bumper', [0.32, 0.42, 2.62], materials.trim, frontAssembly, [0, 0, 0], 0.08);
    roundedBox('front-skid', [0.7, 0.36, 1.92], materials.brightMetal, frontAssembly, [-0.04, -0.3, 0], 0.06).rotation.z = -0.2;
    roundedBox('rear-bumper', [0.34, 0.38, 2.48], materials.trim, chassis, [3.06, 1.05, 0], 0.08);
    socket('front-recovery-socket', frontAssembly, [-0.19, -0.02, 0]);
    socket('rear-tow-socket', chassis, [3.25, 1.0, 0]);

    for (const [sideName, side] of [['left', 1], ['right', -1]]) {
      const frontDoor = group(`${sideName}-door-pivot`, cabin);
      frontDoor.position.set(-0.88, 2.25, side * 1.19);
      roundedBox(
        `${sideName}-door-panel`,
        [0.82, 1.35, 0.1],
        materials.body,
        frontDoor,
        [0.41, 0, 0],
        0.06,
      );
      socket(`${sideName}-door-hinge`, frontDoor, [0, 0, 0]);

      const rearDoor = group(`${sideName}-rear-door-pivot`, cabin);
      rearDoor.position.set(0, 2.25, side * 1.19);
      roundedBox(
        `${sideName}-rear-door-panel`,
        [0.84, 1.35, 0.1],
        materials.body,
        rearDoor,
        [0.42, 0, 0],
        0.06,
      );
      socket(`${sideName}-rear-door-hinge`, rearDoor, [0, 0, 0]);
      collider(
        `${sideName}-door-collider`,
        `${sideName}-door-pivot`,
        'box',
        [0.41, 0, 0],
        [0.82, 1.35, 0.1],
      );
      collider(
        `${sideName}-rear-door-collider`,
        `${sideName}-rear-door-pivot`,
        'box',
        [0.42, 0, 0],
        [0.84, 1.35, 0.1],
      );
    }

    const tailgate = group('tailgate-pivot', utility);
    tailgate.position.set(3.02, 1.64, 0);
    roundedBox('tailgate-panel', [0.12, 1.12, 2.2], materials.body, tailgate, [0, 0.56, 0], 0.05);
    socket('tailgate-hinge', tailgate, [0, 0, 0]);
  }

  if (stageLevel >= STAGE_LEVEL['form-refinement']) {
    roundedBox('hood-raised-panel', [1.75, 0.13, 1.56], materials.bodyDark, hoodPivot, [-1.38, 0.3, 0], 0.07);
    for (const side of [-1, 1]) {
      roundedBox(
        `hood-vent-${side > 0 ? 'left' : 'right'}`,
        [1.05, 0.08, 0.22],
        materials.trim,
        hoodPivot,
        [-1.32, 0.34, side * 0.84],
        0.025,
      );
    }
    roundedBox('windshield-glass', [0.08, 1.1, 1.92], materials.glass, cabin, [-1.16, 2.72, 0], 0.035).rotation.z = -0.16;
    cylinderBetween('windshield-left-a-pillar', [-1.29, 2.17, 1.08], [-1.04, 3.3, 1.08], 0.075, materials.trim, cabin);
    cylinderBetween('windshield-right-a-pillar', [-1.29, 2.17, -1.08], [-1.04, 3.3, -1.08], 0.075, materials.trim, cabin);
    cylinderBetween('windshield-top-bar', [-1.04, 3.3, -1.08], [-1.04, 3.3, 1.08], 0.065, materials.trim, cabin);
    cylinderBetween('windshield-cowl-bar', [-1.29, 2.17, -1.08], [-1.29, 2.17, 1.08], 0.065, materials.trim, cabin);
    for (const side of [-1, 1]) {
      const sideName = side > 0 ? 'left' : 'right';
      const frontDoor = runtime.nodes[`${sideName}-door-pivot`];
      const rearDoor = runtime.nodes[`${sideName}-rear-door-pivot`];
      roundedBox(
        `front-side-window-${sideName}`,
        [0.82, 0.82, 0.07],
        materials.glass,
        frontDoor,
        [0.4, 0.53, 0],
        0.04,
      );
      roundedBox(
        `rear-side-window-${sideName}`,
        [0.72, 0.82, 0.07],
        materials.glass,
        rearDoor,
        [0.42, 0.53, 0],
        0.04,
      );
      box(
        `b-pillar-${side > 0 ? 'left' : 'right'}`,
        [0.1, 0.96, 0.1],
        materials.trim,
        cabin,
        [0, 2.76, side * 1.22],
      );
      roundedBox(
        `side-mirror-${sideName}`,
        [0.34, 0.25, 0.22],
        materials.trim,
        frontDoor,
        [0.06, 0.37, side * 0.24],
        0.05,
      );
      cylinderBetween(
        `mirror-arm-${sideName}`,
        [0.16, 0.25, side * 0.01],
        [0.06, 0.33, side * 0.17],
        0.035,
        materials.trim,
        frontDoor,
      );
      roundedBox(
        `utility-window-${side > 0 ? 'left' : 'right'}`,
        [1.3, 0.72, 0.07],
        materials.glass,
        utility,
        [2.04, 2.64, side * 1.23],
        0.04,
      );
    }
    roundedBox('light-roof', [2.82, 0.24, 2.58], materials.roof, cabin, [0.1, 3.55, 0], 0.14);
    roundedBox('rear-light-roof', [1.86, 0.2, 2.46], materials.roof, utility, [2.14, 3.2, 0], 0.11);

    const grille = group('grille-system', chassis);
    grille.position.set(-3.02, 1.8, 0);
    roundedBox('grille-surround', [0.18, 0.78, 2.22], materials.body, grille, [0, 0, 0], 0.08);
    for (let index = -3; index <= 3; index += 1) {
      box(`grille-slat-${index + 3}`, [0.09, 0.55, 0.085], materials.trim, grille, [-0.1, 0, index * 0.22]);
    }
    for (const side of [-1, 1]) {
      cylinder(
        `headlight-${side > 0 ? 'left' : 'right'}`,
        0.25,
        0.18,
        materials.lamp,
        grille,
        [-0.25, 0.08, side * 0.86],
        [0, 0, Math.PI / 2],
        24,
      );
      cylinder(
        `front-fastener-${side > 0 ? 'left' : 'right'}`,
        0.055,
        0.15,
        materials.brightMetal,
        grille,
        [-0.13, 0.32, side * 0.62],
        [0, 0, Math.PI / 2],
      );
    }
  }

  if (stageLevel >= STAGE_LEVEL['surface-pass']) {
    const studGeometry = new THREE.CylinderGeometry(0.075, 0.075, 0.055, 16);
    const studCount = variant.studCount;
    const studs = new THREE.InstancedMesh(studGeometry, materials.bodyDark, studCount);
    const matrix = new THREE.Matrix4();
    const studPositions = [];
    for (let row = 0; row < 4; row += 1) {
      for (let column = 0; column < 11; column += 1) {
        studPositions.push([-3.08 + column * 0.225, 2.36, -0.75 + row * 0.5]);
      }
    }
    for (let row = 0; row < 5; row += 1) {
      for (let column = 0; column < 9; column += 1) {
        studPositions.push([-0.82 + column * 0.22, 3.69, -0.8 + row * 0.4]);
      }
    }
    if (studCount > studPositions.length) {
      throw new Error(
        `Variant ${variant.id} studCount exceeds ${studPositions.length} authored positions.`,
      );
    }
    for (let studIndex = 0; studIndex < studCount; studIndex += 1) {
      matrix.makeTranslation(...studPositions[studIndex]);
      studs.setMatrixAt(studIndex, matrix);
    }
    studs.instanceMatrix.needsUpdate = true;
    registerMesh('body-stud-language', studs, chassis, 'surface-details');

    const fastenerGeometry = new THREE.CylinderGeometry(0.045, 0.045, 0.04, 12);
    fastenerGeometry.rotateX(Math.PI / 2);
    const fasteners = new THREE.InstancedMesh(fastenerGeometry, materials.brightMetal, 20);
    let index = 0;
    for (const side of [-1, 1]) {
      for (const x of [-2.55, -1.75, -0.72, 0.05, 0.72, 1.55, 2.35, 2.75]) {
        matrix.makeTranslation(x, 1.9 + (index % 2) * 0.42, side * 1.32);
        fasteners.setMatrixAt(index, matrix);
        index += 1;
      }
      for (const x of [-0.65, 0.65]) {
        matrix.makeTranslation(x, 2.12, side * 1.34);
        fasteners.setMatrixAt(index, matrix);
        index += 1;
      }
    }
    fasteners.instanceMatrix.needsUpdate = true;
    registerMesh('panel-fasteners', fasteners, chassis, 'surface-details');

    for (const side of [-1, 1]) {
      const sideName = side > 0 ? 'left' : 'right';
      const frontDoor = runtime.nodes[`${sideName}-door-pivot`];
      const rearDoor = runtime.nodes[`${sideName}-rear-door-pivot`];
      box(`rocker-step-${side}`, [3.15, 0.16, 0.32], materials.trim, chassis, [0.55, 1.18, side * 1.48]);
      roundedBox(
        `front-door-handle-${sideName}`,
        [0.34, 0.1, 0.09],
        materials.trim,
        frontDoor,
        [0.68, 0.09, side * 0.12],
        0.025,
      );
      roundedBox(
        `rear-door-handle-${sideName}`,
        [0.32, 0.1, 0.09],
        materials.trim,
        rearDoor,
        [0.7, 0.09, side * 0.12],
        0.025,
      );
      for (const [doorId, door] of [
        [`${sideName}-front`, frontDoor],
        [`${sideName}-rear`, rearDoor],
      ]) {
        for (const y of [-0.38, 0.38]) {
          roundedBox(
            `door-hinge-${doorId}-${y}`,
            [0.16, 0.24, 0.12],
            materials.trim,
            door,
            [0.03, y, side * 0.11],
            0.03,
          );
        }
      }
    }

    const rack = group('roof-rack', chassis);
    for (const side of [-1, 1]) {
      cylinderBetween(`rack-rail-${side}`, [-1.0, 3.86, side * 1.03], [2.75, 3.5, side * 1.03], 0.055, materials.trim, rack);
    }
    for (const x of [-0.8, 0.2, 1.2, 2.2]) {
      cylinderBetween(`rack-crossbar-${x}`, [x, 3.75 - x * 0.09, -1.03], [x, 3.75 - x * 0.09, 1.03], 0.052, materials.trim, rack);
    }
    roundedBox('roof-cargo-case', [1.2, 0.42, 1.18], materials.trim, rack, [0.92, 4.05, -0.45], 0.08);
    roundedBox('cargo-case-latch', [0.18, 0.12, 0.42], materials.accent, rack, [0.28, 4.02, -0.45], 0.03);
    roundedBox('recovery-board-stack', [1.55, 0.2, 0.62], materials.roof, rack, [1.02, 4.08, 0.6], 0.06);
    const boardHoleGeometry = new THREE.CylinderGeometry(0.065, 0.065, 0.24, 12);
    boardHoleGeometry.rotateX(Math.PI / 2);
    const boardHoles = new THREE.InstancedMesh(boardHoleGeometry, materials.trim, 6);
    for (let boardHole = 0; boardHole < 6; boardHole += 1) {
      matrix.makeTranslation(0.45 + boardHole * 0.22, 4.11, 0.6);
      boardHoles.setMatrixAt(boardHole, matrix);
    }
    boardHoles.instanceMatrix.needsUpdate = true;
    registerMesh('recovery-board-holes', boardHoles, rack, 'surface-details');
    const roofLampGeometry = new THREE.CylinderGeometry(0.12, 0.12, 0.16, 18);
    roofLampGeometry.rotateZ(Math.PI / 2);
    const roofLamps = new THREE.InstancedMesh(
      roofLampGeometry,
      materials.lamp,
      variant.roofLampCount,
    );
    for (let lampIndex = 0; lampIndex < variant.roofLampCount; lampIndex += 1) {
      const z = (lampIndex - (variant.roofLampCount - 1) * 0.5) * 0.28;
      matrix.makeTranslation(-0.72, 3.96, z);
      roofLamps.setMatrixAt(lampIndex, matrix);
    }
    roofLamps.instanceMatrix.needsUpdate = true;
    registerMesh('roof-lamp-system', roofLamps, rack, 'surface-details');
    socket('roof-front-socket', rack, [-0.85, 3.9, 0]);
    socket('roof-cargo-socket', rack, [1.0, 3.93, 0]);
    socket('roof-rear-socket', rack, [2.62, 3.55, 0]);

    roundedBox('front-winch', [0.32, 0.32, 0.72], materials.accent, chassis, [-3.24, 1.14, 0], 0.08);
    cylinder('winch-drum', 0.13, 0.84, materials.brightMetal, chassis, [-3.4, 1.14, 0], [Math.PI / 2, 0, 0], 20);
    for (const side of [-1, 1]) {
      const hook = new THREE.Mesh(
        new THREE.TorusGeometry(0.14, 0.04, 8, 16, Math.PI * 1.4),
        materials.accent,
      );
      hook.position.set(-3.4, 0.82, side * 0.62);
      hook.rotation.x = Math.PI / 2;
      registerMesh(`recovery-hook-${side}`, hook, chassis, 'recovery-hardware');
      roundedBox(`rear-lamp-${side}`, [0.13, 0.3, 0.25], materials.redLamp, utility, [3.08, 2.3, side * 0.9], 0.04);
    }
    box('hood-left-seam', [2.0, 0.025, 0.025], materials.dust, hoodPivot, [-1.4, 0.31, 0.84]);
    box('hood-right-seam', [2.0, 0.025, 0.025], materials.dust, hoodPivot, [-1.4, 0.31, -0.84]);
    box('left-door-seam', [0.025, 1.16, 0.02], materials.dust, cabin, [-0.68, 2.23, 1.3]);
    box('right-door-seam', [0.025, 1.16, 0.02], materials.dust, cabin, [-0.68, 2.23, -1.3]);
  }

  for (const [id, colliderData] of Object.entries(runtime.colliders)) {
    colliderData.userDataSafe = true;
    runtime.colliders[id] = colliderData;
  }
  root.userData.sculptRuntime = {
    schemaVersion: '1.0',
    seed,
    stage,
    variantId: variant.id,
    nodeIds: Object.keys(runtime.nodes),
    meshIds: Object.keys(runtime.meshes),
    socketIds: Object.keys(runtime.sockets),
    colliderIds: Object.keys(runtime.colliders),
    destructionGroupIds: Object.keys(runtime.destructionGroups),
  };
  root.userData.sculptDNA = {
    configuration: variant.id,
    topologyInvariant: 'brick-offroad-four-wheel-v1',
    seed,
    wear: variant.wear,
    dirtAmount: variant.dirtAmount,
  };
  root.userData.variantProvenance = {
    source: 'brick-offroad',
    variantId: variant.id,
    deterministic: true,
    evidencePolicy: 'evidence-backed-production',
  };

  let meshCount = 0;
  let triangleCount = 0;
  root.traverse((object) => {
    if (!object.isMesh) return;
    meshCount += 1;
    const geometry = object.geometry;
    const geometryTriangles = geometry.index
      ? geometry.index.count / 3
      : (geometry.getAttribute('position')?.count ?? 0) / 3;
    triangleCount += geometryTriangles * (object.isInstancedMesh ? object.count : 1);
  });
  const generationMs = performance.now() - started;
  const baseWheelY = runtime.suspensionAnchors.map((anchor) => anchor.position.y);
  const lampMaterials = [materials.lamp, materials.redLamp];
  let disposed = false;

  return {
    root,
    runtime,
    variant,
    stats: {
      generationMs,
      meshes: meshCount,
      triangles: Math.round(triangleCount),
      sceneDrawables: meshCount,
      wheels: runtime.wheelPivots.length,
      treadInstances: stageLevel >= STAGE_LEVEL['surface-pass'] ? variant.treadCount : 0,
      treadsPerWheel: stageLevel >= STAGE_LEVEL['surface-pass']
        ? variant.treadCount / wheelLayout.length
        : 0,
      studInstances: stageLevel >= STAGE_LEVEL['surface-pass'] ? variant.studCount : 0,
      roofLampInstances: stageLevel >= STAGE_LEVEL['surface-pass']
        ? variant.roofLampCount
        : 0,
      importedMeshes: 0,
      generatedTextureResolution: detailedMaterials ? 512 : 0,
      generatedTextureCount: resources.textures.size,
      wear: variant.wear,
      dirtAmount: variant.dirtAmount,
      configurationId: variant.id,
      stage,
    },
    update(elapsedSeconds) {
      const suspensionPhase = elapsedSeconds * 1.1;
      runtime.suspensionAnchors.forEach((anchor, index) => {
        anchor.position.y = baseWheelY[index]
          + Math.sin(suspensionPhase + index * 1.7) * 0.006;
      });
      runtime.steeringPivots.forEach((pivot, index) => {
        pivot.rotation.y = Math.sin(elapsedSeconds * 0.42 + index * 0.18) * 0.035;
      });
      const pulse = 1.75 + Math.sin(elapsedSeconds * 1.8) * 0.18;
      lampMaterials.forEach((material, index) => {
        material.emissiveIntensity = pulse * (index === 0 ? 1 : 0.55);
      });
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      resources.instancedMeshes.forEach((mesh) => mesh.dispose());
      resources.geometries.forEach((geometry) => geometry.dispose());
      resources.materials.forEach((material) => material.dispose());
      resources.textures.forEach((texture) => texture.dispose());
    },
  };
}
