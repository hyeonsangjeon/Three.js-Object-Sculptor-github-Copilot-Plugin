# Brick Off-Road Explorer Flagship

Interactive, code-native reconstruction of `assets/brick-offroad-reference.jpeg`.

## Run

```bash
cd examples/brick-offroad-hero
npm install
npm run dev
```

Open `http://127.0.0.1:4176/`.

Query parameters:

- `variant=base|0|1|2`
- `stage=blockout|structural-pass|form-refinement|material-pass|surface-pass|full`
- `motion=0` disables automatic rotation
- `ui=0` produces an evidence capture without interface chrome
- `capture=1&time=1.25` freezes every animated channel at the canonical evidence time

## Reusable output

The page imports `brick-output/createBrickOffroad.js`, the same zero-import factory intended for application reuse. Its live runtime maps are returned outside `userData`; only serializable IDs and deterministic provenance are stored on the root.

The committed capture measured 566–639ms generation, 63,564–68,324 instance-weighted geometry triangles, 122 scene drawables, and 375 full-frame WebGL calls including shadow, transmission, scene, and output passes. All configurations use 512px independent PBR channels, exactly four wheels, equal tread cadence per wheel, and zero imported meshes. The measured full-frame count remains below the 400-call ObjectSculptSpec budget.

## Regenerate media and evidence

The capture command uses installed Chrome through `puppeteer-core`; it does not download a browser. Preflight requirements are Python 3, `ffmpeg`, `cwebp`, and an installed Chrome or Chromium executable.

```bash
npm run capture
```

This regenerates the hero PNG, four-second rotating GIF, exact-base stage/final comparisons, variant comparisons, opened-door evidence, lifecycle checks, and an SHA-256 artifact manifest. The command captures the canonical frame twice and fails if the pixels differ.
