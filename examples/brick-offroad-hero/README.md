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

- `variant=0|1|2`
- `stage=blockout|structural-pass|form-refinement|material-pass|surface-pass|full`
- `motion=0` disables automatic rotation
- `ui=0` produces an evidence capture without interface chrome

## Reusable output

The page imports `brick-output/createBrickOffroad.js`, the same zero-import factory intended for application reuse. Its live runtime maps are returned outside `userData`; only serializable IDs and deterministic provenance are stored on the root.

The committed capture measured 592–695ms generation, 56,444–63,572 instance-weighted geometry triangles, 116 scene drawables, and 357 full-frame WebGL calls including shadow, transmission, scene, and output passes. All configurations use 512px independent PBR channels, exactly four wheels, equal tread cadence per wheel, and zero imported meshes. The measured full-frame count remains below the 400-call ObjectSculptSpec budget.

## Regenerate media and evidence

The capture command uses installed Chrome through `puppeteer-core`; it does not download a browser. It requires `ffmpeg` and `cwebp`.

```bash
npm run capture
```

This regenerates the hero PNG, four-second rotating GIF, same-camera stage and variant comparisons, and an SHA-256 artifact manifest.
