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

    await page.goto(`${baseUrl}/?stage=full&variant=0&motion=0`, {
      waitUntil: 'networkidle0',
    });
    await waitForHero(page);
    await page.evaluate(() => window.__setBrickReferenceView());
    const stats = await readRuntimeStats(page);
    const serializableRoot = await page.evaluate(() => {
      const hero = window.__BRICK_HERO__;
      const json = hero.root.toJSON();
      return {
        rootName: json.object.name,
        runtimeKeys: Object.keys(hero.runtime),
        userData: hero.root.userData,
      };
    });
    await page.screenshot({ path: path.join(assetsDir, 'brick-offroad-hero.png') });

    await page.goto(`${baseUrl}/?stage=full&variant=0&motion=0&ui=0`, {
      waitUntil: 'networkidle0',
    });
    await waitForHero(page);
    for (let index = 0; index < gifFrameCount; index += 1) {
      const angle = -0.04 + index * Math.PI * 2 / gifFrameCount;
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

    for (const stage of stages) {
      await captureEvidence(
        page,
        stage,
        `${baseUrl}/?stage=${encodeURIComponent(stage)}&variant=0&motion=0&ui=0`,
      );
    }
    await captureEvidence(
      page,
      'final',
      `${baseUrl}/?stage=full&variant=0&motion=0&ui=0`,
    );
    const variantStats = [];
    for (let variant = 0; variant < 3; variant += 1) {
      await captureEvidence(
        page,
        `variant-${variant + 1}`,
        `${baseUrl}/?stage=full&variant=${variant}&motion=0&ui=0`,
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
      '../../scripts/make_visual_comparison_sheet.py',
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
      ...evidenceNames.flatMap((name) => [
        `evidence/${name}.webp`,
        `evidence/${name}-comparison.webp`,
      ]),
    ];
    const manifest = {
      schemaVersion: '1.0',
      capture: {
        seed: 20260712,
        variant: 'brick-offroad-v001',
        viewport: [1200, 675],
        frames: gifFrameCount,
        fps: gifFps,
        rotationSeconds: gifFrameCount / gifFps,
        chrome: path.basename(chromePath),
        localGitMetadataExposed: false,
      },
      runtimeStats: stats,
      variantStats,
      serializationCheck: serializableRoot,
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
