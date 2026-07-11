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
const baseUrl = 'http://127.0.0.1:4175';


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
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // The local Vite server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${url}`);
}


async function waitForHero(page) {
  await page.waitForFunction(() => window.__REPOLIS_READY__ === true, {
    timeout: 120_000,
  });
}


async function sha256(filePath) {
  const content = await readFile(filePath);
  return createHash('sha256').update(content).digest('hex');
}


async function captureStage(page, stage, sourceName) {
  const pngPath = path.join(framesDir, `${stage}.png`);
  await page.goto(
    `${baseUrl}/?stage=${encodeURIComponent(stage)}&variant=0&motion=0&ui=0`,
    { waitUntil: 'networkidle0' },
  );
  await waitForHero(page);
  await page.screenshot({ path: pngPath });
  const outputPath = path.join(evidenceDir, `${sourceName}.webp`);
  run('cwebp', ['-quiet', '-q', '84', pngPath, '-o', outputPath], { quiet: true });
  const comparisonPng = path.join(framesDir, `${stage}-comparison.png`);
  run(
    'python3',
    [
      path.join(repoRoot, 'scripts', 'make_visual_comparison_sheet.py'),
      '--reference',
      path.join(assetsDir, 'repolis-tree-reference.jpeg'),
      '--render',
      pngPath,
      '--out',
      comparisonPng,
      '--json',
    ],
    { cwd: repoRoot, quiet: true },
  );
  run(
    'cwebp',
    [
      '-quiet',
      '-q',
      '82',
      comparisonPng,
      '-o',
      path.join(evidenceDir, `${sourceName}-comparison.webp`),
    ],
    { quiet: true },
  );
}


async function main() {
  const chromePath = await findChrome();
  await rm(framesDir, { recursive: true, force: true });
  await mkdir(framesDir, { recursive: true });
  await mkdir(evidenceDir, { recursive: true });
  const server = spawn(
    process.platform === 'win32' ? 'npm.cmd' : 'npm',
    ['run', 'dev', '--', '--port', '4175', '--strictPort'],
    {
      cwd: heroDir,
      stdio: 'ignore',
      detached: false,
    },
  );
  let browser;
  try {
    await waitForServer(baseUrl);
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
    const stats = await page.evaluate(() => window.__REPOLIS_HERO__.stats);
    await page.screenshot({
      path: path.join(assetsDir, 'repolis-tree-hero.png'),
    });

    await page.goto(`${baseUrl}/?stage=full&variant=0&motion=0&ui=0`, {
      waitUntil: 'networkidle0',
    });
    await waitForHero(page);
    for (let index = 0; index < 20; index += 1) {
      const angle = -0.35 + index * Math.PI * 2 / 20;
      await page.evaluate((value) => window.__setHeroAngle(value), angle);
      await new Promise((resolve) => setTimeout(resolve, 30));
      await page.screenshot({
        path: path.join(framesDir, `frame-${String(index).padStart(2, '0')}.png`),
      });
    }
    run(
      process.env.FFMPEG_BIN ?? 'ffmpeg',
      [
        '-hide_banner',
        '-loglevel',
        'error',
        '-y',
        '-framerate',
        '10',
        '-i',
        path.join(framesDir, 'frame-%02d.png'),
        '-filter_complex',
        'fps=10,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3',
        '-loop',
        '0',
        path.join(assetsDir, 'repolis-tree-hero.gif'),
      ],
      { quiet: true },
    );

    const stages = [
      ['blockout', 'blockout'],
      ['structural-pass', 'structural-pass'],
      ['form-refinement', 'form-refinement'],
      ['material-pass', 'material-pass'],
      ['surface-pass', 'surface-pass'],
    ];
    for (const [stage, sourceName] of stages) {
      await captureStage(page, stage, sourceName);
    }
    await page.goto(`${baseUrl}/?stage=full&variant=0&motion=0&ui=0`, {
      waitUntil: 'networkidle0',
    });
    await waitForHero(page);
    const finalPng = path.join(framesDir, 'final.png');
    await page.screenshot({ path: finalPng });
    run('cwebp', ['-quiet', '-q', '86', finalPng, '-o', path.join(evidenceDir, 'final.webp')], { quiet: true });
    const finalComparison = path.join(framesDir, 'final-comparison.png');
    run(
      'python3',
      [
        path.join(repoRoot, 'scripts', 'make_visual_comparison_sheet.py'),
        '--reference',
        path.join(assetsDir, 'repolis-tree-reference.jpeg'),
        '--render',
        finalPng,
        '--out',
        finalComparison,
        '--json',
      ],
      { cwd: repoRoot, quiet: true },
    );
    run(
      'cwebp',
      ['-quiet', '-q', '84', finalComparison, '-o', path.join(evidenceDir, 'final-comparison.webp')],
      { quiet: true },
    );

    const sources = [
      'index.html',
      'main.js',
      'style.css',
      'repolis-output/createRepolisHero.js',
      'repolis-output/repolis-hero-profile.json',
      '../repolis-tree/object-sculpt-spec.json',
    ];
    const outputs = [
      '../../assets/repolis-tree-hero.png',
      '../../assets/repolis-tree-hero.gif',
      ...[
        'blockout',
        'structural-pass',
        'form-refinement',
        'material-pass',
        'surface-pass',
        'final',
      ].flatMap((name) => [
        `evidence/${name}.webp`,
        `evidence/${name}-comparison.webp`,
      ]),
    ];
    const manifest = {
      schemaVersion: '1.0',
      capture: {
        seed: 20260711,
        variant: 'golden-canopy',
        viewport: [1200, 675],
        frames: 20,
        fps: 10,
        chrome: path.basename(chromePath),
      },
      runtimeStats: stats,
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
