import { createHash } from 'node:crypto';
import { access, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { spawn, spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const heroDir = path.resolve(scriptDir, '..');
const repoRoot = path.resolve(heroDir, '..', '..');
const assetsDir = path.join(repoRoot, 'assets');
const evidenceDir = path.join(heroDir, 'evidence');
const framesDir = path.join(heroDir, '.capture-frames');
const baseUrl = 'http://127.0.0.1:4176';
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

async function waitForServer(url) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Vite is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${url}`);
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

async function main() {
  const chromePath = await findChrome();
  const ffmpeg = process.env.FFMPEG_BIN ?? 'ffmpeg';
  run(ffmpeg, ['-version'], { quiet: true });
  run('cwebp', ['-version'], { quiet: true });
  run('python3', ['--version'], { quiet: true });
  await rm(framesDir, { recursive: true, force: true });
  await mkdir(framesDir, { recursive: true });
  await mkdir(evidenceDir, { recursive: true });
  const server = spawn(
    process.platform === 'win32' ? 'npm.cmd' : 'npm',
    ['run', 'dev', '--', '--port', '4176', '--strictPort'],
    {
      cwd: heroDir,
      stdio: 'ignore',
      detached: false,
    },
  );
  let browser;
  try {
    await waitForServer(baseUrl);
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
          'left-door-hinge',
          'door-hinge-left-front--0.38',
          'door-hinge-left-front-0.38',
        ],
        'left-rear-door-pivot': [
          'left-rear-door-panel',
          'rear-side-window-left',
          'rear-door-handle-left',
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
          'right-door-hinge',
          'door-hinge-right-front--0.38',
          'door-hinge-right-front-0.38',
        ],
        'right-rear-door-pivot': [
          'right-rear-door-panel',
          'rear-side-window-right',
          'rear-door-handle-right',
          'right-rear-door-hinge',
          'door-hinge-right-rear--0.38',
          'door-hinge-right-rear-0.38',
        ],
      };
      return Object.entries(contracts).map(([pivotId, childIds]) => {
        const pivot = hero.runtime.nodes[pivotId];
        const target = pivot.getObjectByName(childIds[1]);
        const before = target.getWorldPosition(target.position.clone()).toArray();
        pivot.rotation.y = pivotId.startsWith('left') ? -0.65 : 0.65;
        pivot.updateMatrixWorld(true);
        const after = target.getWorldPosition(target.position.clone()).toArray();
        const result = {
          pivotId,
          childIds,
          allParented: childIds.every((id) => Boolean(pivot.getObjectByName(id))),
          childMoved: before.some(
            (value, index) => Math.abs(value - after[index]) > 1e-4,
          ),
        };
        pivot.rotation.y = 0;
        pivot.updateMatrixWorld(true);
        return result;
      });
    });
    await page.screenshot({ path: path.join(assetsDir, 'brick-offroad-hero.png') });

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
    const variantStats = [];
    for (let variant = 0; variant < 3; variant += 1) {
      await captureEvidence(
        page,
        `variant-${variant + 1}`,
        `${baseUrl}/?stage=full&variant=${variant}&motion=0&ui=0&capture=1&time=${canonicalElapsed}`,
      );
      variantStats.push(await page.evaluate(() => ({
        id: window.__BRICK_HERO__.variant.id,
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
          + '[a][b][c]hstack=inputs=3[sheet];'
          + '[sheet]split[s0][s1];'
          + '[s0]palettegen=max_colors=192[p];'
          + '[s1][p]paletteuse=dither=bayer:bayer_scale=3[out]',
        '-map',
        '[out]',
        '-frames:v',
        '1',
        path.join(assetsDir, 'brick-offroad-sculpt-dna-result.png'),
      ],
      { quiet: true },
    );
    await page.goto(
      `${baseUrl}/?stage=full&variant=base&motion=0&ui=0&capture=1&time=${canonicalElapsed}`,
      { waitUntil: 'networkidle0' },
    );
    await waitForHero(page);
    const lifecycleCheck = await page.evaluate(() => {
      const hero = window.__BRICK_HERO__;
      const resources = hero.runtime.resources;
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
      hero.dispose();
      return {
        counts,
        disposed,
        complete: Object.keys(counts).every((key) => counts[key] === disposed[key]),
      };
    });

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
      '../../scripts/sculpt_pass_orchestrator.py',
      '../brick-offroad/object-sculpt-spec.json',
      '../showcase/variants/brick/brick-offroad-v001.json',
      '../showcase/variants/brick/brick-offroad-v002.json',
      '../showcase/variants/brick/brick-offroad-v003.json',
      '../showcase/variants/brick/sculpt-dna-manifest.json',
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
      },
      runtimeStats: stats,
      baseConfiguration,
      variantStats,
      serializationCheck: serializableRoot,
      doorArticulation,
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
    await browser?.close();
    server.kill('SIGTERM');
    await rm(framesDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
