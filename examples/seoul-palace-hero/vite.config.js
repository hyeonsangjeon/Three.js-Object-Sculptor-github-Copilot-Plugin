import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const heroDir = path.dirname(fileURLToPath(import.meta.url));
export const seoulCanonicalInputFiles = Object.freeze([
  '../seoul-challenge/assessment.json',
  '../seoul-challenge/object-sculpt-spec.json',
  '../showcase/variants/seoul-production/sculpt-dna-manifest.json',
  '../showcase/variants/seoul-production/seoul-palace-hero-v001.json',
  '../showcase/variants/seoul-production/seoul-palace-hero-v002.json',
  '../showcase/variants/seoul-production/seoul-palace-hero-v003.json',
  '../../assets/seoul-challenge-reference.jpeg',
  '../../scripts/make_visual_comparison_sheet.py',
  'index.html',
  'main.js',
  'package-lock.json',
  'package.json',
  'scripts/capture-isolation.test.mjs',
  'scripts/capture.mjs',
  'scripts/factory-contract.test.mjs',
  'style.css',
  'vite.config.js',
  'seoul-output/createSeoulPalaceHero.d.ts',
  'seoul-output/createSeoulPalaceHero.js',
  'seoul-output/createProceduralMaterials.js',
  'seoul-output/seoul-palace-profile.json',
  'seoul-output/seoul-variant-config.json',
]);

export const seoulRuntimeInputFiles = Object.freeze([
  'index.html',
  'main.js',
  'package-lock.json',
  'package.json',
  'style.css',
  'vite.config.js',
  'seoul-output/createSeoulPalaceHero.js',
  'seoul-output/createProceduralMaterials.js',
  'seoul-output/seoul-variant-config.json',
]);

async function fingerprint(files) {
  const digest = createHash('sha256');
  for (const relative of files) {
    digest.update(relative);
    digest.update('\0');
    digest.update(await readFile(path.join(heroDir, relative)));
    digest.update('\0');
  }
  return digest.digest('hex');
}

export async function seoulSourceFingerprint() {
  return fingerprint(seoulCanonicalInputFiles);
}

export async function seoulRuntimeFingerprint() {
  return fingerprint(seoulRuntimeInputFiles);
}

export default defineConfig(async () => ({
  base: '/threejs-sculpt-dna/seoul/',
  define: {
    __SEOUL_SOURCE_FINGERPRINT__: JSON.stringify(await seoulSourceFingerprint()),
    __SEOUL_RUNTIME_FINGERPRINT__: JSON.stringify(
      await seoulRuntimeFingerprint(),
    ),
  },
  server: {
    host: '127.0.0.1',
    fs: {
      strict: true,
      allow: [heroDir],
    },
  },
  preview: {
    host: '127.0.0.1',
  },
  build: {
    target: 'es2022',
  },
}));
