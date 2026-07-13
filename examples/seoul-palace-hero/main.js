import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import {
  SEOUL_REFERENCE_CAMERA_VIEW,
  SEOUL_STAGES,
  createSeoulPalaceHero,
} from './seoul-output/createSeoulPalaceHero.js';
import variantConfig from './seoul-output/seoul-variant-config.json';

const query = new URLSearchParams(window.location.search);
if (query.get('ui') === '0') document.documentElement.dataset.ui = 'hidden';
if (['127.0.0.1', 'localhost'].includes(window.location.hostname)) {
  document.querySelectorAll('[data-flagship="tree"]').forEach((link) => {
    link.href = 'http://127.0.0.1:4174/';
  });
  document.querySelectorAll('[data-flagship="brick"]').forEach((link) => {
    link.href = 'http://127.0.0.1:4176/';
  });
  document.querySelectorAll('[data-flagship="seoul"]').forEach((link) => {
    link.href = 'http://127.0.0.1:4178/threejs-sculpt-dna/seoul/';
  });
}
const requestedStage = query.get('stage') ?? 'optimization-pass';
const stage = SEOUL_STAGES.includes(requestedStage) ? requestedStage : 'blockout';
const requestedView = query.get('view') ?? 'reference';
const requestedLight = query.get('light') ?? 'reference';
const requestedLens = query.get('lens') ?? 'full';
const requestedGateOpen = Number.parseFloat(query.get('gate') ?? '0');
const parsedVariant = Number.parseInt(query.get('variant') ?? '0', 10);
const requestedVariant = Number.isInteger(parsedVariant)
  && parsedVariant >= 0
  && parsedVariant <= variantConfig.variants.length
  ? parsedVariant
  : 0;
const captureMode = query.get('capture') === '1';
if (captureMode) document.documentElement.dataset.capture = 'true';
let canonicalElapsed = Number.parseFloat(query.get('time') ?? '1.25');
if (!Number.isFinite(canonicalElapsed)) canonicalElapsed = 1.25;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let autoDrift = query.get('motion') !== '0' && !captureMode && !reducedMotion;
let elapsed = captureMode ? canonicalElapsed : 0;

const sceneContainer = document.querySelector('#scene');
const loadingStatus = document.querySelector('#loading');
const renderer = new THREE.WebGLRenderer({
  antialias: true,
  alpha: false,
  preserveDrawingBuffer: true,
  powerPreference: 'high-performance',
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.info.autoReset = false;
sceneContainer.append(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xb9cfda);
scene.fog = new THREE.Fog(0xb9cfda, 122, 242);
const camera = new THREE.PerspectiveCamera(
  35,
  window.innerWidth / window.innerHeight,
  0.1,
  360,
);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.07;
controls.minDistance = 48;
controls.maxDistance = 190;
controls.maxPolarAngle = Math.PI * 0.48;

const CAMERA_VIEWS = {
  reference: SEOUL_REFERENCE_CAMERA_VIEW,
  axis: {
    position: [0, 13, -58],
    target: [0, 4.5, 61],
  },
  side: {
    position: [-76, 28, 18],
    target: [0, 4, 50],
  },
  mountain: {
    position: [-20, 28, 50],
    target: [0, 13, 133],
  },
  material: {
    position: [-22, 14, 35],
    target: [0, 6.2, 62],
  },
  hierarchy: {
    position: [43, 27, -18],
    target: [0, 4, 43],
  },
};

function setCameraView(viewId) {
  const view = CAMERA_VIEWS[viewId];
  if (!view) throw new RangeError(`Unsupported Seoul camera view "${viewId}".`);
  camera.position.fromArray(view.position);
  controls.target.fromArray(view.target);
  controls.update();
}

function setReferenceView() {
  setCameraView('reference');
}

function setMaterialView() {
  setCameraView('material');
}

const keyboardOffset = new THREE.Vector3();
const keyboardSpherical = new THREE.Spherical();
function moveCameraFromKeyboard(key) {
  if (key === 'Home') {
    setReferenceView();
    return true;
  }
  keyboardOffset.subVectors(camera.position, controls.target);
  keyboardSpherical.setFromVector3(keyboardOffset);
  if (key === 'ArrowLeft') keyboardSpherical.theta -= 0.08;
  else if (key === 'ArrowRight') keyboardSpherical.theta += 0.08;
  else if (key === 'ArrowUp') keyboardSpherical.phi -= 0.06;
  else if (key === 'ArrowDown') keyboardSpherical.phi += 0.06;
  else if (key === '+' || key === '=') keyboardSpherical.radius *= 0.9;
  else if (key === '-' || key === '_') keyboardSpherical.radius *= 1.1;
  else return false;
  keyboardSpherical.phi = THREE.MathUtils.clamp(
    keyboardSpherical.phi,
    0.08,
    controls.maxPolarAngle,
  );
  keyboardSpherical.radius = THREE.MathUtils.clamp(
    keyboardSpherical.radius,
    controls.minDistance,
    controls.maxDistance,
  );
  keyboardOffset.setFromSpherical(keyboardSpherical);
  camera.position.copy(controls.target).add(keyboardOffset);
  controls.update();
  return true;
}

sceneContainer.addEventListener('keydown', (event) => {
  if (!moveCameraFromKeyboard(event.key)) return;
  event.preventDefault();
  tourActive = false;
  autoDrift = false;
  hero.setTurntable(false);
  syncTourButton();
  syncMotionButton();
  renderFrame();
});
sceneContainer.addEventListener('pointerdown', () => {
  sceneContainer.focus({ preventScroll: true });
});

setCameraView(CAMERA_VIEWS[requestedView] ? requestedView : 'reference');

const hemisphere = new THREE.HemisphereLight(0xdbe8ed, 0x776f56, 1.65);
scene.add(hemisphere);
const key = new THREE.DirectionalLight(0xfff4db, 2.35);
key.position.set(-45, 82, -32);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.left = -80;
key.shadow.camera.right = 80;
key.shadow.camera.top = 100;
key.shadow.camera.bottom = -50;
key.shadow.camera.near = 10;
key.shadow.camera.far = 230;
key.shadow.bias = -0.0002;
key.shadow.normalBias = 0.04;
key.shadow.radius = 2.4;
key.target.position.set(0, 2.5, 46);
scene.add(key);
scene.add(key.target);
const fill = new THREE.DirectionalLight(0xc9e0ef, 0.58);
fill.position.set(58, 38, -18);
fill.target.position.set(0, 3, 52);
fill.castShadow = false;
scene.add(fill, fill.target);
const rim = new THREE.DirectionalLight(0xe6f1f5, 0.72);
rim.position.set(-8, 45, 128);
rim.target.position.set(0, 5, 58);
rim.castShadow = false;
scene.add(rim, rim.target);

function setLightMode(mode) {
  if (mode === 'neutral') {
    hemisphere.intensity = 1.9;
    hemisphere.color.set(0xe8edf0);
    hemisphere.groundColor.set(0x7f8178);
    key.intensity = 1.55;
    key.color.set(0xffffff);
    key.position.set(-20, 70, -26);
    fill.intensity = 0.72;
    fill.color.set(0xdce6ea);
    rim.intensity = 0.42;
    rim.color.set(0xffffff);
    renderer.toneMappingExposure = 1;
    scene.fog.near = 138;
    scene.fog.far = 258;
    scene.background.set(0xbac1c4);
    scene.fog.color.set(0xbac1c4);
  } else if (mode === 'grazing') {
    hemisphere.intensity = 0.72;
    hemisphere.color.set(0xb8cad2);
    hemisphere.groundColor.set(0x4a4037);
    key.intensity = 3.1;
    key.color.set(0xffd6a1);
    key.position.set(68, 14, 22);
    fill.intensity = 0.22;
    fill.color.set(0x7894a8);
    rim.intensity = 0.62;
    rim.color.set(0xbfdbea);
    renderer.toneMappingExposure = 0.92;
    scene.fog.near = 145;
    scene.fog.far = 270;
    scene.background.set(0x788891);
    scene.fog.color.set(0x788891);
  } else {
    hemisphere.intensity = 1.34;
    hemisphere.color.set(0xdbe5e8);
    hemisphere.groundColor.set(0x756c57);
    key.intensity = 2.48;
    key.color.set(0xffefd2);
    key.position.set(-58, 64, -38);
    fill.intensity = 0.34;
    fill.color.set(0xb8cfdd);
    rim.intensity = 0.58;
    rim.color.set(0xdceaf0);
    renderer.toneMappingExposure = 1.03;
    scene.fog.near = 148;
    scene.fog.far = 282;
    scene.background.set(0xa9c1d2);
    scene.fog.color.set(0xa9c1d2);
  }
  key.target.updateMatrixWorld();
}
setLightMode(requestedLight);

const selectedVariant = requestedVariant > 0
  ? variantConfig.variants[requestedVariant - 1] ?? variantConfig.base
  : variantConfig.base;
const hero = createSeoulPalaceHero({
  seed: selectedVariant.seed,
  stage,
  variant: selectedVariant,
});
scene.add(hero.root);
const initialLens = ['full', 'palace', 'city', 'nature'].includes(requestedLens)
  ? requestedLens
  : 'full';
const initialGateOpen = Number.isFinite(requestedGateOpen)
  ? THREE.MathUtils.clamp(requestedGateOpen, 0, 1)
  : 0;
hero.setLayerLens(initialLens);
hero.setGateOpen(initialGateOpen);
hero.setTurntable(autoDrift);
hero.root.userData.lightingProfile = {
  mode: requestedLight,
  toneMapping: 'ACESFilmicToneMapping',
  exposure: renderer.toneMappingExposure,
  key: { type: 'directional', castsShadow: true, mapSize: 2048 },
  fill: { type: 'directional', castsShadow: false },
  rimEnvironment: { type: 'directional', castsShadow: false },
  contactShadow: 'directional PCF soft shadow plus independent AO maps',
  fog: { type: 'linear', near: scene.fog.near, far: scene.fog.far },
};

const stageLabels = {
  blockout: ['Blockout', 'Macro silhouette · flat materials'],
  'structural-pass': ['Structural pass', 'Attachments · pivots · repeated bays'],
  'form-refinement': ['Form refinement', 'Hip ridges · lifted eaves · tiered podiums'],
  'material-pass': ['Material pass', 'Independent 1024px PBR fields · regional palette evidence'],
  'surface-pass': ['Surface pass', 'Tile rhythm · dancheong · local wear · rock breakup'],
  'lighting-pass': ['Lighting pass', 'Key · fill · rim · contact shadow · restrained haze'],
  'interaction-pass': ['Interaction pass', 'Layer Lens · camera tour · hinged gates · turntable'],
  'optimization-pass': ['Optimization pass', 'Instancing · culling · deterministic six-view review'],
};
const [stageName, stageScope] = stageLabels[stage];
document.querySelector('#stage-name').textContent = stageName;
document.querySelector('#stage-scope').textContent = stageScope;
document.querySelector('#variant-name').textContent = requestedVariant > 0
  ? `Curated DNA ${String(requestedVariant).padStart(2, '0')} / 03`
  : 'Production base';
document.querySelector('#next-variant').addEventListener('click', () => {
  const nextVariant = (Math.max(0, requestedVariant) + 1) % 4;
  const next = new URL(window.location.href);
  next.searchParams.set('variant', String(nextVariant));
  window.location.assign(next);
});

document.querySelector('#generation-time').textContent =
  `${hero.stats.generationMs.toFixed(0)} ms generation`;
document.querySelector('#geometry-stats').textContent =
  `${hero.stats.triangles.toLocaleString()} triangles · ${hero.stats.instances} instances`;

function getRenderInfo() {
  return {
    calls: renderer.info.render.calls,
    triangles: renderer.info.render.triangles,
    lines: renderer.info.render.lines,
    points: renderer.info.render.points,
    frame: renderer.info.render.frame,
    memory: { ...renderer.info.memory },
    sourceFingerprint: __SEOUL_SOURCE_FINGERPRINT__,
    runtimeFingerprint: __SEOUL_RUNTIME_FINGERPRINT__,
  };
}

function renderFrame() {
  renderer.info.reset();
  renderer.render(scene, camera);
}

window.__SEOUL_HERO__ = hero;
window.__SEOUL_READY__ = false;
window.__getSeoulRenderInfo = getRenderInfo;
window.__getSeoulLightingProfile = () => ({ ...hero.root.userData.lightingProfile });
window.__renderSeoulFrame = renderFrame;
window.__setSeoulReferenceView = () => {
  setReferenceView();
  renderFrame();
};
window.__setSeoulMaterialView = () => {
  setMaterialView();
  renderFrame();
};
window.__setSeoulCameraView = (viewId = 'reference') => {
  setCameraView(viewId);
  renderFrame();
};
window.__setSeoulLayerLens = (mode = 'full') => {
  hero.setLayerLens(mode);
  renderFrame();
};
window.__setSeoulGateOpen = (amount = 0) => {
  hero.setGateOpen(amount);
  renderFrame();
};
window.__setSeoulLightMode = (mode = 'reference') => {
  setLightMode(mode);
  hero.root.userData.lightingProfile.mode = mode;
  hero.root.userData.lightingProfile.exposure = renderer.toneMappingExposure;
  hero.root.userData.lightingProfile.fog = {
    type: 'linear',
    near: scene.fog.near,
    far: scene.fog.far,
  };
  renderFrame();
};
window.__setSeoulCaptureTime = (value = 1.25) => {
  canonicalElapsed = Number.isFinite(value) ? value : 1.25;
  elapsed = canonicalElapsed;
  hero.update(elapsed);
  controls.update();
  renderFrame();
};

const motionButton = document.querySelector('#toggle-motion');
const gateButton = document.querySelector('#toggle-gates');
const tourButton = document.querySelector('#toggle-tour');
const cameraPicker = document.querySelector('#camera-view');
const lensButtons = [...document.querySelectorAll('[data-lens]')];
const referenceDialog = document.querySelector('#reference-dialog');
let gatesOpen = initialGateOpen >= 0.5;
let tourActive = query.get('tour') === '1'
  && (!captureMode || query.get('captureTour') === '1')
  && !reducedMotion;

document.querySelector('#open-reference').addEventListener('click', () => referenceDialog.showModal());
document.querySelector('#close-reference').addEventListener('click', () => referenceDialog.close());

function syncLensButtons(mode) {
  lensButtons.forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.lens === mode));
  });
}
syncLensButtons(initialLens);
lensButtons.forEach((button) => {
  button.addEventListener('click', () => {
    hero.setLayerLens(button.dataset.lens);
    syncLensButtons(button.dataset.lens);
    renderFrame();
  });
});

cameraPicker.value = CAMERA_VIEWS[requestedView] ? requestedView : 'reference';
cameraPicker.addEventListener('change', () => {
  tourActive = false;
  syncTourButton();
  setCameraView(cameraPicker.value);
  renderFrame();
});

function syncGateButton() {
  gateButton.setAttribute('aria-pressed', String(gatesOpen));
  gateButton.textContent = gatesOpen ? 'Close gates' : 'Open gates';
}
syncGateButton();
gateButton.addEventListener('click', () => {
  gatesOpen = !gatesOpen;
  hero.setGateOpen(gatesOpen ? 1 : 0);
  syncGateButton();
  renderFrame();
});

function syncTourButton() {
  tourButton.setAttribute('aria-pressed', String(tourActive));
  tourButton.textContent = tourActive ? 'Pause tour' : 'Start tour';
}
syncTourButton();
tourButton.addEventListener('click', () => {
  tourActive = !tourActive;
  syncTourButton();
  requestRenderLoop();
});

function syncMotionButton() {
  motionButton.setAttribute('aria-pressed', String(autoDrift));
  motionButton.textContent = autoDrift ? 'Pause turntable' : 'Start turntable';
}
syncMotionButton();
motionButton.addEventListener('click', () => {
  autoDrift = !autoDrift;
  hero.setTurntable(autoDrift);
  syncMotionButton();
  requestRenderLoop();
});
document.querySelector('#reset-view').addEventListener('click', () => {
  autoDrift = false;
  tourActive = false;
  hero.setTurntable(false);
  hero.setLayerLens('full');
  hero.setGateOpen(0);
  gatesOpen = false;
  syncMotionButton();
  syncTourButton();
  syncGateButton();
  syncLensButtons('full');
  cameraPicker.value = 'reference';
  setReferenceView();
  renderFrame();
});

const TOUR_SEQUENCE = ['reference', 'axis', 'side', 'mountain', 'hierarchy', 'reference'];
function updateTour(time) {
  const segmentDuration = 4.8;
  const phase = (time / segmentDuration) % (TOUR_SEQUENCE.length - 1);
  const index = Math.floor(phase);
  const blend = THREE.MathUtils.smoothstep(phase - index, 0, 1);
  const from = CAMERA_VIEWS[TOUR_SEQUENCE[index]];
  const to = CAMERA_VIEWS[TOUR_SEQUENCE[index + 1]];
  camera.position.lerpVectors(
    new THREE.Vector3().fromArray(from.position),
    new THREE.Vector3().fromArray(to.position),
    blend,
  );
  controls.target.lerpVectors(
    new THREE.Vector3().fromArray(from.target),
    new THREE.Vector3().fromArray(to.target),
    blend,
  );
}

const clock = new THREE.Clock();
let renderedFrames = 0;
let animationFrameId = null;
let loadingRemovalTimer = null;
function requestRenderLoop() {
  if (animationFrameId === null) {
    animationFrameId = requestAnimationFrame(render);
  }
}
function render() {
  animationFrameId = null;
  const delta = Math.min(clock.getDelta(), 0.05);
  elapsed = captureMode ? canonicalElapsed : elapsed + delta;
  if (tourActive) updateTour(elapsed);
  const controlsChanged = controls.update();
  hero.update(elapsed);
  renderFrame();
  renderedFrames += 1;
  if (renderedFrames === 4) {
    loadingStatus.textContent = 'Seoul palace scene ready';
    document.body.classList.add('ready');
    window.__SEOUL_READY__ = true;
    loadingRemovalTimer = window.setTimeout(() => {
      loadingStatus.hidden = true;
    }, captureMode ? 0 : 450);
  }
  if (
    renderedFrames < 4
    || (!captureMode && (autoDrift || tourActive || controlsChanged))
  ) {
    requestRenderLoop();
  }
}
controls.addEventListener('change', requestRenderLoop);
requestRenderLoop();

function handleResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderFrame();
}
window.addEventListener('resize', handleResize);

let disposed = false;
function disposeScene(event) {
  if (disposed || event.persisted) return;
  disposed = true;
  if (animationFrameId !== null) cancelAnimationFrame(animationFrameId);
  if (loadingRemovalTimer !== null) clearTimeout(loadingRemovalTimer);
  window.removeEventListener('resize', handleResize);
  window.removeEventListener('pagehide', disposeScene);
  controls.removeEventListener('change', requestRenderLoop);
  controls.dispose();
  scene.remove(hero.root);
  hero.dispose();
  renderer.dispose();
}
window.addEventListener('pagehide', disposeScene);
