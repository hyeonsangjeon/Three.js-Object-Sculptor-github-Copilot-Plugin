# Repolis Tree Flagship

Interactive, code-native flagship generated from `assets/repolis-tree-reference.jpeg`.

## Run

```bash
cd examples/repolis-hero
npm install
npm run dev
```

Open `http://127.0.0.1:4174/`.

Query parameters:

- `variant=0|1|2`
- `stage=blockout|structural-pass|form-refinement|material-pass|surface-pass|full`
- `motion=0` to disable automatic rotation
- `ui=0` for a clean render

## Production output

Copy `repolis-output/` into the Repolis application. The demo imports that exact factory rather than a separate showcase implementation.

The full Golden Canopy configuration produces approximately:

- 15 macro/root branches
- 56 secondary branches
- 112 fine branches
- 17,761 branch vertices
- 2,600 instanced leaves
- 220 moss instances
- 72 code glyphs
- 0 imported mesh assets

Generation time is measured in the browser and normally stays near 100ms on the development machine.

## Regenerate committed media and evidence

The capture command uses an installed Chrome/Chromium through `puppeteer-core`; it does not download a browser.

Requirements: `ffmpeg`, `cwebp`, and Chrome. Set `CHROME_BIN` when Chrome is not in a standard location.

```bash
npm run capture
```

This regenerates the hero PNG, rotating GIF, staged review evidence, comparison sheets, and `artifact-manifest.json` with source/output SHA-256 hashes.
