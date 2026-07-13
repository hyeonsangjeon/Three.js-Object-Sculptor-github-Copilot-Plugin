# Seoul Palace Scene

Production Three.js flagship for the conditional Seoul Palace Scene Challenge. The scene is a stylized single-view reconstruction from `assets/seoul-challenge-reference.jpeg`, not photogrammetry or a surveyed palace model.

## Run

```bash
npm ci
npm run dev
```

Open `http://127.0.0.1:4178/threejs-sculpt-dna/seoul/`.

Query controls include `variant=0..3`, `view=reference|axis|side|mountain|material|hierarchy`, `lens=full|palace|city|nature`, `gate=0..1`, and deterministic `capture=1&time=1.25`.

## Production evidence

- Factory: `seoul-output/createSeoulPalaceHero.js`
- Runtime profile: `seoul-output/seoul-palace-profile.json`
- Variant controls: `seoul-output/seoul-variant-config.json`
- Locked pass and final evidence: `evidence/`
- Artifact hashes: `artifact-manifest.json`

The accepted base uses 144,472 instance-weighted triangles, 194 drawables, 388 full-frame WebGL calls, one directional shadow map, 35 independent 1024px texture fields, and zero imported meshes. Three curated variants come from a deterministic pool of 24 and preserve the palace axis, gate order, roof topology, hierarchy, sockets, pivots, colliders, and reference camera.
