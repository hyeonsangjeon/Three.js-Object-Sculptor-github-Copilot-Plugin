import { cp } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const showcaseDir = path.dirname(fileURLToPath(import.meta.url));
const variantFamilies = ['tree', 'brick', 'seoul-production'];

export default defineConfig({
  plugins: [
    {
      name: 'copy-showcase-variant-specs',
      async writeBundle(outputOptions) {
        const outputDir = path.resolve(
          showcaseDir,
          outputOptions.dir ?? 'dist',
        );
        await Promise.all(variantFamilies.map((family) => cp(
          path.join(showcaseDir, 'variants', family),
          path.join(outputDir, 'variants', family),
          { recursive: true },
        )));
      },
    },
  ],
});
