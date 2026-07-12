import { createHash } from 'node:crypto';
import {
  access,
  mkdir,
  open,
  readFile,
  rm,
  stat,
  writeFile,
} from 'node:fs/promises';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';
import { brickSourceFingerprint } from '../vite.config.js';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const heroDir = path.resolve(scriptDir, '..');
const repoRoot = path.resolve(heroDir, '..', '..');
const assetsDir = path.join(repoRoot, 'assets');
const evidenceDir = path.join(heroDir, 'evidence');
const framesDir = path.join(heroDir, `.capture-frames-${process.pid}`);
const captureLockPath = path.join(heroDir, '.capture.lock');
const fingerprintPath = path.join(heroDir, '__brick-source-fingerprint.txt');
const gifFrameCount = 24;
const gifFps = 6;
const canonicalElapsed = 1.25;
const stages = [
  'blockout',
  'structural-pass',
  'form-refinement',
  'material-pass',
  'surface-pass',
];

async function exists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (await exists(candidate)) return candidate;
  }
  throw new Error('Set CHROME_BIN to an installed Chrome or Chromium executable.');
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? heroDir,
    encoding: 'utf8',
    stdio: options.quiet ? 'pipe' : 'inherit',
  });
  if (result.status !== 0) {
    throw new Error(
      `${command} ${args.join(' ')} failed: ${result.stderr || result.stdout || result.status}`,
    );
  }
}

export async function allocateEphemeralPort(host = '127.0.0.1') {
  const reservation = createServer();
  await new Promise((resolve, reject) => {
    reservation.once('error', reject);
    reservation.listen(0, host, resolve);
  });
  const address = reservation.address();
  const port = typeof address === 'object' && address ? address.port : null;
  await new Promise((resolve, reject) => reservation.close((error) => (
    error ? reject(error) : resolve()
  )));
  if (!Number.isInteger(port)) throw new Error('Could not allocate an ephemeral capture port.');
  return port;
}

export async function waitForServer(url, server, serverOutput = () => '') {
  let settled = false;
  let onExit;
  const exited = new Promise((_, reject) => {
    onExit = (code, signal) => {
      reject(new Error(
        `Vite exited before capture readiness (code=${code}, signal=${signal}): ${serverOutput()}`,
      ));
    };
    server.once('exit', onExit);
  });
  const ready = (async () => {
    for (let attempt = 0; attempt < 600 && !settled; attempt += 1) {
      try {
        const response = await fetch(url, { cache: 'no-store' });
        if (response.ok) return;
      } catch {
        // Vite is still starting.
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    if (settled) return;
    throw new Error(`Timed out waiting for ${url}`);
  })();
  try {
    await Promise.race([ready, exited]);
  } finally {
    settled = true;
    server.removeListener('exit', onExit);
  }
}

export async function verifySourceFingerprint(baseUrl, expected) {
  const response = await fetch(
    `${baseUrl}/threejs-sculpt-dna/brick/__brick-source-fingerprint.txt`,
    { cache: 'no-store' },
  );
  if (!response.ok) {
    throw new Error(`Capture source fingerprint endpoint failed (${response.status}).`);
  }
  const actual = (await response.text()).trim();
  if (actual !== expected) {
    throw new Error(
      `Capture source fingerprint mismatch: expected ${expected}, served ${actual || '<empty>'}.`,
    );
  }
  return actual;
}

async function waitForHero(page) {
  await page.waitForFunction(() => window.__BRICK_READY__ === true, {
    timeout: 120_000,
  });
}

async function readRuntimeStats(page) {
  return page.evaluate(() => {
    const render = window.__getBrickRenderInfo();
    return {
      ...window.__BRICK_HERO__.stats,
      renderCalls: render.calls,
      renderedTriangles: render.triangles,
    };
  });
}

async function sha256(filePath) {
  return createHash('sha256').update(await readFile(filePath)).digest('hex');
}

async function invalidateStaleShowcaseReview(referencePath, renderPath, comparisonPath) {
  const reviewPath = path.join(repoRoot, 'examples', 'showcase', 'showcase-review.json');
  const review = JSON.parse(await readFile(reviewPath, 'utf8'));
  const brick = review.families?.find((family) => family.id === 'brick-offroad');
  if (!brick) throw new Error('showcase-review.json is missing the Brick family.');
  const hashes = {
    referenceSha256: await sha256(referencePath),
    renderSha256: await sha256(renderPath),
    comparisonSha256: await sha256(comparisonPath),
  };
  const stale = Object.entries(hashes).some(([field, value]) => brick[field] !== value);
  Object.assign(brick, hashes, {
    referenceBinding: 'local-sha256',
    renderBinding: 'local-sha256',
    comparisonBinding: 'local-sha256',
    comparison: path.relative(repoRoot, comparisonPath),
  });
  if (stale) {
    delete brick.scores;
    delete brick.reviewId;
    delete brick.reviewedAt;
    brick.reviewStatus = 'stale';
    brick.decision = 'pending-fresh-visual-review';
    brick.passGateStatus = 'pending-fresh-showcase-review';
    brick.staleReason = 'Capture pixels changed; inspect the new comparison before restoring scores.';
  }
  await writeFile(reviewPath, `${JSON.stringify(review, null, 2)}\n`, 'utf8');
}

function comparison(renderPath, outputPath) {
  run(
    'python3',
    [
      path.join(repoRoot, 'scripts', 'make_visual_comparison_sheet.py'),
      '--reference',
      path.join(assetsDir, 'brick-offroad-reference.jpeg'),
      '--render',
      renderPath,
      '--out',
      outputPath,
      '--json',
    ],
    { cwd: repoRoot, quiet: true },
  );
}

function toWebp(source, output, quality = 84) {
  run('cwebp', ['-quiet', '-q', String(quality), source, '-o', output], {
    quiet: true,
  });
}

async function captureEvidence(page, name, url) {
  await page.goto(url, { waitUntil: 'networkidle0' });
  await waitForHero(page);
  await page.evaluate(() => window.__setBrickReferenceView());
  await page.evaluate((value) => window.__setBrickCaptureTime(value), canonicalElapsed);
  const renderPng = path.join(framesDir, `${name}.png`);
  await page.screenshot({ path: renderPng });
  toWebp(renderPng, path.join(evidenceDir, `${name}.webp`), 85);
  const comparisonPng = path.join(framesDir, `${name}-comparison.png`);
  comparison(renderPng, comparisonPng);
  toWebp(
    comparisonPng,
    path.join(evidenceDir, `${name}-comparison.webp`),
    82,
  );
}

function processIsRunning(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code !== 'ESRCH';
  }
}

async function acquireCaptureLock() {
  try {
    const handle = await open(captureLockPath, 'wx');
    try {
      await handle.writeFile(`${JSON.stringify({
        pid: process.pid,
        startedAt: new Date().toISOString(),
      })}\n`);
      const lockStat = await handle.stat();
      return {
        handle,
        device: lockStat.dev,
        inode: lockStat.ino,
      };
    } catch (error) {
      try {
        await handle.close();
      } finally {
        await rm(captureLockPath, { force: true });
      }
      throw error;
    }
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
    let owner;
    try {
      owner = JSON.parse(await readFile(captureLockPath, 'utf8'));
    } catch {
      throw new Error(
        `Capture lock ${captureLockPath} is malformed; remove it only after verifying no capture is running.`,
      );
    }
    if (Number.isInteger(owner?.pid) && processIsRunning(owner.pid)) {
      throw new Error(
        `Another capture (PID ${owner.pid}) owns ${captureLockPath}.`,
      );
    }
    throw new Error(
      `Stale capture lock from PID ${owner?.pid ?? 'unknown'} at ${captureLockPath}; `
        + 'verify no capture is running, then remove the lock explicitly.',
    );
  }
}

async function releaseCaptureLock(lock) {
  try {
    await lock.handle.close();
  } finally {
    try {
      const current = await stat(captureLockPath);
      if (current.dev === lock.device && current.ino === lock.inode) {
        await rm(captureLockPath, { force: true });
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
}

async function stopServer(server) {
  if (!server || server.exitCode !== null || server.signalCode !== null) return;
  const closed = new Promise((resolve) => server.once('close', resolve));
  server.kill('SIGTERM');
  let timeoutId;
  const stopped = await Promise.race([
    closed.then(() => true),
    new Promise((resolve) => {
      timeoutId = setTimeout(() => resolve(false), 5000);
    }),
  ]);
  clearTimeout(timeoutId);
  if (
    !stopped
    && server.exitCode === null
    && server.signalCode === null
  ) {
    server.kill('SIGKILL');
    await closed;
  }
}

async function main() {
  const chromePath = await findChrome();
  const ffmpeg = process.env.FFMPEG_BIN ?? 'ffmpeg';
  run(ffmpeg, ['-version'], { quiet: true });
  run('cwebp', ['-version'], { quiet: true });
  run('python3', ['--version'], { quiet: true });
  const captureLock = await acquireCaptureLock();
  let server;
  let browser;
  try {
    await rm(framesDir, { recursive: true, force: true });
    await mkdir(framesDir, { recursive: true });
    await mkdir(evidenceDir, { recursive: true });
    const port = await allocateEphemeralPort();
    const baseUrl = `http://127.0.0.1:${port}`;
    const expectedFingerprint = await brickSourceFingerprint();
    await writeFile(fingerprintPath, `${expectedFingerprint}\n`, 'utf8');
    let serverOutput = '';
    server = spawn(
      process.execPath,
      [
        path.join(heroDir, 'node_modules', 'vite', 'bin', 'vite.js'),
        '--host',
        '127.0.0.1',
        '--port',
        String(port),
        '--strictPort',
      ],
      {
        cwd: heroDir,
        stdio: ['ignore', 'pipe', 'pipe'],
        detached: false,
      },
    );
    for (const stream of [server.stdout, server.stderr]) {
      stream.on('data', (chunk) => {
        serverOutput = `${serverOutput}${chunk}`.slice(-8000);
      });
    }
    await waitForServer(baseUrl, server, () => serverOutput);
    const servedFingerprint = await verifySourceFingerprint(baseUrl, expectedFingerprint);
    const gitProbe = await fetch(`${baseUrl}/.git/HEAD`);
    const gitProbeBody = await gitProbe.text();
    if (/^ref: refs\//m.test(gitProbeBody) || /^[0-9a-f]{40}$/m.test(gitProbeBody)) {
      throw new Error('Local server exposed .git metadata.');
    }

    browser = await puppeteer.launch({
      executablePath: chromePath,
      headless: true,
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    });
    const page = await browser.newPage();
    await page.evaluateOnNewDocument(() => {
      window.__BRICK_WEBGL_ALLOCATIONS__ = { buffers: 0, textures: 0 };
      for (const contextType of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
        if (!contextType) continue;
        for (const [method, key] of [
          ['createBuffer', 'buffers'],
          ['createTexture', 'textures'],
        ]) {
          const original = contextType.prototype[method];
          if (typeof original !== 'function' || original.__brickAllocationWrapped) continue;
          const wrapped = function wrappedWebGLAllocation(...args) {
            window.__BRICK_WEBGL_ALLOCATIONS__[key] += 1;
            return original.apply(this, args);
          };
          wrapped.__brickAllocationWrapped = true;
          contextType.prototype[method] = wrapped;
        }
      }
    });
    await page.setViewport({ width: 1200, height: 675, deviceScaleFactor: 1 });

    await page.goto(
      `${baseUrl}/?stage=full&variant=base&motion=0&capture=1&time=${canonicalElapsed}`,
      {
      waitUntil: 'networkidle0',
      },
    );
    await waitForHero(page);
    await page.evaluate(() => window.__setBrickReferenceView());
    await page.evaluate((value) => window.__setBrickCaptureTime(value), canonicalElapsed);
    const stats = await readRuntimeStats(page);
    const baseConfiguration = await page.evaluate(() => window.__BRICK_HERO__.variant);
    const serializableRoot = await page.evaluate(() => {
      const hero = window.__BRICK_HERO__;
      const json = hero.root.toJSON();
      return {
        rootName: json.object.name,
        runtimeKeys: Object.keys(hero.runtime),
        userData: hero.root.userData,
      };
    });
    const doorArticulation = await page.evaluate(() => {
      const hero = window.__BRICK_HERO__;
      const contracts = {
        'left-door-pivot': [
          'left-door-panel',
          'front-side-window-left',
          'front-door-handle-left',
          'side-mirror-left',
          'mirror-arm-left',
          'front-left-door-fasteners',
          'left-door-hinge',
          'door-hinge-left-front--0.38',
          'door-hinge-left-front-0.38',
        ],
        'left-rear-door-pivot': [
          'left-rear-door-panel',
          'rear-side-window-left',
          'rear-door-handle-left',
          'rear-left-door-fasteners',
          'left-rear-door-hinge',
          'door-hinge-left-rear--0.38',
          'door-hinge-left-rear-0.38',
        ],
        'right-door-pivot': [
          'right-door-panel',
          'front-side-window-right',
          'front-door-handle-right',
          'side-mirror-right',
          'mirror-arm-right',
          'front-right-door-fasteners',
          'right-door-hinge',
          'door-hinge-right-front--0.38',
          'door-hinge-right-front-0.38',
        ],
        'right-rear-door-pivot': [
          'right-rear-door-panel',
          'rear-side-window-right',
          'rear-door-handle-right',
          'rear-right-door-fasteners',
          'right-rear-door-hinge',
          'door-hinge-right-rear--0.38',
          'door-hinge-right-rear-0.38',
        ],
      };
      return Object.entries(contracts).map(([pivotId, childIds]) => {
        const pivot = hero.runtime.nodes[pivotId];
        const target = pivot.getObjectByName(childIds[1]);
        const fastenerId = childIds.find((id) => id.includes('fasteners'));
        const fasteners = hero.runtime.meshes[fastenerId];
        const fixedFasteners = hero.runtime.meshes['fixed-panel-fasteners'];
        const instanceWorldPositions = (mesh) => {
          const local = mesh.matrixWorld.clone();
          const world = mesh.matrixWorld.clone();
          const positions = [];
          mesh.updateMatrixWorld(true);
          for (let index = 0; index < mesh.count; index += 1) {
            mesh.getMatrixAt(index, local);
            world.multiplyMatrices(mesh.matrixWorld, local);
            positions.push([world.elements[12], world.elements[13], world.elements[14]]);
          }
          return positions;
        };
        const before = target.getWorldPosition(target.position.clone()).toArray();
        const fastenerWorldBefore = instanceWorldPositions(fasteners);
        const fixedWorldBefore = instanceWorldPositions(fixedFasteners);
        pivot.rotation.y = pivotId.startsWith('left') ? -0.65 : 0.65;
        pivot.updateMatrixWorld(true);
        const after = target.getWorldPosition(target.position.clone()).toArray();
        const fastenerWorldAfter = instanceWorldPositions(fasteners);
        const fixedWorldAfter = instanceWorldPositions(fixedFasteners);
        const positionsDiffer = (first, second) => first.some(
          (position, positionIndex) => position.some(
            (value, axis) => Math.abs(value - second[positionIndex][axis]) > 1e-4,
          ),
        );
        const result = {
          pivotId,
          childIds,
          allParented: childIds.every((id) => Boolean(pivot.getObjectByName(id))),
          fastenerParentedDirectly: fasteners.parent === pivot,
          childMoved: before.some(
            (value, index) => Math.abs(value - after[index]) > 1e-4,
          ),
          fastenerInstancesMoved: positionsDiffer(
            fastenerWorldBefore,
            fastenerWorldAfter,
          ),
          fixedFastenersStayed: !positionsDiffer(fixedWorldBefore, fixedWorldAfter),
          fastenerWorldBefore,
          fastenerWorldAfter,
        };
        pivot.rotation.y = 0;
        pivot.updateMatrixWorld(true);
        return result;
      });
    });
    const recoveryArticulation = await page.evaluate(() => {
      const hero = window.__BRICK_HERO__;
      const pivot = hero.runtime.nodes['front-bumper-pivot'];
      const hardwareIds = [
        'front-winch',
        'winch-drum',
        'recovery-hook--1',
        'recovery-hook-1',
      ];
      const positions = () => Object.fromEntries(hardwareIds.map((id) => {
        const elements = hero.runtime.meshes[id].matrixWorld.elements;
        return [id, [elements[12], elements[13], elements[14]]];
      }));
      hero.root.updateMatrixWorld(true);
      const before = positions();
      pivot.rotation.z = 0.35;
      hero.root.updateMatrixWorld(true);
      const after = positions();
      const moved = (id) => before[id].some(
        (value, index) => Math.abs(value - after[id][index]) > 1e-4,
      );
      const result = {
        pivotId: pivot.name,
        hardwareIds,
        allParented: hardwareIds.every((id) => hero.runtime.meshes[id].parent === pivot),
        allMoved: hardwareIds.every(moved),
        before,
        after,
      };
      pivot.rotation.z = 0;
      hero.root.updateMatrixWorld(true);
      return result;
    });
    await page.goto(
      `${baseUrl}/?stage=full&variant=base&motion=0&ui=0&capture=1&time=${canonicalElapsed}`,
      { waitUntil: 'networkidle0' },
    );
    await waitForHero(page);
    await page.evaluate(() => window.__setBrickReferenceView());
    await page.evaluate((value) => window.__setBrickCaptureTime(value), canonicalElapsed);
    const deterministicA = path.join(framesDir, 'deterministic-a.png');
    const deterministicB = path.join(framesDir, 'deterministic-b.png');
    await page.screenshot({ path: deterministicA });
    await new Promise((resolve) => setTimeout(resolve, 120));
    await page.evaluate((value) => window.__setBrickCaptureTime(value), canonicalElapsed);
    await page.screenshot({ path: deterministicB });
    const deterministicHashA = await sha256(deterministicA);
    const deterministicHashB = await sha256(deterministicB);
    if (deterministicHashA !== deterministicHashB) {
      throw new Error('Canonical capture frames were not byte-identical.');
    }
    for (let index = 0; index < gifFrameCount; index += 1) {
      const angle = -0.04 + index * Math.PI * 2 / gifFrameCount;
      await page.evaluate((value) => window.__setBrickCaptureTime(value), canonicalElapsed);
      await page.evaluate((value) => window.__setBrickAngle(value), angle);
      await new Promise((resolve) => setTimeout(resolve, 25));
      await page.screenshot({
        path: path.join(framesDir, `frame-${String(index).padStart(2, '0')}.png`),
      });
    }
    run(
      ffmpeg,
      [
        '-hide_banner',
        '-loglevel',
        'error',
        '-y',
        '-framerate',
        String(gifFps),
        '-i',
        path.join(framesDir, 'frame-%02d.png'),
        '-filter_complex',
        `fps=${gifFps},scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3`,
        '-loop',
        '0',
        path.join(assetsDir, 'brick-offroad-hero.gif'),
      ],
      { quiet: true },
    );
    await page.evaluate(() => {
      window.__setBrickAngle(-0.04);
      window.__setDoorPose(0.72);
    });
    const doorArticulationPng = path.join(framesDir, 'door-articulation.png');
    await page.screenshot({ path: doorArticulationPng });
    toWebp(
      doorArticulationPng,
      path.join(evidenceDir, 'door-articulation.webp'),
      85,
    );
    await page.evaluate(() => window.__setDoorPose(0));

    for (const stage of stages) {
      await captureEvidence(
        page,
        stage,
        `${baseUrl}/?stage=${encodeURIComponent(stage)}&variant=base&motion=0&ui=0&capture=1&time=${canonicalElapsed}`,
      );
    }
    await captureEvidence(
      page,
      'final',
      `${baseUrl}/?stage=full&variant=base&motion=0&ui=0&capture=1&time=${canonicalElapsed}`,
    );
    run(
      ffmpeg,
      [
        '-hide_banner',
        '-loglevel',
        'error',
        '-y',
        '-i',
        path.join(evidenceDir, 'final.webp'),
        '-frames:v',
        '1',
        '-compression_level',
        '9',
        path.join(assetsDir, 'brick-offroad-hero.png'),
      ],
      { quiet: true },
    );
    const variantStats = [];
    for (let variant = 0; variant < 3; variant += 1) {
      await captureEvidence(
        page,
        `variant-${variant + 1}`,
        `${baseUrl}/?stage=full&variant=${variant}&motion=0&ui=0&capture=1&time=${canonicalElapsed}`,
      );
      variantStats.push(await page.evaluate(() => ({
        id: window.__BRICK_HERO__.variant.id,
        controls: window.__BRICK_HERO__.root.userData.variantProvenance.visualControls,
        stats: {
          ...window.__BRICK_HERO__.stats,
          renderCalls: window.__getBrickRenderInfo().calls,
          renderedTriangles: window.__getBrickRenderInfo().triangles,
        },
      })));
    }
    run(
      ffmpeg,
      [
        '-hide_banner',
        '-loglevel',
        'error',
        '-y',
        '-i',
        path.join(framesDir, 'variant-1.png'),
        '-i',
        path.join(framesDir, 'variant-2.png'),
        '-i',
        path.join(framesDir, 'variant-3.png'),
        '-filter_complex',
        '[0:v]crop=720:675:240:0,scale=400:375,pad=400:675:0:150:color=0x11130f[a];'
          + '[1:v]crop=720:675:240:0,scale=400:375,pad=400:675:0:150:color=0x11130f[b];'
          + '[2:v]crop=720:675:240:0,scale=400:375,pad=400:675:0:150:color=0x11130f[c];'
          + '[a][b][c]hstack=inputs=3[out]',
        '-map',
        '[out]',
        '-frames:v',
        '1',
        path.join(assetsDir, 'brick-offroad-sculpt-dna-result.png'),
      ],
      { quiet: true },
    );
    const showcaseComparisonPng = path.join(framesDir, 'showcase-comparison.png');
    comparison(
      path.join(assetsDir, 'brick-offroad-sculpt-dna-result.png'),
      showcaseComparisonPng,
    );
    const showcaseComparison = path.join(evidenceDir, 'showcase-comparison.webp');
    toWebp(showcaseComparisonPng, showcaseComparison, 82);
    await invalidateStaleShowcaseReview(
      path.join(assetsDir, 'brick-offroad-reference.jpeg'),
      path.join(assetsDir, 'brick-offroad-sculpt-dna-result.png'),
      showcaseComparison,
    );
    await page.goto(
      `${baseUrl}/?stage=full&variant=base&motion=0&ui=0&capture=1&time=${canonicalElapsed}`,
      { waitUntil: 'networkidle0' },
    );
    await waitForHero(page);
    const lifecycleCheck = await page.evaluate(() => {
      const hero = window.__BRICK_HERO__;
      const resources = hero.runtime.resources;
      const memoryBefore = window.__getBrickRenderInfo().memory;
      const allocationsBefore = { ...window.__BRICK_WEBGL_ALLOCATIONS__ };
      const counts = {
        geometries: resources.geometries.size,
        materials: resources.materials.size,
        textures: resources.textures.size,
        instancedMeshes: resources.instancedMeshes.size,
      };
      const disposed = {
        geometries: 0,
        materials: 0,
        textures: 0,
        instancedMeshes: 0,
      };
      for (const [key, items] of Object.entries(resources)) {
        for (const item of items) {
          item.addEventListener('dispose', () => {
            disposed[key] += 1;
          });
        }
      }
      hero.root.parent?.remove(hero.root);
      const removedFromScene = hero.root.parent === null;
      hero.dispose();
      window.__renderBrickFrame();
      const memoryDisposed = window.__getBrickRenderInfo().memory;
      const allocationsDisposed = { ...window.__BRICK_WEBGL_ALLOCATIONS__ };
      const postDisposeFrames = 6;
      for (let frame = 0; frame < postDisposeFrames; frame += 1) {
        window.__renderBrickFrame();
      }
      const memoryPostRender = window.__getBrickRenderInfo().memory;
      const allocationsPostRender = { ...window.__BRICK_WEBGL_ALLOCATIONS__ };
      const rendererMemoryDidNotRebound = (
        memoryPostRender.geometries <= memoryDisposed.geometries
        && memoryPostRender.textures <= memoryDisposed.textures
      );
      const webglAllocationsDidNotRebound = (
        allocationsPostRender.buffers === allocationsDisposed.buffers
        && allocationsPostRender.textures === allocationsDisposed.textures
      );
      return {
        counts,
        disposed,
        complete: Object.keys(counts).every((key) => counts[key] === disposed[key]),
        removedFromScene,
        postDisposeFrames,
        memoryBefore,
        memoryDisposed,
        memoryPostRender,
        allocationsBefore,
        allocationsDisposed,
        allocationsPostRender,
        rendererMemoryDidNotRebound,
        webglAllocationsDidNotRebound,
      };
    });
    if (
      !lifecycleCheck.complete
      || !lifecycleCheck.removedFromScene
      || !lifecycleCheck.rendererMemoryDidNotRebound
      || !lifecycleCheck.webglAllocationsDidNotRebound
    ) {
      throw new Error(`Post-disposal lifecycle check failed: ${JSON.stringify(lifecycleCheck)}`);
    }
    if (
      doorArticulation.some(
        (item) => !item.allParented
          || !item.fastenerParentedDirectly
          || !item.fastenerInstancesMoved
          || !item.fixedFastenersStayed,
      )
    ) {
      throw new Error(`Door articulation contract failed: ${JSON.stringify(doorArticulation)}`);
    }
    if (!recoveryArticulation.allParented || !recoveryArticulation.allMoved) {
      throw new Error(
        `Front recovery articulation contract failed: ${JSON.stringify(recoveryArticulation)}`,
      );
    }

    const sources = [
      'index.html',
      'main.js',
      'style.css',
      'package.json',
      'package-lock.json',
      'vite.config.js',
      'scripts/capture.mjs',
      'brick-output/createBrickOffroad.js',
      'brick-output/createBrickOffroad.d.ts',
      'brick-output/brick-variant-config.json',
      'brick-output/brick-offroad-profile.json',
      '../../scripts/append_sculpt_review.py',
      '../../scripts/make_visual_comparison_sheet.py',
      '../../scripts/sculpt_dna.py',
      '../../scripts/sculpt_pass_orchestrator.py',
      '../../scripts/validate_sculpt_spec.py',
      '../../scripts/visual_evidence_hashes.py',
      '../../scripts/migrate_review_policy.py',
      '../../scripts/refresh_brick_reviews.py',
      '../../scripts/verify_release.py',
      '../brick-offroad/object-sculpt-spec.json',
      '../showcase/variants/brick/brick-offroad-v001.json',
      '../showcase/variants/brick/brick-offroad-v002.json',
      '../showcase/variants/brick/brick-offroad-v003.json',
      '../showcase/variants/brick/sculpt-dna-manifest.json',
      '../showcase/showcase-review.json',
      'reference/brick-offroad-reference.jpeg',
    ];
    const evidenceNames = [
      ...stages,
      'final',
      'variant-1',
      'variant-2',
      'variant-3',
    ];
    const outputs = [
      '../../assets/brick-offroad-hero.png',
      '../../assets/brick-offroad-hero.gif',
      '../../assets/brick-offroad-sculpt-dna-result.png',
      'evidence/door-articulation.webp',
      'evidence/showcase-comparison.webp',
      ...evidenceNames.flatMap((name) => [
        `evidence/${name}.webp`,
        `evidence/${name}-comparison.webp`,
      ]),
    ];
    const manifest = {
      schemaVersion: '1.0',
      capture: {
        seed: 20260712,
        variant: 'brick-offroad-base',
        viewport: [1200, 675],
        frames: gifFrameCount,
        fps: gifFps,
        rotationSeconds: gifFrameCount / gifFps,
        chrome: path.basename(chromePath),
        localGitMetadataExposed: false,
        deterministic: true,
        canonicalElapsed,
        deterministicFrameSha256: deterministicHashA,
        portAllocation: 'ephemeral-os-assigned',
        sourceFingerprint: servedFingerprint,
      },
      runtimeStats: stats,
      baseConfiguration,
      variantStats,
      serializationCheck: serializableRoot,
      doorArticulation,
      recoveryArticulation,
      lifecycleCheck,
      referenceSha256: {
        source: await sha256(path.join(assetsDir, 'brick-offroad-reference.jpeg')),
        heroCopy: await sha256(
          path.join(heroDir, 'reference', 'brick-offroad-reference.jpeg'),
        ),
      },
      sourceSha256: Object.fromEntries(
        await Promise.all(
          sources.map(async (relative) => [
            relative,
            await sha256(path.resolve(heroDir, relative)),
          ]),
        ),
      ),
      outputSha256: Object.fromEntries(
        await Promise.all(
          outputs.map(async (relative) => [
            relative,
            await sha256(path.resolve(heroDir, relative)),
          ]),
        ),
      ),
    };
    await writeFile(
      path.join(heroDir, 'artifact-manifest.json'),
      `${JSON.stringify(manifest, null, 2)}\n`,
      'utf8',
    );
  } finally {
    try {
      await browser?.close();
    } finally {
      try {
        await stopServer(server);
      } finally {
        try {
          await rm(framesDir, { recursive: true, force: true });
        } finally {
          try {
            await rm(fingerprintPath, { force: true });
          } finally {
            await releaseCaptureLock(captureLock);
          }
        }
      }
    }
  }
}

if (
  process.argv[1]
  && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
