import { createHash } from 'node:crypto';
import { once } from 'node:events';
import {
  access,
  mkdir,
  open,
  readFile,
  rm,
  writeFile,
} from 'node:fs/promises';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import puppeteer from 'puppeteer-core';
import {
  seoulCanonicalInputFiles,
  seoulRuntimeFingerprint,
  seoulRuntimeInputFiles,
  seoulSourceFingerprint,
} from '../vite.config.js';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const heroDir = path.resolve(scriptDir, '..');
const repoRoot = path.resolve(heroDir, '..', '..');
const assetsDir = path.join(repoRoot, 'assets');
const evidenceDir = path.join(heroDir, 'evidence');
const framesDir = path.join(heroDir, `.capture-frames-${process.pid}`);
const captureLockPath = path.join(heroDir, '.capture.lock');
const fingerprintPath = path.join(heroDir, '__seoul-source-fingerprint.txt');
const canonicalElapsed = 1.25;
const frameCount = 24;
const fps = 6;

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
    onExit = (code, signal) => reject(new Error(
      `Vite exited before capture readiness (code=${code}, signal=${signal}): ${serverOutput()}`,
    ));
    server.once('exit', onExit);
  });
  const ready = (async () => {
    for (let attempt = 0; attempt < 600 && !settled; attempt += 1) {
      try {
        const response = await fetch(url, { cache: 'no-store' });
        if (response.ok) return;
      } catch {
        // The isolated Vite server is still starting.
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
    `${baseUrl}/threejs-sculpt-dna/seoul/__seoul-source-fingerprint.txt`,
    { cache: 'no-store' },
  );
  if (!response.ok) {
    throw new Error(`Capture source fingerprint endpoint failed (${response.status}).`);
  }
  const actual = (await response.text()).trim();
  if (actual !== expected) {
    throw new Error(`Capture source fingerprint mismatch: expected ${expected}, got ${actual}.`);
  }
  return actual;
}

export async function stopServer(server, timeoutMs = 5000) {
  if (!server || server.exitCode !== null || server.signalCode !== null) return;
  const exited = once(server, 'exit');
  if (!server.kill('SIGTERM')) {
    if (server.exitCode !== null || server.signalCode !== null) return;
    throw new Error('Failed to send SIGTERM to the isolated Vite server.');
  }
  const stopped = await Promise.race([
    exited.then(() => true),
    new Promise((resolve) => setTimeout(() => resolve(false), timeoutMs)),
  ]);
  if (stopped || server.exitCode !== null || server.signalCode !== null) return;
  const killed = once(server, 'exit');
  if (!server.kill('SIGKILL')) {
    throw new Error('Failed to send SIGKILL to the isolated Vite server.');
  }
  const forced = await Promise.race([
    killed.then(() => true),
    new Promise((resolve) => setTimeout(() => resolve(false), timeoutMs)),
  ]);
  if (!forced) throw new Error('Timed out stopping the isolated Vite server.');
}

async function sha256(filePath) {
  return createHash('sha256').update(await readFile(filePath)).digest('hex');
}

async function waitForHero(page) {
  await page.waitForFunction(() => window.__SEOUL_READY__ === true, { timeout: 120_000 });
}

async function captureCanonical(
  page,
  baseUrl,
  outputPath,
  variant = 0,
  view = 'reference',
) {
  await page.setViewport({ width: 1200, height: 675, deviceScaleFactor: 1 });
  await page.goto(
    `${baseUrl}/threejs-sculpt-dna/seoul/?stage=optimization-pass&variant=${variant}&view=${encodeURIComponent(view)}&lens=full&gate=0&motion=0&ui=0&capture=1&time=${canonicalElapsed}`,
    { waitUntil: 'networkidle0' },
  );
  await waitForHero(page);
  await page.screenshot({ path: outputPath });
  return page.evaluate(() => ({
    ...window.__SEOUL_HERO__.stats,
    renderCalls: window.__getSeoulRenderInfo().calls,
    renderedTriangles: window.__getSeoulRenderInfo().triangles,
    sourceFingerprint: window.__getSeoulRenderInfo().sourceFingerprint,
    runtimeFingerprint: window.__getSeoulRenderInfo().runtimeFingerprint,
  }));
}

async function main() {
  const lock = await open(captureLockPath, 'wx').catch((error) => {
    if (error.code === 'EEXIST') {
      throw new Error(`Capture lock already exists: ${captureLockPath}`);
    }
    throw error;
  });
  let server;
  let browser;
  let primaryError;

  try {
    const port = await allocateEphemeralPort();
    const baseUrl = `http://127.0.0.1:${port}`;
    const sourceFingerprint = await seoulSourceFingerprint();
    const runtimeFingerprint = await seoulRuntimeFingerprint();
    await writeFile(fingerprintPath, `${sourceFingerprint}\n`);
    await mkdir(framesDir, { recursive: true });
    await mkdir(evidenceDir, { recursive: true });

    let serverOutput = '';
    server = spawn(
      process.platform === 'win32' ? 'npm.cmd' : 'npm',
      ['run', 'dev', '--', '--port', String(port), '--strictPort'],
      { cwd: heroDir, stdio: ['ignore', 'pipe', 'pipe'] },
    );
    server.stdout.on('data', (chunk) => { serverOutput += chunk; });
    server.stderr.on('data', (chunk) => { serverOutput += chunk; });
    await waitForServer(`${baseUrl}/threejs-sculpt-dna/seoul/`, server, () => serverOutput);
    await verifySourceFingerprint(baseUrl, sourceFingerprint);
    browser = await puppeteer.launch({
      executablePath: await findChrome(),
      headless: true,
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    });
    const page = await browser.newPage();
    await page.emulateMediaFeatures([
      { name: 'prefers-reduced-motion', value: 'no-preference' },
    ]);
    const consoleErrors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => consoleErrors.push(error.message));

    const heroPath = path.join(assetsDir, 'seoul-palace-hero.png');
    const repeatedPath = path.join(framesDir, 'canonical-repeat.png');
    const runtimeStats = await captureCanonical(page, baseUrl, heroPath);
    if (runtimeStats.runtimeFingerprint !== runtimeFingerprint) {
      throw new Error('Canonical Seoul runtime fingerprint is stale.');
    }
    const runtimeSnapshot = await page.evaluate(
      () => window.__SEOUL_HERO__.root.userData.sculptRuntime,
    );
    const colliderSnapshot = await page.evaluate(() => Object.fromEntries(
      Object.entries(window.__SEOUL_HERO__.runtime.colliders).map(
        ([id, proxy]) => [
          id,
          {
            parentId: proxy.userData.collider.parentId,
            parentNodeId: proxy.parent?.name ?? null,
            center: proxy.position.toArray(),
            size: [...proxy.userData.collider.size],
          },
        ],
      ),
    ));
    const socketSnapshot = await page.evaluate(() => Object.fromEntries(
      Object.entries(window.__SEOUL_HERO__.runtime.sockets).map(
        ([id, marker]) => [
          id,
          {
            parentNodeId:
              marker.parent?.userData.sculptId
              ?? marker.parent?.name
              ?? null,
            declaredParentNodeId: marker.userData.socket.parentNodeId,
            position: marker.position.toArray(),
            rotation: [
              marker.rotation.x,
              marker.rotation.y,
              marker.rotation.z,
            ],
          },
        ],
      ),
    ));
    await captureCanonical(page, baseUrl, repeatedPath);
    const canonicalHashes = [await sha256(heroPath), await sha256(repeatedPath)];
    if (canonicalHashes[0] !== canonicalHashes[1]) {
      throw new Error('Repeated canonical Seoul captures are not byte-identical.');
    }

    const finalEvidence = path.join(evidenceDir, 'final.png');
    await writeFile(finalEvidence, await readFile(heroPath));
    run('python3', [
      path.join(repoRoot, 'scripts', 'make_visual_comparison_sheet.py'),
      '--reference',
      path.join(assetsDir, 'seoul-challenge-reference.jpeg'),
      '--render',
      finalEvidence,
      '--out',
      path.join(evidenceDir, 'final-comparison.png'),
      '--json',
    ], { cwd: repoRoot, quiet: true });

    const optimizationViews = [
      'reference',
      'axis',
      'side',
      'mountain',
      'material',
      'hierarchy',
    ];
    const baseSpec = JSON.parse(await readFile(path.join(
      repoRoot,
      'examples',
      'seoul-challenge',
      'object-sculpt-spec.json',
    )));
    const optimizationReview = [...baseSpec.reviewHistory]
      .reverse()
      .find((review) => review.passId === 'optimization-pass');
    const optimizationBindings = new Map(
      optimizationReview?.visualEvidence?.supplementalEvidence?.map(
        (item) => [item.path, item.sha256],
      ) ?? [],
    );
    const optimizationCaptures = [];
    for (const view of optimizationViews) {
      const relative = `examples/seoul-palace-hero/evidence/optimization-${view}.png`;
      const temporaryPath = path.join(framesDir, `optimization-${view}.png`);
      await captureCanonical(page, baseUrl, temporaryPath, 0, view);
      optimizationCaptures.push({
        relative,
        temporaryPath,
        outputPath: path.join(evidenceDir, `optimization-${view}.png`),
        sha256: await sha256(temporaryPath),
      });
    }
    const optimizationComparison = {
      relative:
        'examples/seoul-palace-hero/evidence/optimization-pass-comparison.png',
      temporaryPath: path.join(framesDir, 'optimization-pass-comparison.png'),
      outputPath: path.join(evidenceDir, 'optimization-pass-comparison.png'),
    };
    run('python3', [
      path.join(repoRoot, 'scripts', 'make_visual_comparison_sheet.py'),
      '--reference',
      path.join(assetsDir, 'seoul-challenge-reference.jpeg'),
      '--render',
      optimizationCaptures[0].temporaryPath,
      '--out',
      optimizationComparison.temporaryPath,
      '--json',
    ], { cwd: repoRoot, quiet: true });
    optimizationComparison.sha256 = await sha256(
      optimizationComparison.temporaryPath,
    );
    for (const capture of [
      ...optimizationCaptures,
      optimizationComparison,
    ]) {
      if (optimizationBindings.get(capture.relative) !== capture.sha256) {
        throw new Error(
          `${capture.relative} changed; a fresh AI-vision review is required.`,
        );
      }
    }
    for (const capture of [
      ...optimizationCaptures,
      optimizationComparison,
    ]) {
      await writeFile(capture.outputPath, await readFile(capture.temporaryPath));
    }

    const variantRuntimeStats = [];
    for (let variant = 1; variant <= 3; variant += 1) {
      const renderPath = path.join(evidenceDir, `variant-${variant}.png`);
      const comparisonPath = path.join(evidenceDir, `variant-${variant}-comparison.png`);
      const stats = await captureCanonical(
        page,
        baseUrl,
        renderPath,
        variant,
      );
      run('python3', [
        path.join(repoRoot, 'scripts', 'make_visual_comparison_sheet.py'),
        '--reference',
        path.join(assetsDir, 'seoul-challenge-reference.jpeg'),
        '--render',
        renderPath,
        '--out',
        comparisonPath,
        '--json',
      ], { cwd: repoRoot, quiet: true });
      const variantSpec = JSON.parse(await readFile(path.join(
        repoRoot,
        'examples',
        'showcase',
        'variants',
        'seoul-production',
        `seoul-palace-hero-v00${variant}.json`,
      )));
      const acceptance = variantSpec.variantProvenance?.visualAcceptance;
      const currentHashes = {
        referenceSha256: await sha256(path.join(assetsDir, 'seoul-challenge-reference.jpeg')),
        renderSha256: await sha256(renderPath),
        comparisonSha256: await sha256(comparisonPath),
      };
      for (const [field, actual] of Object.entries(currentHashes)) {
        if (acceptance?.[field] !== actual) {
          throw new Error(
            `Variant ${variant} ${field} changed; a fresh AI-vision review is required.`,
          );
        }
      }
      variantRuntimeStats.push(stats);
    }

    await page.setViewport({ width: 960, height: 540, deviceScaleFactor: 1 });
    const animationFrameHashes = [];
    for (let index = 0; index < frameCount; index += 1) {
      const time = canonicalElapsed + index / fps;
      await page.goto(
        `${baseUrl}/threejs-sculpt-dna/seoul/?stage=optimization-pass&variant=0&lens=full&gate=0&motion=0&ui=0&capture=1&tour=1&captureTour=1&time=${time}`,
        { waitUntil: 'networkidle0' },
      );
      await waitForHero(page);
      const framePath = path.join(
        framesDir,
        `frame-${String(index).padStart(2, '0')}.png`,
      );
      await page.screenshot({ path: framePath });
      animationFrameHashes.push(await sha256(framePath));
    }
    const uniqueAnimationFrames = new Set(animationFrameHashes).size;
    if (uniqueAnimationFrames < 2) {
      throw new Error('Animated Seoul capture produced no frame diversity.');
    }
    const gifPath = path.join(assetsDir, 'seoul-palace-hero.gif');
    run(process.env.FFMPEG_BIN ?? 'ffmpeg', [
      '-y',
      '-framerate',
      String(fps),
      '-i',
      path.join(framesDir, 'frame-%02d.png'),
      '-filter_complex',
      `[0:v]fps=${fps},split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer`,
      gifPath,
    ], { quiet: true });

    if (consoleErrors.length) {
      throw new Error(`Browser console errors: ${consoleErrors.join('; ')}`);
    }

    const outputFiles = [
      '../../assets/seoul-palace-hero.png',
      '../../assets/seoul-palace-hero.gif',
      'evidence/final.png',
      'evidence/final-comparison.png',
      'evidence/variant-1.png',
      'evidence/variant-1-comparison.png',
      'evidence/variant-2.png',
      'evidence/variant-2-comparison.png',
      'evidence/variant-3.png',
      'evidence/variant-3-comparison.png',
      'evidence/optimization-reference.png',
      'evidence/optimization-axis.png',
      'evidence/optimization-side.png',
      'evidence/optimization-mountain.png',
      'evidence/optimization-material.png',
      'evidence/optimization-hierarchy.png',
      'evidence/optimization-pass-comparison.png',
    ];
    const sourceSha256 = {};
    const runtimeSha256 = {};
    const outputSha256 = {};
    for (const relative of seoulCanonicalInputFiles) {
      sourceSha256[relative] = await sha256(path.resolve(heroDir, relative));
    }
    for (const relative of seoulRuntimeInputFiles) {
      runtimeSha256[relative] = await sha256(path.resolve(heroDir, relative));
    }
    for (const relative of outputFiles) outputSha256[relative] = await sha256(path.resolve(heroDir, relative));

    const manifest = {
      schemaVersion: '1.0',
      sourceFingerprint,
      sourceFiles: [...seoulCanonicalInputFiles],
      sourceSha256,
      runtimeFingerprint,
      runtimeFiles: [...seoulRuntimeInputFiles],
      runtimeSha256,
      runtimeSnapshot,
      colliderSnapshot,
      socketSnapshot,
      outputSha256,
      runtimeStats,
      variantRuntimeStats,
      capture: {
        browser: 'installed Chrome via puppeteer-core',
        canonical: {
          width: 1200,
          height: 675,
          stage: 'optimization-pass',
          camera: 'reference',
          time: canonicalElapsed,
        },
        animation: {
          width: 960,
          height: 540,
          frames: frameCount,
          fps,
          seconds: 4,
          reducedMotion: 'no-preference',
          uniqueFrameCount: uniqueAnimationFrames,
        },
        deterministicRepeatedCapture: true,
        repeatedCanonicalSha256: canonicalHashes[0],
        localGitMetadataExposed: false,
        isolatedLoopbackServer: true,
        ephemeralPort: true,
      },
    };
    await writeFile(
      path.join(heroDir, 'artifact-manifest.json'),
      `${JSON.stringify(manifest, null, 2)}\n`,
    );
  } catch (error) {
    primaryError = error;
    throw error;
  } finally {
    const cleanupErrors = [];
    for (const cleanup of [
      async () => { if (browser) await browser.close(); },
      async () => stopServer(server),
      async () => lock.close(),
      async () => rm(captureLockPath, { force: true }),
      async () => rm(fingerprintPath, { force: true }),
      async () => rm(framesDir, { recursive: true, force: true }),
    ]) {
      try {
        await cleanup();
      } catch (error) {
        cleanupErrors.push(error);
      }
    }
    if (cleanupErrors.length) {
      throw new AggregateError(
        primaryError ? [primaryError, ...cleanupErrors] : cleanupErrors,
        'Seoul capture cleanup failed.',
      );
    }
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
