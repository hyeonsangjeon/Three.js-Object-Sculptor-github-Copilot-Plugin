import { defineConfig } from 'vite';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const heroDir = path.dirname(fileURLToPath(import.meta.url));
const fingerprintSources = [
  'main.js',
  'brick-output/createBrickOffroad.js',
];

export async function brickSourceFingerprint() {
  const digest = createHash('sha256');
  for (const relative of fingerprintSources) {
    digest.update(relative);
    digest.update('\0');
    digest.update(await readFile(path.join(heroDir, relative)));
    digest.update('\0');
  }
  return digest.digest('hex');
}

export default defineConfig({
  base: '/threejs-sculpt-dna/brick/',
  server: {
    host: '127.0.0.1',
    fs: {
      strict: true,
      allow: ['.'],
    },

  },
  preview: {
    host: '127.0.0.1',
  },
  build: {
    target: 'es2022',
  },
});
