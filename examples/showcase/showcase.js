import * as THREE from './node_modules/three/build/three.module.js';

const params = new URLSearchParams(window.location.search);
const sceneId = params.get('scene') ?? 'tree';
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
document.body.prepend(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 0.1, 200);
const title = document.querySelector('#title');
const subtitle = document.querySelector('#subtitle');

function mulberry32(seed) {
  return () => {
    let value = seed += 0x6D2B79F5;
    value = Math.imul(value ^ value >>> 15, value | 1);
    value ^= value + Math.imul(value ^ value >>> 7, value | 61);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}

function hashString(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function stableVariantSeed(spec, fallback) {
  const identity = spec.targetId
    ?? spec.variantProvenance?.variantId
    ?? spec.variantProvenance?.variantSeed
    ?? fallback;
  return hashString(String(identity));
}

function materialSpec(spec, id) {
  return spec.materials.find((item) => item.id === id) ?? {};
}

function paletteColor(spec, id, fallback) {
  const material = materialSpec(spec, id);
  const palette = material.colorVariation?.palette;
  return new THREE.Color(Array.isArray(palette) && palette[0] ? palette[0] : material.baseColor ?? fallback);
}

function identityColor(spec, id, fallback, identityWeight = 0.45) {
  return paletteColor(spec, id, fallback).lerp(new THREE.Color(fallback), identityWeight);
}

function repetitionCount(spec, id, fallback) {
  return spec.repetitionSystems.find((item) => item.id === id)?.count ?? fallback;
}

function roughnessValue(spec, id, fallback) {
  const roughness = materialSpec(spec, id).roughness;
  return typeof roughness?.base === 'number' ? roughness.base : fallback;
}

function standard(color, roughness = 0.65, metalness = 0, emissive = 0x000000, intensity = 0) {
  return new THREE.MeshPhysicalMaterial({
    color,
    roughness,
    metalness,
    emissive,
    emissiveIntensity: intensity,
    clearcoat: metalness > 0.2 ? 0.22 : 0.04,
    clearcoatRoughness: 0.3,
  });
}

function box(group, size, position, material, rotation = [0, 0, 0]) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), material);
  mesh.position.set(...position);
  mesh.rotation.set(...rotation);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  group.add(mesh);
  return mesh;
}

function cylinderBetween(group, start, end, radiusStart, radiusEnd, material, radialSegments = 12) {
  const startVector = new THREE.Vector3(...start);
  const endVector = new THREE.Vector3(...end);
  const delta = endVector.clone().sub(startVector);
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(radiusEnd, radiusStart, delta.length(), radialSegments, 4),
    material,
  );
  mesh.position.copy(startVector).add(endVector).multiplyScalar(0.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), delta.normalize());
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  group.add(mesh);
  return mesh;
}

function ground(width, depth, color) {
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(width, depth),
    new THREE.MeshStandardMaterial({ color, roughness: 0.92, metalness: 0 }),
  );
  mesh.rotation.x = -Math.PI / 2;
  mesh.receiveShadow = true;
  scene.add(mesh);
  return mesh;
}

function setupLights(mode) {
  scene.add(new THREE.HemisphereLight(mode === 'tree' ? 0x7ab5ff : 0xe9f3ff, mode === 'tree' ? 0x1d160f : 0x75674f, mode === 'tree' ? 1.5 : 2.0));
  const key = new THREE.DirectionalLight(mode === 'tree' ? 0xffd59a : 0xfff0d2, mode === 'tree' ? 4.2 : 3.4);
  key.position.set(-8, 14, 10);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left = -30;
  key.shadow.camera.right = 30;
  key.shadow.camera.top = 24;
  key.shadow.camera.bottom = -12;
  scene.add(key);
  const rim = new THREE.DirectionalLight(mode === 'tree' ? 0x3fdcff : 0x8dc6ff, 1.6);
  rim.position.set(10, 8, -14);
  scene.add(rim);
}

function createStars(count, seed) {
  const rng = mulberry32(seed);
  const positions = new Float32Array(count * 3);
  for (let index = 0; index < count; index += 1) {
    positions[index * 3] = (rng() - 0.5) * 55;
    positions[index * 3 + 1] = 5 + rng() * 20;
    positions[index * 3 + 2] = -8 - rng() * 18;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  scene.add(new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0x9ddcff, size: 0.05 })));
}

function createTree(spec, index) {
  const group = new THREE.Group();
  const rng = mulberry32(stableVariantSeed(spec, `tree-${index}`));
  const barkColor = paletteColor(spec, 'bark', '#5a341f');
  const goldColor = identityColor(spec, 'gold-energy', '#ffb347', 0.55);
  const amberColor = identityColor(spec, 'amber-leaf', '#f2a545', 0.58);
  const cyanColor = identityColor(spec, 'cyan-leaf', '#38cde0', 0.62);
  const bark = standard(barkColor, roughnessValue(spec, 'bark', 0.72));
  const gold = standard(goldColor, roughnessValue(spec, 'gold-energy', 0.24), 0, goldColor, 3.2);
  const amber = standard(amberColor, roughnessValue(spec, 'amber-leaf', 0.45), 0, amberColor, 1.1);
  const cyan = standard(cyanColor, roughnessValue(spec, 'cyan-leaf', 0.36), 0, cyanColor, 1.8);

  cylinderBetween(group, [0, 0, 0], [0.08, 4.5, 0], 0.72, 0.42, bark, 18);
  const branches = [
    [[0, 3.3, 0], [-2.6, 6.2, 0.25], 0.46, 0.17],
    [[0.05, 3.4, 0], [2.55, 6.25, 0.1], 0.45, 0.16],
    [[0.03, 3.5, 0], [0.2, 7.5, -0.1], 0.38, 0.1],
    [[-1.5, 5.0, 0.1], [-3.8, 6.6, 0.4], 0.22, 0.06],
    [[1.45, 5.0, 0.05], [3.7, 6.8, 0.2], 0.22, 0.06],
    [[-1.0, 5.0, -0.05], [-2.4, 6.1, -1.1], 0.18, 0.05],
    [[1.0, 5.0, -0.1], [2.5, 6.2, -1.05], 0.18, 0.05],
  ];
  branches.forEach(([start, end, startRadius, endRadius]) => {
    cylinderBetween(group, start, end, startRadius, endRadius, bark, 14);
    const offsetStart = [start[0], start[1], start[2] + 0.04];
    const offsetEnd = [end[0], end[1], end[2] + 0.04];
    cylinderBetween(group, offsetStart, offsetEnd, startRadius * 0.12, endRadius * 0.16, gold, 8);
  });
  cylinderBetween(group, [0, 0.25, 0.55], [0.05, 4.7, 0.45], 0.1, 0.055, gold, 10);
  [
    [[0, 0.35, 0], [-1.5, 0.05, 0.8]],
    [[0, 0.35, 0], [1.5, 0.05, 0.75]],
    [[0, 0.3, 0], [-0.8, 0.02, -1.1]],
    [[0, 0.3, 0], [0.9, 0.02, -1.05]],
  ].forEach(([start, end]) => cylinderBetween(group, start, end, 0.34, 0.08, bark, 12));

  const amberCount = Math.min(120, Math.max(54, Math.round(repetitionCount(spec, 'amber-leaf-clusters', 520) / 6)));
  const cyanCount = Math.min(36, Math.max(14, Math.round(repetitionCount(spec, 'cyan-leaf-accents', 112) / 5)));
  const leafGeometry = new THREE.IcosahedronGeometry(0.12, 0);
  const amberLeaves = new THREE.InstancedMesh(leafGeometry, amber, amberCount);
  const cyanLeaves = new THREE.InstancedMesh(leafGeometry, cyan, cyanCount);
  const matrix = new THREE.Matrix4();
  const placeLeaf = (mesh, leafIndex, isCyan) => {
    const side = rng() < 0.48 ? -1 : 1;
    const radius = 0.65 + rng() * 3.0;
    const x = side * (0.5 + radius);
    const y = 4.9 + rng() * 2.7 - Math.abs(x) * 0.12;
    const z = (rng() - 0.5) * 2.5;
    const scale = (isCyan ? 0.8 : 1.0) * (0.7 + rng() * 1.4);
    matrix.compose(
      new THREE.Vector3(x, y, z),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(rng() * Math.PI, rng() * Math.PI, rng() * Math.PI)),
      new THREE.Vector3(scale * 1.8, scale * 0.65, scale),
    );
    mesh.setMatrixAt(leafIndex, matrix);
  };
  for (let leafIndex = 0; leafIndex < amberCount; leafIndex += 1) placeLeaf(amberLeaves, leafIndex, false);
  for (let leafIndex = 0; leafIndex < cyanCount; leafIndex += 1) placeLeaf(cyanLeaves, leafIndex, true);
  amberLeaves.castShadow = true;
  cyanLeaves.castShadow = true;
  group.add(amberLeaves, cyanLeaves);

  const nodeCount = Math.min(18, Math.max(8, Math.round(repetitionCount(spec, 'constellation-nodes', 32) / 2)));
  const nodeGeometry = new THREE.SphereGeometry(0.055, 10, 8);
  const nodes = new THREE.InstancedMesh(nodeGeometry, cyan, nodeCount);
  const constellationPoints = [];
  for (let nodeIndex = 0; nodeIndex < nodeCount; nodeIndex += 1) {
    const angle = nodeIndex / nodeCount * Math.PI * 2;
    const point = new THREE.Vector3(
      Math.cos(angle) * 3.2,
      6.1 + Math.sin(angle * 2) * 0.7,
      0.8 + Math.sin(angle) * 0.7,
    );
    constellationPoints.push(point);
    matrix.makeTranslation(point.x, point.y, point.z);
    nodes.setMatrixAt(nodeIndex, matrix);
  }
  group.add(nodes);
  const constellation = new THREE.LineLoop(
    new THREE.BufferGeometry().setFromPoints(constellationPoints),
    new THREE.LineBasicMaterial({ color: cyanColor, transparent: true, opacity: 0.48 }),
  );
  group.add(constellation);
  const strandCount = Math.min(8, Math.max(2, Math.round(repetitionCount(spec, 'hanging-light-strands', 18) / 4)));
  for (let strand = 0; strand < strandCount; strand += 1) {
    const x = -2.8 + strand * (5.6 / Math.max(1, strandCount - 1));
    cylinderBetween(group, [x, 5.7, 0.4], [x, 4.8 - strand * 0.08, 0.4], 0.022, 0.012, gold, 6);
    const light = new THREE.Mesh(new THREE.SphereGeometry(0.07, 10, 8), gold);
    light.position.set(x, 4.78 - strand * 0.08, 0.4);
    group.add(light);
  }
  group.scale.setScalar(0.78);
  return group;
}

function createWheel(material, hubMaterial, treadCount) {
  const group = new THREE.Group();
  const tire = new THREE.Mesh(new THREE.CylinderGeometry(0.72, 0.72, 0.48, 24), material);
  tire.rotation.x = Math.PI / 2;
  tire.castShadow = true;
  group.add(tire);
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.52, 16), hubMaterial);
  hub.rotation.x = Math.PI / 2;
  group.add(hub);
  const treadMaterial = standard(0x0a0c0a, 0.92);
  for (let index = 0; index < treadCount; index += 1) {
    const angle = index / treadCount * Math.PI * 2;
    const tread = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.16, 0.48), treadMaterial);
    tread.position.set(Math.cos(angle) * 0.76, Math.sin(angle) * 0.76, 0);
    tread.rotation.z = angle;
    group.add(tread);
  }
  return group;
}

function createVehicle(spec, index) {
  const group = new THREE.Group();
  const bodyColor = paletteColor(spec, 'body-shell', '#6e7476');
  const trimColor = paletteColor(spec, 'dark-trim', '#171a19');
  const accentColor = paletteColor(spec, 'accent', '#d87927');
  const lampColor = paletteColor(spec, 'lamp', '#ffd782');
  const body = standard(bodyColor, roughnessValue(spec, 'body-shell', 0.58), 0.08);
  const trim = standard(trimColor, roughnessValue(spec, 'dark-trim', 0.76), 0.12);
  const accent = standard(accentColor, roughnessValue(spec, 'accent', 0.5), 0.08);
  const roof = standard(
    paletteColor(spec, 'roof-shell', '#d8d8d2'),
    roughnessValue(spec, 'roof-shell', 0.56),
    0.03,
  );
  const rubber = standard(
    paletteColor(spec, 'rubber', '#111311'),
    roughnessValue(spec, 'rubber', 0.9),
  );
  const glass = new THREE.MeshPhysicalMaterial({
    color: paletteColor(spec, 'glass', '#29434a'),
    roughness: roughnessValue(spec, 'glass', 0.16),
    metalness: 0.05,
    transmission: 0.18,
    transparent: true,
    opacity: 0.9,
  });
  const lamp = standard(lampColor, roughnessValue(spec, 'lamp', 0.24), 0, lampColor, 2.5);
  box(group, [5.8, 0.7, 2.6], [0, 1.15, 0], body);
  box(group, [2.0, 0.6, 2.45], [-2.05, 1.7, 0], body, [0, 0, 0.03]);
  box(group, [2.35, 1.55, 2.4], [-0.45, 2.15, 0], body);
  box(group, [2.65, 0.28, 2.5], [-0.38, 3.0, 0], roof);
  box(group, [1.9, 0.75, 2.35], [1.85, 1.65, 0], trim);
  box(group, [0.18, 0.95, 2.15], [-1.5, 2.3, 0], glass, [0, 0, -0.2]);
  box(group, [2.55, 0.18, 2.5], [-0.35, 3.1, 0], trim);
  box(group, [0.35, 0.45, 2.85], [-3.0, 1.15, 0], accent);
  box(group, [0.22, 0.65, 2.6], [2.95, 1.3, 0], trim);
  box(group, [4.6, 0.18, 0.08], [-0.1, 1.55, 1.34], accent);
  box(group, [4.6, 0.18, 0.08], [-0.1, 1.55, -1.34], accent);
  box(group, [1.85, 0.12, 0.1], [-0.35, 3.28, 1.1], trim);
  box(group, [1.85, 0.12, 0.1], [-0.35, 3.28, -1.1], trim);
  [-1.1, 0.4].forEach((x) => box(group, [0.1, 0.12, 2.2], [x, 3.28, 0], trim));
  const treadCount = Math.max(10, Math.min(20, Math.round(repetitionCount(spec, 'wheel-treads', 64) / 4)));
  [-2.0, 2.0].forEach((x) => {
    [-1.45, 1.45].forEach((z) => {
      const wheel = createWheel(rubber, trim, treadCount);
      wheel.position.set(x, 0.72, z);
      group.add(wheel);
    });
  });
  const studCount = Math.min(40, Math.max(18, Math.round(repetitionCount(spec, 'body-studs', 72) / 2)));
  const studGeometry = new THREE.CylinderGeometry(0.07, 0.07, 0.055, 10);
  const studs = new THREE.InstancedMesh(studGeometry, body, studCount);
  const matrix = new THREE.Matrix4();
  for (let studIndex = 0; studIndex < studCount; studIndex += 1) {
    const row = Math.floor(studIndex / 10);
    const column = studIndex % 10;
    matrix.makeTranslation(-2.7 + column * 0.58, 1.54 + row * 0.16, 1.31);
    matrix.multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2));
    studs.setMatrixAt(studIndex, matrix);
  }
  group.add(studs);
  const lampCount = Math.max(3, Math.min(7, repetitionCount(spec, 'roof-lamps', 5)));
  for (let lightIndex = 0; lightIndex < lampCount; lightIndex += 1) {
    const lightMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.12, 12), lamp);
    lightMesh.rotation.x = Math.PI / 2;
    lightMesh.position.set(-1.15 + lightIndex * (2.3 / Math.max(1, lampCount - 1)), 3.28, 1.24);
    group.add(lightMesh);
  }
  [-0.78, 0.78].forEach((z) => {
    const headlight = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.12, 14), lamp);
    headlight.rotation.z = Math.PI / 2;
    headlight.position.set(-3.2, 1.58, z);
    group.add(headlight);
  });
  group.rotation.y = -0.45;
  group.scale.setScalar(0.88);
  return group;
}

function palaceRoof(group, position, size, material) {
  const roof = new THREE.Mesh(new THREE.ConeGeometry(1, 0.55, 4), material);
  roof.position.set(...position);
  roof.rotation.y = Math.PI / 4;
  roof.scale.set(size[0], size[1], size[2]);
  roof.castShadow = true;
  group.add(roof);
}

function createSeoul(spec, index) {
  const group = new THREE.Group();
  const courtyard = standard(
    paletteColor(spec, 'courtyard', '#c9b58b'),
    roughnessValue(spec, 'courtyard', 0.88),
  );
  const wall = standard(
    paletteColor(spec, 'palace-wall', '#bdae8c'),
    roughnessValue(spec, 'palace-wall', 0.72),
  );
  const roof = standard(
    paletteColor(spec, 'roof', '#202827'),
    roughnessValue(spec, 'roof', 0.78),
  );
  const mountain = standard(
    paletteColor(spec, 'mountain', '#254d36'),
    roughnessValue(spec, 'mountain', 0.94),
  );
  const city = standard(
    paletteColor(spec, 'city', '#cbd0cc'),
    roughnessValue(spec, 'city', 0.8),
  );
  const vegetation = standard(
    paletteColor(spec, 'vegetation', '#39704a'),
    roughnessValue(spec, 'vegetation', 0.92),
  );
  box(group, [10.5, 0.25, 8.0], [0, 0, 0], courtyard);
  box(group, [4.1, 1.35, 2.2], [1.5, 0.8, -1.6], wall);
  palaceRoof(group, [1.5, 1.75, -1.6], [2.8, 1.0, 1.6], roof);
  box(group, [3.2, 1.1, 1.0], [-3.0, 0.68, 2.5], wall);
  palaceRoof(group, [-3.0, 1.45, 2.5], [2.2, 0.85, 0.9], roof);
  const roofCount = Math.min(18, Math.max(8, repetitionCount(spec, 'palace-roofs', 14)));
  for (let roofIndex = 0; roofIndex < roofCount; roofIndex += 1) {
    const side = roofIndex % 2 === 0 ? -1 : 1;
    const row = Math.floor(roofIndex / 4);
    const x = side * (1.7 + (roofIndex % 4) * 0.75);
    const z = -0.4 + row * 1.25;
    box(group, [1.25, 0.55, 0.72], [x, 0.45, z], wall);
    palaceRoof(group, [x, 0.86, z], [0.9, 0.55, 0.55], roof);
  }
  const buildingCount = Math.min(58, Math.max(24, repetitionCount(spec, 'urban-blocks', 48)));
  const rng = mulberry32(stableVariantSeed(spec, `seoul-${index}`));
  for (let buildingIndex = 0; buildingIndex < buildingCount; buildingIndex += 1) {
    const width = 0.3 + rng() * 0.45;
    const height = 0.35 + rng() * 1.2;
    const x = (rng() - 0.5) * 12;
    const z = -5.2 - rng() * 2.2;
    box(group, [width, height, width * (0.8 + rng() * 0.6)], [x, height / 2, z], city);
  }
  const treeCount = Math.min(90, Math.max(36, repetitionCount(spec, 'tree-clusters', 72)));
  const treeGeometry = new THREE.IcosahedronGeometry(0.18, 0);
  const trees = new THREE.InstancedMesh(treeGeometry, vegetation, treeCount);
  const matrix = new THREE.Matrix4();
  for (let treeIndex = 0; treeIndex < treeCount; treeIndex += 1) {
    const x = (rng() - 0.5) * 11;
    const z = -2.6 - rng() * 2.2;
    const scale = 0.7 + rng() * 1.3;
    matrix.compose(new THREE.Vector3(x, 0.25 + scale * 0.1, z), new THREE.Quaternion(), new THREE.Vector3(scale, scale * 1.3, scale));
    trees.setMatrixAt(treeIndex, matrix);
  }
  group.add(trees);
  const peakCount = Math.min(9, Math.max(5, repetitionCount(spec, 'mountain-peaks', 7)));
  for (let peakIndex = 0; peakIndex < peakCount; peakIndex += 1) {
    const x = -7 + peakIndex * (14 / Math.max(1, peakCount - 1));
    const height = 2.2 + rng() * 2.2;
    const peak = new THREE.Mesh(new THREE.ConeGeometry(2.2 + rng(), height, 7), mountain);
    peak.position.set(x, height / 2 - 0.2, -9.0 - rng() * 1.0);
    peak.scale.z = 0.7;
    group.add(peak);
  }
  group.scale.setScalar(0.8);
  return group;
}

const config = {
  tree: {
    title: 'Repolis Tree · Sculpt DNA Family',
    subtitle: 'Botanical emission, leaf density, and constellation variants',
    prefix: 'repolis-tree',
    background: 0x06101a,
    fog: 0x06101a,
    positions: [-8.0, 0, 8.0],
    camera: [0, 7.0, 25],
    target: [0, 3.0, 0],
    ground: 0x172117,
    factory: createTree,
  },
  brick: {
    title: 'Brick Off-Road Explorer · Sculpt DNA Family',
    subtitle: 'Olive panel palette, tread density, and expedition-detail variants',
    prefix: 'brick-offroad',
    background: 0x13191c,
    fog: 0x13191c,
    positions: [-6.5, 0, 6.5],
    camera: [0, 5.2, 19],
    target: [0, 1.15, 0],
    ground: 0x4c514d,
    factory: createVehicle,
  },
  seoul: {
    title: 'Seoul Palace Challenge · Sculpt DNA Family',
    subtitle: 'Palace, city-density, vegetation, and mountain-layer variants',
    prefix: 'seoul-challenge',
    background: 0x89b4dc,
    fog: 0xa9c7df,
    positions: [-10.5, 0, 10.5],
    camera: [0, 14.5, 28],
    target: [0, 0.5, -2.0],
    ground: 0x8da57d,
    factory: createSeoul,
  },
}[sceneId];

if (!config) throw new Error(`Unknown showcase scene: ${sceneId}`);
title.textContent = config.title;
subtitle.textContent = config.subtitle;
scene.background = new THREE.Color(config.background);
scene.fog = new THREE.Fog(config.fog, sceneId === 'seoul' ? 24 : 28, sceneId === 'seoul' ? 48 : 52);
camera.position.set(...config.camera);
camera.lookAt(...config.target);
setupLights(sceneId);
ground(sceneId === 'seoul' ? 44 : 36, sceneId === 'seoul' ? 32 : 18, config.ground);
if (sceneId === 'tree') createStars(420, 20260711);

const specs = await Promise.all(
  [1, 2, 3].map((index) =>
    fetch(`./variants/${sceneId}/${config.prefix}-v${String(index).padStart(3, '0')}.json`).then((response) => {
      if (!response.ok) throw new Error(`Could not load variant ${index}`);
      return response.json();
    }),
  ),
);
specs.forEach((spec, index) => {
  const model = config.factory(spec, index);
  model.position.x = config.positions[index];
  scene.add(model);
});

let frame = 0;
function render() {
  frame += 1;
  renderer.render(scene, camera);
  if (frame === 4) {
    window.__SHOWCASE_READY__ = true;
    document.body.dataset.ready = 'true';
  }
  requestAnimationFrame(render);
}
render();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});
