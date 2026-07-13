import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import {
  BRICK_BASE_CONFIG,
  BRICK_STAGES,
  BRICK_VARIANTS,
  createBrickOffroad,
} from './brick-output/createBrickOffroad.js';

const query = new URLSearchParams(window.location.search);
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
if (query.get('ui') === '0') document.documentElement.dataset.ui = 'hidden';
const requestedStage = query.get('stage');
const stage = BRICK_STAGES.includes(requestedStage) ? requestedStage : 'full';
const requestedVariantValue = query.get('variant') ?? '0';
const requestedVariant = Number.parseInt(requestedVariantValue, 10);
let activeVariant = requestedVariantValue === 'base'
  ? 'base'
  : Number.isFinite(requestedVariant)
    ? ((requestedVariant % BRICK_VARIANTS.length) + BRICK_VARIANTS.length)
      % BRICK_VARIANTS.length
    : 0;
const captureMode = query.get('capture') === '1';
if (captureMode) document.documentElement.dataset.capture = 'true';
let canonicalElapsed = Number.parseFloat(query.get('time') ?? '1.25');
if (!Number.isFinite(canonicalElapsed)) canonicalElapsed = 1.25;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let autoRotate = query.get('motion') !== '0' && !reducedMotion && !captureMode;
let elapsed = captureMode ? canonicalElapsed : 0;

const sceneContainer = document.querySelector('#scene');
const renderer = new THREE.WebGLRenderer({
  antialias: true,
  alpha: true,
  preserveDrawingBuffer: true,
  powerPreference: 'high-performance',
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.info.autoReset = false;
sceneContainer.append(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x171914);
scene.fog = new THREE.Fog(0x171914, 16, 34);
const camera = new THREE.PerspectiveCamera(
  34,
  window.innerWidth / window.innerHeight,
  0.1,
  80,
);

function setReferenceView() {
  camera.position.set(-7.6, 4.85, 8.45);
  controls.target.set(0, 1.85, 0);
  controls.update();
}

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.065;
controls.minDistance = 7;
controls.maxDistance = 19;
controls.maxPolarAngle = Math.PI * 0.56;
setReferenceView();

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new OutputPass());

function renderFrame() {
  renderer.info.reset();
  composer.render();
}

function setupStudio() {
  scene.add(new THREE.HemisphereLight(0xd8dfd0, 0x3d352a, 1.5));

  const key = new THREE.DirectionalLight(0xfff8ed, 3.25);
  key.position.set(-7, 11, 8);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left = -8;
  key.shadow.camera.right = 8;
  key.shadow.camera.top = 8;
  key.shadow.camera.bottom = -5;
  key.shadow.camera.near = 1;
  key.shadow.camera.far = 28;
  key.shadow.bias = -0.00025;
  key.shadow.normalBias = 0.025;
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xc4d3dc, 1.6);
  fill.position.set(6, 5, 8);
  scene.add(fill);

  const rim = new THREE.DirectionalLight(0xd6e0c0, 1.2);
  rim.position.set(5, 7, -8);
  scene.add(rim);

  const floor = new THREE.Mesh(
    new THREE.CircleGeometry(16, 64),
    new THREE.MeshStandardMaterial({
      color: 0x30322c,
      roughness: 0.88,
      metalness: 0,
    }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = 0;
  floor.receiveShadow = true;
  scene.add(floor);

  const backdrop = new THREE.Mesh(
    new THREE.PlaneGeometry(34, 18),
    new THREE.MeshBasicMaterial({ color: 0x1e211b }),
  );
  backdrop.position.set(0, 7, -10);
  scene.add(backdrop);
}

setupStudio();

const generationLabel = document.querySelector('#generation-time');
const geometryLabel = document.querySelector('#geometry-stats');
const variantName = document.querySelector('#variant-name');
const variantIndex = document.querySelector('#variant-index');
const motionButton = document.querySelector('#toggle-motion');
let explorer = null;

function updateLabels() {
  if (activeVariant === 'base') {
    variantName.textContent = BRICK_BASE_CONFIG.label;
    variantIndex.textContent = 'BASE SPEC';
    return;
  }
  variantName.textContent = BRICK_VARIANTS[activeVariant].label;
  variantIndex.textContent = `${String(activeVariant + 1).padStart(2, '0')} / ${String(BRICK_VARIANTS.length).padStart(2, '0')}`;
}

function syncMotionButton() {
  motionButton.setAttribute('aria-pressed', String(autoRotate));
  motionButton.textContent = autoRotate ? 'Pause rotation' : 'Auto rotate';
}

function rebuildExplorer() {
  if (explorer) {
    scene.remove(explorer.root);
    explorer.dispose();
  }
  explorer = createBrickOffroad({
    seed: 20260712,
    variant: activeVariant,
    stage,
  });
  explorer.root.rotation.y = -0.04;
  scene.add(explorer.root);
  generationLabel.textContent = captureMode
    ? 'Canonical capture · 1.25 s'
    : `${explorer.stats.generationMs.toFixed(0)} ms generation`;
  geometryLabel.textContent = `${explorer.stats.triangles.toLocaleString()} triangles · ${explorer.stats.wheels} wheels`;
  updateLabels();
  window.__BRICK_HERO__ = explorer;
  window.__getBrickRenderInfo = () => ({
    calls: renderer.info.render.calls,
    triangles: renderer.info.render.triangles,
    lines: renderer.info.render.lines,
    points: renderer.info.render.points,
    frame: renderer.info.render.frame,
    memory: { ...renderer.info.memory },
  });
  window.__renderBrickFrame = renderFrame;
}

rebuildExplorer();
syncMotionButton();

motionButton.addEventListener('click', () => {
  autoRotate = !autoRotate;
  syncMotionButton();
});

document.querySelector('#reset-view').addEventListener('click', () => {
  autoRotate = false;
  syncMotionButton();
  explorer.root.rotation.y = -0.04;
  setReferenceView();
});

document.querySelector('#next-variant').addEventListener('click', () => {
  activeVariant = activeVariant === 'base'
    ? 0
    : (activeVariant + 1) % BRICK_VARIANTS.length;
  rebuildExplorer();
});

const referenceDialog = document.querySelector('#reference-dialog');
document.querySelector('#open-reference').addEventListener('click', () => referenceDialog.showModal());
document.querySelector('#close-reference').addEventListener('click', () => referenceDialog.close());

window.__setBrickAngle = (angle) => {
  autoRotate = false;
  explorer.root.rotation.y = angle;
  controls.update();
  renderFrame();
};
window.__setBrickVariant = (variant) => {
  activeVariant = ((variant % BRICK_VARIANTS.length) + BRICK_VARIANTS.length)
    % BRICK_VARIANTS.length;
  rebuildExplorer();
  renderFrame();
};
window.__setBrickReferenceView = () => {
  explorer.root.rotation.y = -0.04;
  setReferenceView();
  renderFrame();
};
window.__setBrickCaptureTime = (value = 1.25) => {
  canonicalElapsed = value;
  elapsed = value;
  explorer.update(value);
  controls.update();
  renderFrame();
};
window.__setDoorPose = (angle = 0) => {
  const front = explorer.runtime.nodes['left-door-pivot'];
  const rear = explorer.runtime.nodes['left-rear-door-pivot'];
  front.rotation.y = -angle;
  rear.rotation.y = -angle;
  front.updateMatrixWorld(true);
  rear.updateMatrixWorld(true);
  renderFrame();
};

const clock = new THREE.Clock();
let renderedFrames = 0;
function render() {
  const delta = Math.min(clock.getDelta(), 0.05);
  elapsed = captureMode ? canonicalElapsed : elapsed + delta;
  controls.update();
  explorer.update(elapsed);
  if (autoRotate) explorer.root.rotation.y += delta * 0.08;
  renderFrame();
  renderedFrames += 1;
  if (renderedFrames === 4) {
    document.body.classList.add('ready');
    window.__BRICK_READY__ = true;
  }
  if (!captureMode || renderedFrames < 4) requestAnimationFrame(render);
}
render();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
});
