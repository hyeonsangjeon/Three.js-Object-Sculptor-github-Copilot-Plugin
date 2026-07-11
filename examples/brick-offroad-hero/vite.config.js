import { defineConfig } from 'vite';

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
