import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import {
  createRepolisHero,
  REPOLIS_STAGES,
  REPOLIS_VARIANTS,
} from './repolis-output/createRepolisHero.js';

const query = new URLSearchParams(window.location.search);
if (query.get('ui') === '0') document.documentElement.dataset.ui = 'hidden';
const captureMode = query.get('capture') === '1';
const canonicalElapsed = Number.parseFloat(query.get('time') ?? '1.25');
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
const initialVariant = Number.parseInt(query.get('variant') ?? '0', 10);
const stage = REPOLIS_STAGES.includes(query.get('stage'))
  ? query.get('stage')
  : 'full';
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
sceneContainer.append(renderer.domElement);

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x07141E, 0.018);
const camera = new THREE.PerspectiveCamera(
  36,
  window.innerWidth / window.innerHeight,
  0.1,
  160,
);
camera.position.set(15.5, 8.5, 20.5);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 10;
controls.maxDistance = 34;
controls.maxPolarAngle = Math.PI * 0.55;
controls.target.set(0, 5.4, 0);
controls.update();

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(
  new THREE.Vector2(window.innerWidth, window.innerHeight),
  0.5,
  0.36,
  0.88,
);
composer.addPass(bloom);
composer.addPass(new OutputPass());

function setupEnvironment() {
  scene.add(new THREE.HemisphereLight(0x7FB9D6, 0x2B2118, 1.45));
  const key = new THREE.DirectionalLight(0xFFE2B6, 3.3);
  key.position.set(-9, 16, 11);
  key.castShadow = true;
  key.shadow.mapSize.set(4096, 4096);
  key.shadow.camera.left = -14;
  key.shadow.camera.right = 14;
  key.shadow.camera.top = 16;
  key.shadow.camera.bottom = -8;
  key.shadow.camera.near = 1;
  key.shadow.camera.far = 42;
  key.shadow.bias = -0.0003;
  key.shadow.normalBias = 0.025;
  scene.add(key);
  const coolRim = new THREE.DirectionalLight(0x49D9F0, 2.25);
  coolRim.position.set(11, 9, -12);
  scene.add(coolRim);
  const warmFill = new THREE.DirectionalLight(0xE99A45, 1.15);
  warmFill.position.set(4, 4, 10);
  scene.add(warmFill);
  const frontFill = new THREE.DirectionalLight(0xD8AA7A, 1.35);
  frontFill.position.set(0, 8, 16);
  scene.add(frontFill);

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(70, 70),
    new THREE.ShadowMaterial({
      color: 0x000000,
      opacity: 0.24,
      transparent: true,
    }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.58;
  floor.receiveShadow = true;
  scene.add(floor);

  const starCount = 850;
  const positions = new Float32Array(starCount * 3);
  let state = 20260711;
  const random = () => {
    state += 0x6D2B79F5;
    let value = state;
    value = Math.imul(value ^ value >>> 15, value | 1);
    value ^= value + Math.imul(value ^ value >>> 7, value | 61);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
  for (let index = 0; index < starCount; index += 1) {
    positions[index * 3] = (random() - 0.5) * 62;
    positions[index * 3 + 1] = random() * 29 + 2;
    positions[index * 3 + 2] = -12 - random() * 28;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  scene.add(new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      color: 0x9BD8E6,
      size: 0.045,
      transparent: true,
      opacity: 0.72,
    }),
  ));
}

setupEnvironment();

let activeVariant = Number.isFinite(initialVariant)
  ? ((initialVariant % REPOLIS_VARIANTS.length) + REPOLIS_VARIANTS.length) % REPOLIS_VARIANTS.length
  : 0;
let hero = null;
let autoRotate = !captureMode && query.get('motion') !== '0';
let elapsed = 0;
const clock = new THREE.Clock();
const motionButton = document.querySelector('#toggle-motion');
const generationLabel = document.querySelector('#generation-time');
const variantName = document.querySelector('#variant-name');
const variantIndex = document.querySelector('#variant-index');

function updateLabels() {
  variantName.textContent = REPOLIS_VARIANTS[activeVariant].label;
  variantIndex.textContent = `${String(activeVariant + 1).padStart(2, '0')} / ${String(REPOLIS_VARIANTS.length).padStart(2, '0')}`;
}

function syncMotionButton() {
  motionButton.setAttribute('aria-pressed', String(autoRotate));
  motionButton.textContent = autoRotate ? 'Pause rotation' : 'Auto rotate';
}

function rebuildHero() {
  if (hero) {
    scene.remove(hero.root);
    hero.dispose();
  }
  hero = createRepolisHero({
    seed: 20260711,
    variant: activeVariant,
    stage,
  });
  hero.root.scale.setScalar(0.96);
  hero.root.rotation.y = -0.14;
  scene.add(hero.root);
  generationLabel.textContent = captureMode
    ? `~100 ms · ${hero.stats.leafInstances.toLocaleString()} leaves`
    : `${hero.stats.generationMs.toFixed(0)} ms · ${hero.stats.leafInstances.toLocaleString()} leaves`;
  updateLabels();
  window.__REPOLIS_HERO__ = hero;
}

rebuildHero();
syncMotionButton();

motionButton.addEventListener('click', () => {
  autoRotate = !autoRotate;
  syncMotionButton();
});

document.querySelector('#reset-view').addEventListener('click', () => {
  camera.position.set(15.5, 8.5, 20.5);
  controls.target.set(0, 5.4, 0);
  controls.update();
  hero.root.rotation.y = -0.14;
});

document.querySelector('#next-variant').addEventListener('click', () => {
  activeVariant = (activeVariant + 1) % REPOLIS_VARIANTS.length;
  rebuildHero();
});

const referenceDialog = document.querySelector('#reference-dialog');
document.querySelector('#open-reference').addEventListener('click', () => referenceDialog.showModal());
document.querySelector('#close-reference').addEventListener('click', () => referenceDialog.close());

window.__setHeroAngle = (angle) => {
  autoRotate = false;
  hero.root.rotation.y = angle;
  controls.update();
  composer.render();
};
window.__setHeroVariant = (variant) => {
  activeVariant = ((variant % REPOLIS_VARIANTS.length) + REPOLIS_VARIANTS.length) % REPOLIS_VARIANTS.length;
  rebuildHero();
  composer.render();
};

let renderedFrames = 0;
function render() {
  if (!captureMode || renderedFrames < 4) requestAnimationFrame(render);
  const delta = captureMode ? 0 : Math.min(clock.getDelta(), 0.05);
  elapsed = captureMode ? canonicalElapsed : elapsed + delta;
  controls.update();
  hero.update(elapsed);
  if (autoRotate) hero.root.rotation.y += delta * 0.09;
  composer.render();
  renderedFrames += 1;
  if (renderedFrames === 4) {
    document.body.classList.add('ready');
    window.__REPOLIS_READY__ = true;
    window.__REPOLIS_CAPTURE__ = captureMode
      ? { frozen: true, canonicalElapsed }
      : { frozen: false };
  }
}
render();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
  composer.setSize(window.innerWidth, window.innerHeight);
});
