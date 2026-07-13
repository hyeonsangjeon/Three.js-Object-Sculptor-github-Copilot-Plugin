import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import {
  applySeoulPbrMaps,
  createSeoulProceduralMaps,
} from './createProceduralMaterials.js';

export const SEOUL_STAGES = Object.freeze([
  'blockout',
  'structural-pass',
  'form-refinement',
  'material-pass',
  'surface-pass',
  'lighting-pass',
  'interaction-pass',
  'optimization-pass',
]);
export const SEOUL_DEFAULT_SEED = 20260712;
export const SEOUL_REFERENCE_CAMERA_VIEW = Object.freeze({
  position: Object.freeze([-68, 43, -65]),
  target: Object.freeze([2, 4, 42]),
  rotation: Object.freeze([
    -2.79207146259973,
    -0.5511221457213583,
    -2.953000092782706,
  ]),
});

const MACRO_GROUP_IDS = Object.freeze([
  'foreground',
  'palace-axis',
  'palace-side',
  'vegetation',
  'city',
  'mountain',
]);

function seedValue(seed) {
  if (Number.isFinite(seed)) return Number(seed) >>> 0;
  const seedText = String(seed);
  if (/^(?:0|[1-9]\d*)$/.test(seedText)) {
    return Number(BigInt(seedText) & 0xFFFFFFFFn);
  }
  let hash = 2166136261;
  for (const character of seedText) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function seededRandom(seed) {
  let state = seedValue(seed);
  return () => {
    state += 0x6D2B79F5;
    let value = state;
    value = Math.imul(value ^ value >>> 15, value | 1);
    value ^= value + Math.imul(value ^ value >>> 7, value | 61);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}

function createRoofSurfaceGeometry(width, depth, roofHeight, cornerLift, centerSag) {
  const columns = 12;
  const rows = 8;
  const vertices = [];
  const uvs = [];
  const indices = [];
  for (let row = 0; row <= rows; row += 1) {
    const zRatio = row / rows * 2 - 1;
    for (let column = 0; column <= columns; column += 1) {
      const xRatio = column / columns * 2 - 1;
      const absX = Math.abs(xRatio);
      const absZ = Math.abs(zRatio);
      const eaveCurve = cornerLift * absX ** 2 - centerSag * (1 - absX ** 2);
      const hipEnvelope = Math.min(1, Math.max(0, (1 - absX) / 0.26));
      const pitch = roofHeight * (1 - absZ) * hipEnvelope;
      vertices.push(
        xRatio * width * 0.5,
        eaveCurve + pitch,
        zRatio * depth * 0.5,
      );
      uvs.push(column / columns, row / rows);
    }
  }
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const a = row * (columns + 1) + column;
      const b = a + 1;
      const c = a + columns + 1;
      const d = c + 1;
      indices.push(a, c, b, b, c, d);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function curvedEavePoints(width, depth, y, side, cornerLift, centerSag) {
  return Array.from({ length: 17 }, (_, index) => {
    const ratio = index / 16 * 2 - 1;
    const lift = cornerLift * Math.abs(ratio) ** 2 - centerSag * (1 - ratio ** 2);
    return new THREE.Vector3(ratio * width * 0.5, y + lift, side * depth * 0.5);
  });
}

function sideEavePoints(width, depth, y, side, cornerLift, centerSag) {
  return Array.from({ length: 13 }, (_, index) => {
    const ratio = index / 12 * 2 - 1;
    const lift = cornerLift * Math.abs(ratio) ** 2 - centerSag * 0.35 * (1 - ratio ** 2);
    return new THREE.Vector3(side * width * 0.5, y + lift, ratio * depth * 0.5);
  });
}

function cylinderBetween(start, end, radius, radialSegments = 7) {
  const direction = new THREE.Vector3().subVectors(end, start);
  const midpoint = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);
  const geometry = new THREE.CylinderGeometry(radius, radius, direction.length(), radialSegments);
  const quaternion = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    direction.normalize(),
  );
  geometry.applyMatrix4(new THREE.Matrix4().compose(
    midpoint,
    quaternion,
    new THREE.Vector3(1, 1, 1),
  ));
  return geometry;
}

function createRoofRidgeGeometry(width, depth, roofHeight, cornerLift, centerSag) {
  const ridgeY = roofHeight - centerSag + 0.08;
  const ridgeHalf = width * 0.24;
  const ridgeEnds = [
    new THREE.Vector3(-ridgeHalf, ridgeY, 0),
    new THREE.Vector3(ridgeHalf, ridgeY, 0),
  ];
  const geometries = [
    cylinderBetween(ridgeEnds[0], ridgeEnds[1], 0.13, 8),
  ];
  for (const side of [-1, 1]) {
    const ridgeEnd = ridgeEnds[side < 0 ? 0 : 1];
    for (const frontOrRear of [-1, 1]) {
      geometries.push(cylinderBetween(
        ridgeEnd,
        new THREE.Vector3(
          side * width * 0.49,
          cornerLift + 0.04,
          frontOrRear * depth * 0.49,
        ),
        0.095,
        7,
      ));
      const corner = new THREE.Vector3(
        side * width * 0.49,
        cornerLift + 0.04,
        frontOrRear * depth * 0.49,
      );
      geometries.push(cylinderBetween(
        corner,
        new THREE.Vector3(
          side * width * 0.515,
          cornerLift + 0.31,
          frontOrRear * depth * 0.515,
        ),
        0.085,
        7,
      ));
      const cornerCap = new THREE.SphereGeometry(0.14, 7, 5);
      cornerCap.translate(
        side * width * 0.515,
        cornerLift + 0.31,
        frontOrRear * depth * 0.515,
      );
      geometries.push(cornerCap);
    }
    const cap = new THREE.SphereGeometry(0.24, 8, 5);
    cap.translate(ridgeEnd.x + side * 0.2, ridgeY + 0.04, 0);
    geometries.push(cap);
  }
  const merged = mergeGeometries(geometries, false);
  geometries.forEach((geometry) => geometry.dispose());
  if (!merged) throw new Error('Unable to merge Korean roof ridge geometry.');
  merged.computeVertexNormals();
  return merged;
}

function createTieredPodiumGeometry(width, depth) {
  const lower = new THREE.BoxGeometry(width + 0.5, 0.3, depth + 0.5);
  lower.translate(0, 0.15, 0);
  const upper = new THREE.BoxGeometry(width, 0.4, depth);
  upper.translate(0, 0.48, 0);
  const merged = mergeGeometries([lower, upper], false);
  lower.dispose();
  upper.dispose();
  if (!merged) throw new Error('Unable to merge tiered podium geometry.');
  return merged;
}

function createRidgeTerrainGeometry(profile, zCenter, depth, colorBias = 0) {
  const depthRows = 5;
  const profileCurve = new THREE.CatmullRomCurve3(
    profile.map(([x, height]) => new THREE.Vector3(x, height, 0)),
    false,
    'catmullrom',
    0.18,
  );
  const sampledProfile = profileCurve
    .getPoints(Math.max(48, profile.length * 2))
    .map((point) => [point.x, point.y]);
  const vertices = [];
  const colors = [];
  const uvs = [];
  const indices = [];
  for (let row = 0; row <= depthRows; row += 1) {
    const depthRatio = row / depthRows;
    const z = zCenter + (depthRatio - 0.5) * depth;
    const crown = 0.08 + Math.sin(depthRatio * Math.PI) * 0.92;
    for (let column = 0; column < sampledProfile.length; column += 1) {
      const [x, height] = sampledProfile[column];
      const shoulderBreakup = 0.94
        + 0.045 * Math.sin(column * 1.71 + depthRatio * Math.PI * 2.4)
        + 0.025 * Math.cos(column * 0.83 - depthRatio * Math.PI * 3.2);
      vertices.push(x, height * crown * shoulderBreakup, z);
      const shade = 0.68 + depthRatio * 0.15 + colorBias;
      colors.push(shade, shade, shade);
      uvs.push(column / (sampledProfile.length - 1), depthRatio);
    }
  }
  const columns = sampledProfile.length;
  for (let row = 0; row < depthRows; row += 1) {
    for (let column = 0; column < columns - 1; column += 1) {
      const a = row * columns + column;
      const b = a + 1;
      const c = a + columns;
      const d = c + 1;
      indices.push(a, c, b, b, c, d);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

export function createSeoulPalaceHero(options = {}) {
  const started = performance.now();
  const stage = options.stage ?? 'blockout';
  if (!SEOUL_STAGES.includes(stage)) {
    throw new RangeError(`Unsupported Seoul sculpt stage "${stage}". Only "blockout" is unlocked.`);
  }
  const seed = seedValue(
    options.seed ?? options.variant?.seed ?? SEOUL_DEFAULT_SEED,
  );
  const variant = options.variant ?? {
    id: 'seoul-palace-hero-base',
    roofRoughness: 0.72,
    roofAccent: '#315B52',
    courtyardRoughness: 0.9,
    courtyardTone: '#C7AB77',
    treeDensity: 560,
    cityDensity: 148,
    mountainForestDensity: 720,
    mountainRockDensity: 46,
  };
  const random = seededRandom(seed);
  const stageIndex = SEOUL_STAGES.indexOf(stage);
  const structuralEnabled = stageIndex >= SEOUL_STAGES.indexOf('structural-pass');
  const formEnabled = stageIndex >= SEOUL_STAGES.indexOf('form-refinement');
  const materialEnabled = stageIndex >= SEOUL_STAGES.indexOf('material-pass');
  const surfaceEnabled = stageIndex >= SEOUL_STAGES.indexOf('surface-pass');
  const root = new THREE.Group();
  root.name = 'seoul-palace-hero-root';
  root.userData.sculptId = 'root';

  const materials = {
    court: new THREE.MeshStandardMaterial({ name: 'blockout-court', color: 0xcabf98, roughness: 0.92 }),
    courtPath: new THREE.MeshStandardMaterial({ name: 'compacted-court-path', color: 0xb7aa8d, roughness: 0.97 }),
    courtSeam: new THREE.MeshStandardMaterial({ name: 'court-stone-seam', color: 0xaa9c7d, roughness: 0.96 }),
    stone: new THREE.MeshStandardMaterial({ name: 'blockout-stone', color: 0xd9d4c4, roughness: 0.9 }),
    timber: new THREE.MeshStandardMaterial({ name: 'blockout-timber', color: 0x6f4037, roughness: 0.86 }),
    gateLeaf: new THREE.MeshStandardMaterial({ name: 'gate-leaf-shadow', color: 0x39443d, roughness: 0.88 }),
    roof: new THREE.MeshStandardMaterial({
      name: 'blockout-roof',
      color: 0x313d39,
      roughness: 0.84,
      side: THREE.DoubleSide,
    }),
    eave: new THREE.MeshStandardMaterial({ name: 'blockout-eave', color: 0x24312d, roughness: 0.82 }),
    roofRib: new THREE.MeshStandardMaterial({ name: 'roof-rafter-rhythm', color: 0x46524c, roughness: 0.86 }),
    dancheong: new THREE.MeshStandardMaterial({
      name: 'dancheong-accent',
      color: 0x315f51,
      roughness: 0.72,
      metalness: 0,
    }),
    green: new THREE.MeshStandardMaterial({ name: 'blockout-vegetation', color: 0x526d49, roughness: 0.95 }),
    greenDark: new THREE.MeshStandardMaterial({ name: 'blockout-tree-belt', color: 0x3e5943, roughness: 0.96 }),
    city: new THREE.MeshStandardMaterial({ name: 'blockout-city', color: 0x7f8b8a, roughness: 0.92 }),
    cityRoof: new THREE.MeshStandardMaterial({ name: 'bounded-city-roof', color: 0x58635f, roughness: 0.9 }),
    cityWindow: new THREE.MeshStandardMaterial({ name: 'bounded-city-facade-band', color: 0x465351, roughness: 0.82 }),
    road: new THREE.MeshStandardMaterial({ name: 'blockout-road-gap', color: 0x7e8580, roughness: 0.98 }),
    mountain: new THREE.MeshStandardMaterial({
      name: 'blockout-mountain',
      color: 0x607160,
      roughness: 1,
      vertexColors: true,
      side: THREE.DoubleSide,
    }),
    mountainFar: new THREE.MeshStandardMaterial({
      name: 'blockout-distant-ridge',
      color: 0x849393,
      roughness: 1,
      vertexColors: true,
      side: THREE.DoubleSide,
    }),
    mountainRock: new THREE.MeshStandardMaterial({ name: 'mountain-rock-breakup', color: 0x7b8276, roughness: 0.98 }),
  };
  const procedural = materialEnabled ? createSeoulProceduralMaps(seed) : null;
  if (procedural) {
    applySeoulPbrMaps(materials.roof, procedural.mapSets.roof, [7, 2], {
      normalScale: 0.52,
      bumpScale: 0.035,
      aoIntensity: 0.92,
    });
    applySeoulPbrMaps(materials.eave, procedural.mapSets.roof, [7, 2], {
      normalScale: 0.34,
      bumpScale: 0.018,
      aoIntensity: 0.9,
    });
    applySeoulPbrMaps(materials.court, procedural.mapSets.court, [7, 10], {
      normalScale: 0.28,
      bumpScale: 0.018,
      aoIntensity: 0.76,
    });
    applySeoulPbrMaps(materials.timber, procedural.mapSets.timber, [2, 5], {
      normalScale: 0.4,
      bumpScale: 0.022,
      aoIntensity: 0.88,
    });
    applySeoulPbrMaps(materials.stone, procedural.mapSets.stone, [4, 4], {
      normalScale: 0.36,
      bumpScale: 0.02,
      aoIntensity: 0.84,
    });
    applySeoulPbrMaps(materials.green, procedural.mapSets.vegetation, [7, 6], {
      normalScale: 0.5,
      bumpScale: 0.026,
      aoIntensity: 0.9,
    });
    applySeoulPbrMaps(materials.greenDark, procedural.mapSets.vegetation, [7, 6], {
      normalScale: 0.56,
      bumpScale: 0.03,
      aoIntensity: 0.94,
    });
    applySeoulPbrMaps(materials.city, procedural.mapSets.city, [6, 2], {
      normalScale: 0.24,
      bumpScale: 0.012,
      aoIntensity: 0.72,
    });
    applySeoulPbrMaps(materials.mountain, procedural.mapSets.mountain, [2, 2], {
      normalScale: 0.62,
      bumpScale: 0.05,
      aoIntensity: 0.94,
    });
    applySeoulPbrMaps(materials.mountainFar, procedural.mapSets.mountain, [2, 2], {
      normalScale: 0.34,
      bumpScale: 0.025,
      aoIntensity: 0.78,
    });
    applySeoulPbrMaps(materials.road, procedural.mapSets.city, [6, 2], {
      normalScale: 0.18,
      bumpScale: 0.008,
      aoIntensity: 0.68,
    });
  }
  materials.roof.roughness = variant.roofRoughness;
  materials.eave.roughness = Math.min(1, variant.roofRoughness + 0.08);
  materials.dancheong.color
    .set(variant.roofAccent)
    .offsetHSL(0, 0.04, 0.11);
  materials.court.roughness = variant.courtyardRoughness;
  materials.court.color
    .set(variant.courtyardTone)
    .lerp(new THREE.Color(0xffffff), 0.62);
  const forestRatio = THREE.MathUtils.clamp(variant.mountainForestDensity / 720, 0.84, 1.16);

  const runtime = {
    nodes: {},
    meshes: {},
    sockets: {},
    colliders: {},
    destructionGroups: {},
    resources: {
      geometries: new Set(),
      materials: new Set(Object.values(materials)),
      textures: new Set(procedural?.textures ?? []),
      instancedMeshes: new Set(),
    },
  };
  runtime.nodes.root = root;

  const registerNode = (id, node, parent = root) => {
    node.name = id;
    node.userData.sculptId = id;
    parent.add(node);
    runtime.nodes[id] = node;
    return node;
  };
  const group = (id, parent = root) => registerNode(id, new THREE.Group(), parent);
  const addToDestructionGroup = (id, object) => {
    runtime.destructionGroups[id] ??= [];
    runtime.destructionGroups[id].push(object);
    object.userData.destructionGroup = id;
  };
  const registerMesh = (id, mesh, parent, destructionGroup) => {
    mesh.name = id;
    mesh.userData.sculptId = id;
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    runtime.meshes[id] = mesh;
    runtime.resources.geometries.add(mesh.geometry);
    if (mesh.isInstancedMesh) runtime.resources.instancedMeshes.add(mesh);
    addToDestructionGroup(destructionGroup, mesh);
    return mesh;
  };
  const attach = (
    object,
    parentSocket,
    localStart,
    localEnd,
    contactType = 'embedded',
    overlap = 0.08,
    gapTolerance = 0.02,
  ) => {
    object.userData.attachment = {
      parentSocket,
      localStart: [...localStart],
      localEnd: [...localEnd],
      contactType,
      embedDepth: contactType === 'embedded' ? overlap : 0,
      overlap,
      gapTolerance,
    };
    return object;
  };
  const box = (id, size, material, parent, position, destructionGroup) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), material);
    mesh.position.set(...position);
    return registerMesh(id, mesh, parent, destructionGroup);
  };
  const collider = (id, parentId, parent, center, size) => {
    const proxy = new THREE.Object3D();
    proxy.position.set(...center);
    proxy.name = id;
    proxy.userData.collider = {
      id,
      parentId,
      type: 'box',
      size: [...size],
      isTrigger: false,
    };
    parent.add(proxy);
    runtime.colliders[id] = proxy;
    return proxy;
  };
  const socket = (
    id,
    position,
    rotation = [0, 0, 0],
    parent = root,
    parentNodeId = 'root',
  ) => {
    const object = new THREE.Object3D();
    object.name = id;
    object.position.set(...position);
    object.rotation.set(...rotation);
    object.userData.socketId = id;
    object.userData.socket = { id, parentNodeId };
    parent.add(object);
    runtime.sockets[id] = object;
    return object;
  };

  const groups = Object.fromEntries(MACRO_GROUP_IDS.map((id) => [id, group(id)]));
  const surfaceAccentPlacements = [];
  groups.foreground.userData.specId = 'foreground-system';
  groups['palace-axis'].userData.specId = 'palace-axis-system';
  groups['palace-side'].userData.specId = 'palace-side-system';
  groups.vegetation.userData.specId = 'vegetation-system';
  groups.city.userData.specId = 'city-system';
  groups.mountain.userData.specId = 'mountain-system';

  const createKoreanRoofBlockout = (
    id,
    parent,
    position,
    width,
    depth,
    roofHeight,
    destructionGroup,
    roofStyle = {},
  ) => {
    const roofGroup = group(id, parent);
    roofGroup.position.set(...position);
    roofGroup.userData.geometryRole = formEnabled
      ? 'reusable-korean-hip-and-gable-roof'
      : 'reusable-korean-curved-eave-blockout';
    roofGroup.userData.formRole = formEnabled
      ? 'merged-four-eave-hip-and-gable-system'
      : 'curved-eave-blockout';
    attach(roofGroup, `${parent.name}-beam-ring`, [0, -0.16, 0], [0, 0.08, 0]);
    const cornerLift = Math.max(0.28, width * (formEnabled ? 0.034 : 0.022));
    const centerSag = Math.max(0.09, width * (formEnabled ? 0.009 : 0.006));
    const tiered = formEnabled && roofStyle.tiered === true;
    const tierOffset = roofHeight * 0.74;
    const tierWidth = width * 0.7;
    const tierDepth = depth * 0.7;
    const tierHeight = roofHeight * 0.62;
    const tierCornerLift = Math.max(0.22, tierWidth * 0.034);
    const tierCenterSag = Math.max(0.07, tierWidth * 0.009);
    roofGroup.userData.roofApexLocal = tiered
      ? [0, tierOffset + tierHeight - tierCenterSag + 0.08, 0]
      : [0, roofHeight - centerSag + 0.08, 0];
    const surfaceGeometries = [
      createRoofSurfaceGeometry(width, depth, roofHeight, cornerLift, centerSag),
    ];
    if (tiered) {
      const upperSurface = createRoofSurfaceGeometry(
        tierWidth,
        tierDepth,
        tierHeight,
        tierCornerLift,
        tierCenterSag,
      );
      upperSurface.translate(0, tierOffset, 0);
      surfaceGeometries.push(upperSurface);
    }
    const surfaceGeometry = surfaceGeometries.length === 1
      ? surfaceGeometries[0]
      : mergeGeometries(surfaceGeometries, false);
    if (!surfaceGeometry) throw new Error(`Unable to merge roof surfaces for ${id}.`);
    if (surfaceGeometries.length > 1) {
      surfaceGeometries.forEach((geometry) => geometry.dispose());
    }
    const surface = new THREE.Mesh(
      surfaceGeometry,
      materials.roof,
    );
    registerMesh(`${id}-surface`, surface, roofGroup, destructionGroup);
    if (tiered) {
      const coreHeight = Math.max(0.9, roofHeight * 0.32);
      const upperCore = new THREE.Mesh(
        new THREE.BoxGeometry(tierWidth * 0.58, coreHeight, tierDepth * 0.52),
        materials.timber,
      );
      upperCore.position.y = tierOffset - coreHeight * 0.46;
      registerMesh(`${id}-upper-hall-core`, upperCore, roofGroup, destructionGroup);
    }
    if (formEnabled) {
      const eaveGeometries = [];
      const pushEaveTier = (
        tierWidthValue,
        tierDepthValue,
        tierY,
        lift,
        sag,
      ) => {
        for (const side of [-1, 1]) {
          for (const fasciaOffset of [-0.02, -0.17]) {
            const fasciaLift = fasciaOffset < -0.1 ? lift * 0.9 : lift;
            const fasciaSag = fasciaOffset < -0.1 ? sag * 0.82 : sag;
            eaveGeometries.push(new THREE.TubeGeometry(
              new THREE.CatmullRomCurve3(
                curvedEavePoints(
                  tierWidthValue,
                  tierDepthValue,
                  tierY + fasciaOffset,
                  side,
                  fasciaLift,
                  fasciaSag,
                ),
              ),
              32,
              fasciaOffset < -0.1 ? 0.09 : 0.13,
              5,
              false,
            ));
            eaveGeometries.push(new THREE.TubeGeometry(
              new THREE.CatmullRomCurve3(
                sideEavePoints(
                  tierWidthValue,
                  tierDepthValue,
                  tierY + fasciaOffset,
                  side,
                  fasciaLift,
                  fasciaSag,
                ),
              ),
              24,
              fasciaOffset < -0.1 ? 0.09 : 0.13,
              5,
              false,
            ));
          }
        }
      };
      pushEaveTier(width, depth, 0, cornerLift, centerSag);
      if (tiered) {
        pushEaveTier(
          tierWidth,
          tierDepth,
          tierOffset,
          tierCornerLift,
          tierCenterSag,
        );
      }
      const mergedEaves = mergeGeometries(eaveGeometries, false);
      eaveGeometries.forEach((geometry) => geometry.dispose());
      if (!mergedEaves) throw new Error(`Unable to merge eaves for ${id}.`);
      registerMesh(
        `${id}-four-sided-eaves`,
        new THREE.Mesh(mergedEaves, materials.eave),
        roofGroup,
        destructionGroup,
      );
    } else {
      for (const side of [-1, 1]) {
        const curve = new THREE.CatmullRomCurve3(
          curvedEavePoints(width, depth, -0.02, side, cornerLift, centerSag),
        );
        const fascia = new THREE.Mesh(
          new THREE.TubeGeometry(curve, 32, 0.12, 5, false),
          materials.eave,
        );
        registerMesh(`${id}-eave-${side < 0 ? 'front' : 'rear'}`, fascia, roofGroup, destructionGroup);
      }
    }
    const ridgeGeometries = [
      formEnabled
        ? createRoofRidgeGeometry(width, depth, roofHeight, cornerLift, centerSag)
        : new THREE.CylinderGeometry(0.13, 0.13, width * 0.48, 8),
    ];
    if (tiered) {
      const upperRidge = createRoofRidgeGeometry(
        tierWidth,
        tierDepth,
        tierHeight,
        tierCornerLift,
        tierCenterSag,
      );
      upperRidge.translate(0, tierOffset, 0);
      ridgeGeometries.push(upperRidge);
    }
    const ridgeGeometry = ridgeGeometries.length === 1
      ? ridgeGeometries[0]
      : mergeGeometries(ridgeGeometries, false);
    if (!ridgeGeometry) throw new Error(`Unable to merge roof ridges for ${id}.`);
    if (ridgeGeometries.length > 1) {
      ridgeGeometries.forEach((geometry) => geometry.dispose());
    }
    const ridge = new THREE.Mesh(ridgeGeometry, materials.eave);
    if (!formEnabled) {
      ridge.rotation.z = Math.PI / 2;
      ridge.position.y = roofHeight - centerSag + 0.08;
    }
    registerMesh(`${id}-${formEnabled ? 'ridge-caps-and-hips' : 'ridge'}`, ridge, roofGroup, destructionGroup);
    if (surfaceEnabled) {
      const tierDefinitions = [
        {
          width,
          depth,
          y: 0,
          roofHeight,
          cornerLift,
          centerSag,
          rows: 12,
        },
      ];
      if (tiered) {
        tierDefinitions.push({
          width: tierWidth,
          depth: tierDepth,
          y: tierOffset,
          roofHeight: tierHeight,
          cornerLift: tierCornerLift,
          centerSag: tierCenterSag,
          rows: 10,
        });
      }
      const tileCount = tierDefinitions.reduce((count, tier) => count + tier.rows * 2, 0);
      const tileRibs = new THREE.InstancedMesh(
        new THREE.CylinderGeometry(0.042, 0.042, 1, 6),
        materials.roofRib,
        tileCount,
      );
      const tileMatrix = new THREE.Matrix4();
      const tilePosition = new THREE.Vector3();
      const tileQuaternion = new THREE.Quaternion();
      const tileScale = new THREE.Vector3();
      const up = new THREE.Vector3(0, 1, 0);
      let tileIndex = 0;
      for (const tier of tierDefinitions) {
        for (let row = 0; row < tier.rows; row += 1) {
          const xRatio = row / (tier.rows - 1) * 1.68 - 0.84;
          const x = xRatio * tier.width * 0.5;
          const absX = Math.abs(xRatio);
          const eaveY = tier.y
            + tier.cornerLift * absX ** 2
            - tier.centerSag * (1 - absX ** 2);
          const hipEnvelope = Math.min(1, Math.max(0, (1 - absX) / 0.26));
          const ridgePointY = eaveY + tier.roofHeight * hipEnvelope;
          for (const frontOrRear of [-1, 1]) {
            const start = new THREE.Vector3(
              x,
              eaveY + 0.05,
              frontOrRear * tier.depth * 0.49,
            );
            const end = new THREE.Vector3(x, ridgePointY + 0.05, 0);
            const direction = new THREE.Vector3().subVectors(end, start);
            tilePosition.addVectors(start, end).multiplyScalar(0.5);
            tileQuaternion.setFromUnitVectors(up, direction.clone().normalize());
            tileScale.set(1, direction.length(), 1);
            tileMatrix.compose(tilePosition, tileQuaternion, tileScale);
            tileRibs.setMatrixAt(tileIndex, tileMatrix);
            tileIndex += 1;
          }
        }
      }
      tileRibs.instanceMatrix.needsUpdate = true;
      registerMesh(`${id}-tile-rafter-rhythm`, tileRibs, roofGroup, destructionGroup);
    }
    return roofGroup;
  };

  const createPalaceMass = (
    id,
    parent,
    position,
    width,
    depth,
    bodyHeight,
    roofHeight,
    destructionGroup,
    options = {},
  ) => {
    const building = group(id, parent);
    building.position.set(...position);
    const podium = formEnabled
      ? registerMesh(
        `${id}-podium`,
        new THREE.Mesh(createTieredPodiumGeometry(width + 1.4, depth + 1.3), materials.stone),
        building,
        destructionGroup,
      )
      : box(`${id}-podium`, [width + 1.4, 0.55, depth + 1.3], materials.stone, building, [0, 0.28, 0], destructionGroup);
    podium.userData.structuralRole = 'podium-foundation';
    attach(podium, `${id}-ground-contact`, [0, -0.28, 0], [0, 0.06, 0], 'overlap', 0.06);

    const portalWidth = options.portalWidth ?? 0;
    if (portalWidth > 0) {
      const pierWidth = (width - portalWidth) * 0.5;
      for (const side of [-1, 1]) {
        const sideName = side < 0 ? 'west' : 'east';
        const pier = box(
          `${id}-body-${sideName}`,
          [pierWidth, bodyHeight, depth * 0.82],
          materials.timber,
          building,
          [side * (portalWidth * 0.5 + pierWidth * 0.5), 0.55 + bodyHeight * 0.5, 0],
          destructionGroup,
        );
        attach(pier, `${id}-podium-top`, [0, -bodyHeight * 0.5, 0], [0, -bodyHeight * 0.5 - 0.08, 0]);
      }
    } else {
      const body = box(
        `${id}-body`,
        [structuralEnabled ? width * 0.88 : width, bodyHeight, structuralEnabled ? depth * 0.66 : depth],
        materials.timber,
        building,
        [0, 0.55 + bodyHeight * 0.5, 0],
        destructionGroup,
      );
      attach(body, `${id}-podium-top`, [0, -bodyHeight * 0.5, 0], [0, -bodyHeight * 0.5 - 0.08, 0]);
    }

    if (structuralEnabled) {
      const bayCount = Math.max(3, Math.round(width / 4));
      const columnHeight = bodyHeight + 0.22;
      const columnGeometry = new THREE.CylinderGeometry(
        Math.max(0.13, Math.min(0.22, width * 0.012)),
        Math.max(0.15, Math.min(0.25, width * 0.014)),
        columnHeight,
        8,
      );
      const columns = new THREE.InstancedMesh(columnGeometry, materials.timber, bayCount * 2);
      const columnMatrix = new THREE.Matrix4();
      const columnPosition = new THREE.Vector3();
      const columnScale = new THREE.Vector3(1, 1, 1);
      const columnQuaternion = new THREE.Quaternion();
      let columnIndex = 0;
      for (const side of [-1, 1]) {
        for (let bay = 0; bay < bayCount; bay += 1) {
          const ratio = bayCount === 1 ? 0 : bay / (bayCount - 1);
          columnPosition.set(
            (ratio - 0.5) * width * 0.86,
            0.55 + columnHeight * 0.5,
            side * depth * 0.46,
          );
          columnMatrix.compose(columnPosition, columnQuaternion, columnScale);
          columns.setMatrixAt(columnIndex, columnMatrix);
          columnIndex += 1;
        }
      }
      columns.instanceMatrix.needsUpdate = true;
      attach(
        registerMesh(`${id}-column-bays`, columns, building, destructionGroup),
        `${id}-podium-top`,
        [0, -columnHeight * 0.5, 0],
        [0, -columnHeight * 0.5 - 0.1, 0],
        'embedded',
        0.1,
      );

      const beamY = bodyHeight + 0.62;
      const beamRing = new THREE.InstancedMesh(
        new THREE.BoxGeometry(1, 1, 1),
        materials.eave,
        4,
      );
      const beamScale = new THREE.Vector3();
      for (let index = 0; index < 4; index += 1) {
        const frontOrRear = index < 2;
        columnPosition.set(
          frontOrRear ? 0 : (index === 2 ? -1 : 1) * width * 0.43,
          beamY,
          frontOrRear ? (index === 0 ? -1 : 1) * depth * 0.46 : 0,
        );
        beamScale.set(
          frontOrRear ? width * 0.94 : 0.34,
          0.34,
          frontOrRear ? 0.34 : depth * 0.88,
        );
        columnMatrix.compose(columnPosition, columnQuaternion, beamScale);
        beamRing.setMatrixAt(index, columnMatrix);
      }
      beamRing.instanceMatrix.needsUpdate = true;
      attach(
        registerMesh(`${id}-beam-ring`, beamRing, building, destructionGroup),
        `${id}-column-tops`,
        [0, -0.17, 0],
        [0, -0.25, 0],
        'overlap',
        0.08,
      );

    }

    if (portalWidth > 0) {
      const leafWidth = portalWidth * 0.5;
      const leafHeight = bodyHeight * 0.72;
      for (const side of [-1, 1]) {
        const sideName = side < 0 ? 'west' : 'east';
        const hingeName = side < 0 ? 'left' : 'right';
        const pivot = group(`${id}-${sideName}-leaf-pivot`, building);
        pivot.position.set(side * portalWidth * 0.5, 0, -depth * 0.42);
        pivot.userData.actionPivot = {
          axis: [0, 1, 0],
          limits: side < 0 ? [0, Math.PI * 0.48] : [-Math.PI * 0.48, 0],
        };
        const leaf = box(
          `${id}-${sideName}-leaf`,
          [leafWidth, leafHeight, 0.24],
          materials.gateLeaf,
          pivot,
          [-side * leafWidth * 0.5, 0.55 + leafHeight * 0.5, 0],
          destructionGroup,
        );
        attach(leaf, `${id}-${hingeName}-hinge`, [side * leafWidth * 0.5, 0, 0], [0, 0, 0], 'hinged', 0.04, 0.01);
        collider(
          `${id}-${sideName}-leaf-collider`,
          `${id}-${sideName}-leaf`,
          pivot,
          [-side * leafWidth * 0.5, 0.55 + leafHeight * 0.5, 0],
          [leafWidth, leafHeight, 0.24],
        );
      }
    }

    const roof = createKoreanRoofBlockout(
      `${id}-roof`,
      building,
      [0, bodyHeight + 0.75, 0],
      width + 2.1,
      depth + 2,
      roofHeight,
      destructionGroup,
      { tiered: options.tieredRoof === true },
    );
    roof.userData.supportedBy = structuralEnabled
      ? [`${id}-beam-ring`]
      : [`${id}-body`];
    if (surfaceEnabled) {
      surfaceAccentPlacements.push({
        id,
        position: [...position],
        width,
        depth,
        bodyHeight,
        portalWidth,
        destructionGroup,
      });
    }
    if (portalWidth > 0) {
      const pierWidth = (width - portalWidth) * 0.5;
      for (const side of [-1, 1]) {
        const sideName = side < 0 ? 'west' : 'east';
        collider(
          `${id}-${sideName}-pier-collider`,
          `${id}-body-${sideName}`,
          building,
          [side * (portalWidth * 0.5 + pierWidth * 0.5), 0.55 + bodyHeight * 0.5, 0],
          [pierWidth, bodyHeight, depth * 0.82],
        );
      }
    } else {
      collider(`${id}-collider`, id, building, [0, bodyHeight * 0.5, 0], [width + 1.4, bodyHeight + 1.2, depth + 1.3]);
    }
    return building;
  };

  box('foreground-ground', [90, 0.35, 34], materials.court, groups.foreground, [0, -0.18, -28], 'protected-foreground');
  box('foreground-road', [90, 0.18, 5.2], materials.road, groups.foreground, [0, 0.03, -42], 'protected-foreground');
  box('perimeter-wall-west', [29, 2.2, 1.1], materials.stone, groups.foreground, [-34, 1.1, -19], 'protected-foreground');
  box('perimeter-wall-center', [15, 2.2, 1.1], materials.stone, groups.foreground, [0.5, 1.1, -19], 'protected-foreground');
  box('perimeter-wall-east', [31, 2.2, 1.1], materials.stone, groups.foreground, [29.5, 1.1, -19], 'protected-foreground');
  createPalaceMass('outer-gate', groups.foreground, [-13, 0, -19], 13, 4.2, 3.3, 2.1, 'protected-foreground', { portalWidth: 6.2 });
  collider('foreground-collider', 'foreground-ground', groups.foreground, [0, -0.18, -28], [90, 0.35, 34]);

  box('outer-court', [62, 0.3, 35], materials.court, groups['palace-axis'], [-3, -0.12, 0], 'protected-palace-axis');
  box('processional-court', [58, 0.3, 39], materials.court, groups['palace-axis'], [0, -0.1, 41], 'protected-palace-axis');
  box('main-court', [54, 0.3, 20], materials.court, groups['palace-axis'], [0, -0.08, 72], 'protected-palace-axis');
  createPalaceMass('inner-gate', groups['palace-axis'], [0, 0, 22], 18, 5.5, 3.8, 2.4, 'protected-palace-axis', { portalWidth: 7.2 });
  createPalaceMass(
    'main-hall',
    groups['palace-axis'],
    [0, 0, 62],
    24,
    9.5,
    6.2,
    3.6,
    'protected-palace-axis',
    { tieredRoof: true },
  );
  createPalaceMass('rear-hall', groups['palace-axis'], [1.5, 0, 84], 16, 7, 4.2, 2.7, 'protected-palace-axis');
  createPalaceMass('secondary-hall', groups['palace-axis'], [-2, 0, 98], 12, 5.5, 3.4, 2.2, 'protected-palace-axis');
  box('axis-wall-west', [1.1, 2.1, 82], materials.stone, groups['palace-axis'], [-30, 1.05, 37], 'protected-palace-axis');
  box('axis-wall-east', [1.1, 2.1, 82], materials.stone, groups['palace-axis'], [30, 1.05, 37], 'protected-palace-axis');

  for (const side of [-1, 1]) {
    const sideName = side < 0 ? 'west' : 'east';
    createPalaceMass(`${sideName}-front-pavilion`, groups['palace-side'], [side * 27, 0, 7], 10, 5, 2.8, 1.8, 'protected-palace-side');
    createPalaceMass(`${sideName}-court-pavilion`, groups['palace-side'], [side * 25, 0, 49], 11, 5.2, 3, 1.9, 'protected-palace-side');
    createPalaceMass(`${sideName}-rear-pavilion`, groups['palace-side'], [side * 22, 0, 80], 9, 4.6, 2.7, 1.7, 'protected-palace-side');
    for (let index = 0; index < 4; index += 1) {
      createPalaceMass(
        `${sideName}-corridor-${index + 1}`,
        groups['palace-side'],
        [side * 30, 0, 25 + index * 12],
        5,
        8.2,
        1.8,
        1.05,
        'protected-palace-side',
      );
    }
    if (structuralEnabled) {
      box(
        `${sideName}-corridor-foundation`,
        [6.4, 0.32, 48],
        materials.stone,
        groups['palace-side'],
        [side * 30, 0.16, 43],
        'protected-palace-side',
      );
    }
  }
  box('service-court-west', [18, 0.24, 24], materials.court, groups['palace-side'], [-39, -0.1, 67], 'protected-palace-side');
  box('service-court-east', [16, 0.24, 20], materials.court, groups['palace-side'], [39, -0.1, 58], 'protected-palace-side');
  if (surfaceEnabled) {
    const courtPathDefinitions = [
      [0, 0.08, 3, 3.1, 0.08, 33],
      [0, 0.08, 42, 3.3, 0.08, 35],
      [0, 0.08, 72, 3.5, 0.08, 18],
      [0, 0.07, 21, 54, 0.06, 0.28],
      [0, 0.07, 82, 46, 0.06, 0.24],
    ];
    const courtPaths = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1),
      materials.courtPath,
      courtPathDefinitions.length,
    );
    const courtAccentMatrix = new THREE.Matrix4();
    const courtAccentQuaternion = new THREE.Quaternion();
    courtPathDefinitions.forEach(([x, y, z, sx, sy, sz], index) => {
      courtAccentMatrix.compose(
        new THREE.Vector3(x, y, z),
        courtAccentQuaternion,
        new THREE.Vector3(sx, sy, sz),
      );
      courtPaths.setMatrixAt(index, courtAccentMatrix);
    });
    courtPaths.instanceMatrix.needsUpdate = true;
    registerMesh(
      'ceremonial-compacted-paths',
      courtPaths,
      groups['palace-axis'],
      'protected-palace-axis',
    );

    const courtSeamDefinitions = [];
    for (let z = -10; z <= 90; z += 12) {
      const courtWidth = z < 22 ? 58 : z < 62 ? 54 : 48;
      courtSeamDefinitions.push([0, 0.105, z, courtWidth, 0.02, 0.055]);
    }
    for (const x of [-15, 15]) {
      courtSeamDefinitions.push([x, 0.106, 39, 0.045, 0.02, 68]);
    }
    const courtSeams = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1),
      materials.courtSeam,
      courtSeamDefinitions.length,
    );
    courtSeamDefinitions.forEach(([x, y, z, sx, sy, sz], index) => {
      courtAccentMatrix.compose(
        new THREE.Vector3(x, y, z),
        courtAccentQuaternion,
        new THREE.Vector3(sx, sy, sz),
      );
      courtSeams.setMatrixAt(index, courtAccentMatrix);
    });
    courtSeams.instanceMatrix.needsUpdate = true;
    registerMesh(
      'ceremonial-court-seams',
      courtSeams,
      groups['palace-axis'],
      'protected-palace-axis',
    );

    const bayPanels = [];
    surfaceAccentPlacements.forEach((placement) => {
      const portalWidth = placement.portalWidth ?? 0;
      if (portalWidth > 0) {
        const pierWidth = (placement.width - portalWidth) * 0.5;
        for (const side of [-1, 1]) {
          bayPanels.push({
            x: placement.position[0] + side * (portalWidth * 0.5 + pierWidth * 0.5),
            y: 0.58 + placement.bodyHeight * 0.52,
            z: placement.position[2] - placement.depth * 0.42 - 0.03,
            width: pierWidth * 0.58,
            height: placement.bodyHeight * 0.5,
          });
        }
        return;
      }
      const bayCount = Math.max(3, Math.round(placement.width / 4));
      for (let bay = 0; bay < bayCount; bay += 1) {
        const ratio = bayCount === 1 ? 0 : bay / (bayCount - 1);
        bayPanels.push({
          x: placement.position[0] + (ratio - 0.5) * placement.width * 0.72,
          y: 0.58 + placement.bodyHeight * 0.52,
          z: placement.position[2] - placement.depth * 0.34 - 0.035,
          width: placement.width * 0.58 / bayCount,
          height: placement.bodyHeight * 0.52,
        });
      }
    });
    const palaceBayShadows = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1),
      materials.eave,
      bayPanels.length,
    );
    bayPanels.forEach((panel, index) => {
      courtAccentMatrix.compose(
        new THREE.Vector3(panel.x, panel.y, panel.z),
        courtAccentQuaternion,
        new THREE.Vector3(panel.width, panel.height, 0.1),
      );
      palaceBayShadows.setMatrixAt(index, courtAccentMatrix);
    });
    palaceBayShadows.instanceMatrix.needsUpdate = true;
    registerMesh(
      'palace-recessed-bay-shadows',
      palaceBayShadows,
      groups['palace-axis'],
      'protected-palace-axis',
    );

    const accentBands = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1),
      materials.dancheong,
      surfaceAccentPlacements.length * 4,
    );
    const accentMatrix = new THREE.Matrix4();
    const accentQuaternion = new THREE.Quaternion();
    surfaceAccentPlacements.forEach((placement, placementIndex) => {
      accentMatrix.compose(
        new THREE.Vector3(
          placement.position[0],
          0.55 + placement.bodyHeight * 0.88,
          placement.position[2] - placement.depth * 0.35,
        ),
        accentQuaternion,
        new THREE.Vector3(placement.width * 0.78, 0.18, 0.16),
      );
      accentBands.setMatrixAt(placementIndex * 4, accentMatrix);
      for (let bracket = 0; bracket < 3; bracket += 1) {
        accentMatrix.compose(
          new THREE.Vector3(
            placement.position[0] + (bracket - 1) * placement.width * 0.28,
            0.55 + placement.bodyHeight * 0.98,
            placement.position[2] - placement.depth * 0.36,
          ),
          accentQuaternion,
          new THREE.Vector3(
            Math.max(0.18, placement.width * 0.022),
            0.3,
            0.2,
          ),
        );
        accentBands.setMatrixAt(placementIndex * 4 + bracket + 1, accentMatrix);
      }
    });
    accentBands.instanceMatrix.needsUpdate = true;
    registerMesh(
      'dancheong-beam-bands',
      accentBands,
      groups['palace-axis'],
      'protected-palace-axis',
    );

    const markerCount = 24;
    const courtMarkers = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1),
      materials.stone,
      markerCount,
    );
    for (let index = 0; index < markerCount; index += 1) {
      const pairIndex = Math.floor(index / 2);
      accentMatrix.compose(
        new THREE.Vector3(index % 2 === 0 ? -2.2 : 2.2, 0.2, -2 + pairIndex * 4.3),
        accentQuaternion,
        new THREE.Vector3(0.26, 0.38, 0.62),
      );
      courtMarkers.setMatrixAt(index, accentMatrix);
    }
    courtMarkers.instanceMatrix.needsUpdate = true;
    registerMesh(
      'processional-court-markers',
      courtMarkers,
      groups['palace-axis'],
      'protected-palace-axis',
    );
  }

  const treeGeometry = new THREE.IcosahedronGeometry(1, 1);
  const canopyPositions = treeGeometry.getAttribute('position');
  for (let index = 0; index < canopyPositions.count; index += 1) {
    const x = canopyPositions.getX(index);
    const y = canopyPositions.getY(index);
    const z = canopyPositions.getZ(index);
    const breakup = 1 + 0.11 * Math.sin(x * 6.1 + y * 7.3 + z * 5.7);
    const baseTaper = y < -0.12 ? 0.78 + (y + 1) * 0.18 : 1;
    canopyPositions.setXYZ(
      index,
      x * breakup * baseTaper * 1.05,
      y * breakup * 0.84,
      z * breakup * baseTaper * 0.96,
    );
  }
  canopyPositions.needsUpdate = true;
  treeGeometry.computeVertexNormals();
  const treeCount = Math.round(190 * THREE.MathUtils.clamp(variant.treeDensity / 560, 0.82, 1.18));
  const treeBeltCount = Math.round(treeCount * 0.72);
  const canopyLobes = 3;
  const trees = new THREE.InstancedMesh(
    treeGeometry,
    materials.greenDark,
    treeCount * canopyLobes,
  );
  const trunks = surfaceEnabled
    ? new THREE.InstancedMesh(
      new THREE.CylinderGeometry(0.16, 0.24, 1, 6),
      materials.timber,
      treeCount,
    )
    : null;
  const matrix = new THREE.Matrix4();
  const treePosition = new THREE.Vector3();
  const treeScale = new THREE.Vector3();
  const treeQuaternion = new THREE.Quaternion();
  const canopyColor = new THREE.Color();
  for (let index = 0; index < treeCount; index += 1) {
    const belt = index < treeBeltCount;
    const x = belt ? -50 + random() * 100 : (random() < 0.5 ? -1 : 1) * (32 + random() * 12);
    const z = belt ? 90 + random() * 22 : -5 + random() * 88;
    const scale = belt ? 1.45 + random() * 1.65 : 1 + random() * 1.3;
    const widthScale = scale * (0.8 + random() * 0.28);
    const depthScale = scale * (0.8 + random() * 0.28);
    const lobeDefinitions = [
      [0, 0, 0, 0.92, 1, 0.88],
      [0.38, 0.15, 0.14, 0.63, 0.76, 0.62],
      [-0.34, 0.12, -0.22, 0.68, 0.8, 0.58],
    ];
    lobeDefinitions.forEach(([ox, oy, oz, sx, sy, sz], lobe) => {
      treePosition.set(
        x + ox * scale * (index % 2 === 0 ? 1 : -1),
        scale * (0.76 + oy),
        z + oz * scale,
      );
      treeScale.set(widthScale * sx, scale * sy, depthScale * sz);
      treeQuaternion.setFromAxisAngle(
        new THREE.Vector3(0, 1, 0),
        (index * 0.31 + lobe * 0.8) % (Math.PI * 2),
      );
      matrix.compose(treePosition, treeQuaternion, treeScale);
      const instanceIndex = index * canopyLobes + lobe;
      trees.setMatrixAt(instanceIndex, matrix);
      canopyColor.setHSL(
        0.285 + ((index + lobe * 7) % 9 - 4) * 0.004,
        0.12 + ((index + lobe) % 4) * 0.014,
        (belt ? 0.68 : 0.72) + ((index * 3 + lobe) % 5) * 0.025,
      );
      trees.setColorAt(instanceIndex, canopyColor);
    });
    if (trunks) {
      matrix.compose(
        new THREE.Vector3(x, scale * 0.32, z),
        treeQuaternion,
        new THREE.Vector3(0.82, scale * 0.64, 0.82),
      );
      trunks.setMatrixAt(index, matrix);
    }
  }
  trees.instanceMatrix.needsUpdate = true;
  trees.instanceColor.needsUpdate = true;
  registerMesh('tree-belt-instances', trees, groups.vegetation, 'protected-vegetation');
  if (trunks) {
    trunks.instanceMatrix.needsUpdate = true;
    registerMesh('tree-trunk-instances', trunks, groups.vegetation, 'protected-vegetation');
  }
  const foothillClusterCount = 34;
  const foothillForest = new THREE.InstancedMesh(
    treeGeometry,
    materials.green,
    foothillClusterCount,
  );
  for (let index = 0; index < foothillClusterCount; index += 1) {
    const ratio = index / (foothillClusterCount - 1);
    const x = (ratio - 0.5) * 100 * forestRatio;
    const z = 112 + (index % 4) * 2.4;
    const scale = 2.2 + (index * 7 % 9) * 0.18;
    treeQuaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), index * 0.41);
    matrix.compose(
      new THREE.Vector3(x, scale * 0.54, z),
      treeQuaternion,
      new THREE.Vector3(scale * 1.35, scale * 0.64, scale),
    );
    foothillForest.setMatrixAt(index, matrix);
    canopyColor.setHSL(
      0.29 + (index % 5 - 2) * 0.005,
      0.12,
      0.66 + (index % 4) * 0.025,
    );
    foothillForest.setColorAt(index, canopyColor);
  }
  foothillForest.instanceMatrix.needsUpdate = true;
  foothillForest.instanceColor.needsUpdate = true;
  registerMesh(
    'foothill-forest-mass',
    foothillForest,
    groups.vegetation,
    'protected-vegetation',
  );

  box('city-road-west', [4.5, 0.18, 24], materials.road, groups.city, [-18, 0.02, 107], 'protected-city');
  box('city-road-east', [5.5, 0.18, 24], materials.road, groups.city, [20, 0.02, 106], 'protected-city');
  box('city-green-gap', [13, 0.2, 8], materials.green, groups.city, [2, 0.03, 109], 'protected-city');
  const cityGeometry = new THREE.BoxGeometry(1, 1, 1);
  const cityCount = Math.round(136 * THREE.MathUtils.clamp(variant.cityDensity / 148, 0.82, 1.18));
  const buildings = new THREE.InstancedMesh(cityGeometry, materials.city, cityCount);
  const cityRoofCaps = surfaceEnabled
    ? new THREE.InstancedMesh(cityGeometry, materials.cityRoof, cityCount)
    : null;
  const cityFacadeBands = surfaceEnabled
    ? new THREE.InstancedMesh(cityGeometry, materials.cityWindow, cityCount * 2)
    : null;
  const cityQuaternion = new THREE.Quaternion();
  const cityColor = new THREE.Color();
  for (let index = 0; index < cityCount; index += 1) {
    const band = index % 4;
    const typology = index % 5;
    let x = -62 + random() * 124;
    if (Math.abs(x + 18) < 4 || Math.abs(x - 20) < 5 || Math.abs(x) < 7) x += x < 0 ? -7 : 7;
    const z = 100 + band * 6.2 + random() * 3.8;
    const width = (typology === 0 ? 2.1 : 2.8) + random() * (typology === 2 ? 4.8 : 3.7);
    const height = (typology === 0 ? 5.6 : 2.2) + random() * (typology === 0 ? 4.4 : 5.2);
    const depth = 2.2 + random() * (typology === 3 ? 4.8 : 3.4);
    cityQuaternion.setFromAxisAngle(
      new THREE.Vector3(0, 1, 0),
      formEnabled ? (band - 1) * 0.035 + (typology - 2) * 0.008 : 0,
    );
    matrix.compose(
      new THREE.Vector3(x, height * 0.5, z),
      cityQuaternion,
      new THREE.Vector3(width, height, depth),
    );
    buildings.setMatrixAt(index, matrix);
    cityColor.setHSL(
      0.12 + (index % 7 - 3) * 0.006,
      0.035 + (index % 3) * 0.012,
      0.5 + (index % 5) * 0.035,
    );
    buildings.setColorAt(index, cityColor);
    if (cityRoofCaps) {
      matrix.compose(
        new THREE.Vector3(x, height + 0.12, z),
        cityQuaternion,
        new THREE.Vector3(width * 1.04, 0.2, depth * 1.04),
      );
      cityRoofCaps.setMatrixAt(index, matrix);
    }
    if (cityFacadeBands) {
      for (let level = 0; level < 2; level += 1) {
        matrix.compose(
          new THREE.Vector3(
            x,
            height * (0.38 + level * 0.28),
            z - depth * 0.5 - 0.035,
          ),
          cityQuaternion,
          new THREE.Vector3(width * 0.72, 0.13, 0.08),
        );
        cityFacadeBands.setMatrixAt(index * 2 + level, matrix);
      }
    }
  }
  buildings.instanceMatrix.needsUpdate = true;
  buildings.instanceColor.needsUpdate = true;
  registerMesh('bounded-city-instances', buildings, groups.city, 'protected-city');
  if (cityRoofCaps) {
    cityRoofCaps.instanceMatrix.needsUpdate = true;
    registerMesh('bounded-city-roof-caps', cityRoofCaps, groups.city, 'protected-city');
  }
  if (cityFacadeBands) {
    cityFacadeBands.instanceMatrix.needsUpdate = true;
    registerMesh('bounded-city-facade-bands', cityFacadeBands, groups.city, 'protected-city');
  }

  if (surfaceEnabled) {
    const foregroundMassCount = 14;
    const foregroundMasses = new THREE.InstancedMesh(
      cityGeometry,
      materials.city,
      foregroundMassCount,
    );
    const foregroundRoofCaps = new THREE.InstancedMesh(
      cityGeometry,
      materials.cityRoof,
      foregroundMassCount,
    );
    const foregroundFacadeBands = new THREE.InstancedMesh(
      cityGeometry,
      materials.cityWindow,
      foregroundMassCount,
    );
    for (let index = 0; index < foregroundMassCount; index += 1) {
      const side = index < foregroundMassCount / 2 ? -1 : 1;
      const laneIndex = index % (foregroundMassCount / 2);
      const width = 3.6 + (laneIndex % 3) * 1.1;
      const height = 1.8 + (laneIndex * 5 % 7) * 0.42;
      const depth = 3 + (laneIndex % 2) * 1.6;
      const x = side * (21 + laneIndex * 4.8);
      const z = -29 - (laneIndex % 3) * 3.2;
      matrix.compose(
        new THREE.Vector3(x, height * 0.5, z),
        cityQuaternion.identity(),
        new THREE.Vector3(width, height, depth),
      );
      foregroundMasses.setMatrixAt(index, matrix);
      cityColor.setHSL(0.11, 0.03, 0.48 + (laneIndex % 4) * 0.04);
      foregroundMasses.setColorAt(index, cityColor);
      matrix.compose(
        new THREE.Vector3(x, height + 0.1, z),
        cityQuaternion,
        new THREE.Vector3(width * 1.04, 0.18, depth * 1.04),
      );
      foregroundRoofCaps.setMatrixAt(index, matrix);
      matrix.compose(
        new THREE.Vector3(x, height * 0.58, z - depth * 0.5 - 0.04),
        cityQuaternion,
        new THREE.Vector3(width * 0.68, 0.16, 0.08),
      );
      foregroundFacadeBands.setMatrixAt(index, matrix);
    }
    foregroundMasses.instanceMatrix.needsUpdate = true;
    foregroundMasses.instanceColor.needsUpdate = true;
    registerMesh(
      'foreground-modern-masses',
      foregroundMasses,
      groups.foreground,
      'protected-foreground',
    );
    foregroundRoofCaps.instanceMatrix.needsUpdate = true;
    registerMesh(
      'foreground-modern-roof-caps',
      foregroundRoofCaps,
      groups.foreground,
      'protected-foreground',
    );
    foregroundFacadeBands.instanceMatrix.needsUpdate = true;
    registerMesh(
      'foreground-modern-facade-bands',
      foregroundFacadeBands,
      groups.foreground,
      'protected-foreground',
    );
  }

  const nearProfile = [
    [-68, 8], [-62, 12], [-57, 19], [-52, 25], [-47, 28], [-42, 27],
    [-37, 24], [-31, 19], [-24, 14], [-16, 10], [-7, 8], [2, 7],
    [11, 8], [20, 10], [29, 13], [37, 17], [44, 22], [50, 28],
    [55, 31], [60, 29], [65, 22], [70, 12],
  ];
  const farProfile = [
    [-70, 9], [-61, 13], [-52, 11], [-43, 15], [-34, 12], [-25, 16],
    [-16, 13], [-7, 17], [2, 14], [11, 18], [20, 15], [30, 19],
    [40, 16], [50, 20], [60, 15], [70, 10],
  ];
  const nearRidge = new THREE.Mesh(
    createRidgeTerrainGeometry(nearProfile, 134, 42),
    materials.mountain,
  );
  registerMesh('asymmetric-near-ridge', nearRidge, groups.mountain, 'protected-terrain');
  const distantRidge = new THREE.Mesh(
    createRidgeTerrainGeometry(farProfile, 151, 30, 0.13),
    materials.mountainFar,
  );
  distantRidge.position.y = 2;
  registerMesh('distant-ridge-layer', distantRidge, groups.mountain, 'protected-terrain');
  if (surfaceEnabled) {
    const rockPlacements = [
      [51, 19.2, 126, 3.8, 0.48, 1.8],
      [45, 15.8, 132, 4.2, 0.52, 2.1],
      [37, 12.4, 127, 3.1, 0.42, 1.6],
      [28, 9.4, 134, 2.7, 0.38, 1.4],
      [-30, 12.8, 126, 2.8, 0.4, 1.5],
      [-38, 17.2, 130, 3.7, 0.48, 1.8],
      [-46, 20.6, 132, 3.2, 0.42, 1.6],
      [-54, 15.5, 128, 2.5, 0.35, 1.3],
      [-21, 9.2, 136, 2.4, 0.34, 1.2],
      [13, 7.6, 131, 2.3, 0.32, 1.2],
      [58, 20.4, 136, 2.5, 0.35, 1.3],
      [-61, 11.8, 136, 2.2, 0.32, 1.2],
    ];
    const rockCount = Math.round(
      rockPlacements.length * THREE.MathUtils.clamp(variant.mountainRockDensity / 46, 0.82, 1.18),
    );
    const rockPatches = new THREE.InstancedMesh(
      new THREE.IcosahedronGeometry(1, 1),
      materials.mountainRock,
      rockCount,
    );
    const rockMatrix = new THREE.Matrix4();
    const rockQuaternion = new THREE.Quaternion();
    rockPlacements.slice(0, rockCount).forEach(([x, y, z, sx, sy, sz], index) => {
      rockQuaternion.setFromEuler(new THREE.Euler(0.1 * index, 0.17 * index, -0.08 * index));
      rockMatrix.compose(
        new THREE.Vector3(x, y, z),
        rockQuaternion,
        new THREE.Vector3(sx, sy, sz),
      );
      rockPatches.setMatrixAt(index, rockMatrix);
    });
    rockPatches.instanceMatrix.needsUpdate = true;
    registerMesh('mountain-rock-patches', rockPatches, groups.mountain, 'protected-terrain');

    const mountainForestCount = 30;
    const mountainForest = new THREE.InstancedMesh(
      treeGeometry,
      materials.greenDark,
      mountainForestCount,
    );
    for (let index = 0; index < mountainForestCount; index += 1) {
      const ratio = index / (mountainForestCount - 1);
      const x = -61 + ratio * 122;
      const shoulder = x < -10
        ? 7 + 17 * Math.exp(-(((x + 47) / 18) ** 2))
        : 6 + 19 * Math.exp(-(((x - 53) / 17) ** 2));
      const z = 123 + (index % 5) * 3.1;
      const scale = 1.8 + (index * 11 % 7) * 0.2;
      treeQuaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), index * 0.37);
      matrix.compose(
        new THREE.Vector3(x, shoulder * (0.48 + (index % 3) * 0.052), z),
        treeQuaternion,
        new THREE.Vector3(scale * 1.4, scale * 0.62, scale),
      );
      mountainForest.setMatrixAt(index, matrix);
      canopyColor.setHSL(
        0.295 + (index % 5 - 2) * 0.004,
        0.1,
        0.62 + (index % 4) * 0.025,
      );
      mountainForest.setColorAt(index, canopyColor);
    }
    mountainForest.instanceMatrix.needsUpdate = true;
    mountainForest.instanceColor.needsUpdate = true;
    registerMesh(
      'mountain-forest-patches',
      mountainForest,
      groups.mountain,
      'protected-terrain',
    );
  }
  collider('mountain-collider', 'mountain', groups.mountain, [0, 11, 132], [112, 34, 35]);

  socket(
    'ReferenceCamera',
    SEOUL_REFERENCE_CAMERA_VIEW.position,
    SEOUL_REFERENCE_CAMERA_VIEW.rotation,
  );
  socket('AxisStart', [-13, 0, -33]);
  socket('OuterGate', [-13, 0, -19]);
  socket('InnerGate', [0, 0, 22]);
  socket('MainCourt', [0, 0, 40]);
  socket('MainHall', [0, 0, 62]);
  socket('RearHall', [0, 0, 84]);
  socket('MountainLookout', [0, 18, 116]);
  socket('VariantAnchor', [0, 0, 35]);
  socket(
    'outer-gate-left-hinge',
    [0, 0, 0],
    [0, 0, 0],
    runtime.nodes['outer-gate-west-leaf-pivot'],
    'outer-gate-west-leaf-pivot',
  );
  socket(
    'outer-gate-right-hinge',
    [0, 0, 0],
    [0, 0, 0],
    runtime.nodes['outer-gate-east-leaf-pivot'],
    'outer-gate-east-leaf-pivot',
  );
  socket(
    'inner-gate-left-hinge',
    [0, 0, 0],
    [0, 0, 0],
    runtime.nodes['inner-gate-west-leaf-pivot'],
    'inner-gate-west-leaf-pivot',
  );
  socket(
    'inner-gate-right-hinge',
    [0, 0, 0],
    [0, 0, 0],
    runtime.nodes['inner-gate-east-leaf-pivot'],
    'inner-gate-east-leaf-pivot',
  );
  socket(
    'main-hall-roof-apex',
    runtime.nodes['main-hall-roof'].userData.roofApexLocal,
    [0, 0, 0],
    runtime.nodes['main-hall-roof'],
    'main-hall-roof',
  );

  const semanticNodeAliases = {
    root: 'root',
    'foreground-system': 'foreground',
    'palace-axis-system': 'palace-axis',
    'palace-side-system': 'palace-side',
    'vegetation-system': 'vegetation',
    'city-system': 'city',
    'mountain-system': 'mountain',
    'foreground-strip': 'foreground-ground',
    'perimeter-wall': 'perimeter-wall-center',
    'outer-gate': 'outer-gate',
    'outer-court': 'outer-court',
    'processional-court': 'processional-court',
    'inner-gate': 'inner-gate',
    'main-hall': 'main-hall',
    'rear-hall': 'rear-hall',
    'secondary-hall': 'secondary-hall',
    'central-axis-walls': 'palace-axis',
    'east-corridor': 'east-corridor-1',
    'west-corridor': 'west-corridor-1',
    'east-pavilions': 'east-front-pavilion',
    'west-pavilions': 'west-front-pavilion',
    'service-courts': 'service-court-west',
    'tree-belt': 'tree-belt-instances',
    'palace-tree-clusters': 'tree-belt-instances',
    'foothill-forest': 'foothill-forest-mass',
    'urban-west': 'bounded-city-instances',
    'urban-center': 'bounded-city-instances',
    'urban-east': 'bounded-city-instances',
    'road-green-gaps': 'city-green-gap',
    'left-ridge': 'asymmetric-near-ridge',
    'central-saddle': 'asymmetric-near-ridge',
    'right-peak': 'asymmetric-near-ridge',
    'distant-ridge': 'distant-ridge-layer',
  };
  Object.entries(semanticNodeAliases).forEach(([semanticId, targetId]) => {
    const target = runtime.nodes[targetId] ?? runtime.meshes[targetId];
    if (!target) {
      throw new Error(`Semantic component "${semanticId}" is missing runtime target "${targetId}".`);
    }
    runtime.nodes[semanticId] = target;
  });

  const lensVisibility = {
    full: new Set(MACRO_GROUP_IDS),
    palace: new Set(['foreground', 'palace-axis', 'palace-side']),
    city: new Set(['city']),
    nature: new Set(['vegetation', 'mountain']),
  };
  let activeLens = 'full';
  let gateOpenAmount = 0;
  let turntableEnabled = false;
  const setLayerLens = (mode) => {
    if (!lensVisibility[mode]) {
      throw new RangeError(`Unsupported Layer Lens mode "${mode}".`);
    }
    activeLens = mode;
    Object.entries(groups).forEach(([id, layer]) => {
      layer.visible = lensVisibility[mode].has(id);
    });
    if (root.userData.sculptRuntime) {
      root.userData.sculptRuntime.interaction.activeLens = mode;
    }
  };
  const setGateOpen = (amount) => {
    if (!Number.isFinite(amount)) {
      throw new TypeError('Gate open amount must be a finite number.');
    }
    gateOpenAmount = THREE.MathUtils.clamp(amount, 0, 1);
    [
      'outer-gate-west-leaf-pivot',
      'outer-gate-east-leaf-pivot',
      'inner-gate-west-leaf-pivot',
      'inner-gate-east-leaf-pivot',
    ].forEach((id) => {
      const pivot = runtime.nodes[id];
      if (!pivot) return;
      const [minimum, maximum] = pivot.userData.actionPivot.limits;
      const openAngle = Math.abs(maximum) > Math.abs(minimum) ? maximum : minimum;
      pivot.rotation.y = openAngle * gateOpenAmount;
    });
    if (root.userData.sculptRuntime) {
      root.userData.sculptRuntime.interaction.gateOpenAmount = gateOpenAmount;
    }
  };
  const setTurntable = (enabled) => {
    turntableEnabled = Boolean(enabled);
    if (!turntableEnabled) root.rotation.y = 0;
    if (root.userData.sculptRuntime) {
      root.userData.sculptRuntime.interaction.turntableEnabled = turntableEnabled;
    }
  };

  const destructionGroupIndex = Object.fromEntries(
    Object.entries(runtime.destructionGroups).map(([id, objects]) => [
      id,
      objects.map((object) => object.userData.sculptId),
    ]),
  );
  root.userData.sculptRuntime = {
    schemaVersion: '1.0',
    seed,
    stage,
    importedMeshes: 0,
    macroGroupIds: [...MACRO_GROUP_IDS],
    nodeIds: Object.keys(runtime.nodes),
    meshIds: Object.keys(runtime.meshes),
    socketIds: Object.keys(runtime.sockets),
    colliderIds: Object.keys(runtime.colliders),
    semanticNodeAliases,
    destructionGroupIds: Object.keys(runtime.destructionGroups),
    destructionGroupIndex,
    materialEvidence: procedural?.metadata ?? null,
    interaction: {
      activeLens,
      gateOpenAmount,
      turntableEnabled,
      layerLensModes: Object.keys(lensVisibility),
      protectedArchitecture: true,
      detachableLightweightOrnamentsOnly: true,
    },
    optimization: {
      importedMeshes: 0,
      instanceWeightedTriangleBudget: 200000,
      sceneDrawableBudget: 220,
      fullFrameCallBudget: 400,
      directionalShadowMaps: 1,
      strategies: [
        'instanced-tree-canopy-and-trunk-clusters',
        'instanced-city-massing-and-roof-caps',
        'instanced-roof-tile-and-rafter-rhythm',
        'merged-four-sided-eaves-and-ridge-geometry',
        'semantic-spatial-layer-groups',
        'frustum-culling-and-linear-texture-minification',
      ],
      lodPolicy: 'No topology-changing distance LOD in canonical review; bounded distant systems use simplified instanced geometry.',
    },
  };
  root.userData.sculptDNA = {
    configuration: variant.id,
    topologyInvariant: 'seoul-palace-axis-and-six-layer-v1',
    deterministic: true,
    seed,
    controls: {
      roofRoughness: variant.roofRoughness,
      roofAccent: variant.roofAccent,
      courtyardRoughness: variant.courtyardRoughness,
      courtyardTone: variant.courtyardTone,
      treeDensity: variant.treeDensity,
      cityDensity: variant.cityDensity,
      mountainForestDensity: variant.mountainForestDensity,
      mountainRockDensity: variant.mountainRockDensity,
    },
  };
  root.userData.variantProvenance = variant.provenance ?? {
    base: true,
    invariantsPassed: true,
    reviewEvidenceReset: false,
  };

  let sceneDrawables = 0;
  let triangles = 0;
  let instances = 0;
  root.traverse((object) => {
    if (!object.isMesh) return;
    sceneDrawables += 1;
    const geometryTriangles = object.geometry.index
      ? object.geometry.index.count / 3
      : (object.geometry.getAttribute('position')?.count ?? 0) / 3;
    const count = object.isInstancedMesh ? object.count : 1;
    triangles += geometryTriangles * count;
    instances += object.isInstancedMesh ? object.count : 0;
  });

  let disposed = false;
  return {
    root,
    runtime,
    groups,
    materials,
    setLayerLens,
    setGateOpen,
    setTurntable,
    stats: {
      generationMs: performance.now() - started,
      seed,
      stage,
      variantId: variant.id,
      macroGroups: MACRO_GROUP_IDS.length,
      nodes: Object.keys(runtime.nodes).length,
      meshes: Object.keys(runtime.meshes).length,
      sceneDrawables,
      triangles: Math.round(triangles),
      instances,
      treeInstances: treeCount,
      cityInstances: cityCount,
      sockets: Object.keys(runtime.sockets).length,
      colliders: Object.keys(runtime.colliders).length,
      importedMeshes: 0,
      generatedTextureCount: procedural?.metadata.textureCount ?? 0,
    },
    update(elapsedSeconds) {
      if (turntableEnabled) root.rotation.y = elapsedSeconds * 0.08;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      runtime.resources.instancedMeshes.forEach((mesh) => mesh.dispose());
      runtime.resources.geometries.forEach((geometry) => geometry.dispose());
      runtime.resources.textures.forEach((texture) => texture.dispose());
      runtime.resources.materials.forEach((material) => material.dispose());
    },
  };
}
