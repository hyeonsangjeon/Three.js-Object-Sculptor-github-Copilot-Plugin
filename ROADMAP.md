# Roadmap

`threejs-sculpt-dna` turns reference images into quality-gated procedural Three.js assets and deterministic design families.

The roadmap prioritizes reproducibility, visual evidence, action-ready hierarchy, and honest limits over one-shot output volume.

## Current: 0.4.x

- GitHub Copilot plugin and repository marketplace
- reference suitability and complexity assessment
- versioned `ObjectSculptSpec`
- locked sculpt passes with browser and AI-vision evidence
- generated PBR channels and Three.js factory scaffolds
- action-ready pivots, sockets, collider proxies, and destruction groups
- Sculpt DNA constraints, invariants, deterministic provenance, and preview mode
- Coverage Curator
- Repolis Living Archive flagship and reproducible capture pipeline

## 0.5 — Reproducible quality

### Visual regression matrix

- render promoted variants from fixed cameras
- compare geometry, material, lighting, and semantic feature layers
- store thresholds and failures in machine-readable reports
- support CPU/GPU-tolerant image review without making pixel diff the final authority

### Region-aware reference extraction

- select material crops independently from the full reference
- preserve crop coordinates and source hashes in `referencePbr`
- compare extraction confidence per material
- reject mixed-background or mixed-material crops

### Better generated geometry

- implement object-specific curve sweep, lathe, extrusion, and instancing templates
- add attachment-safe derived controls for dimensions and collider updates
- retain deterministic geometry across variant ordering and rebuilds

### Coverage Curator 2

- combine parameter-space and render-space diversity
- expose why each candidate was selected
- detect visually redundant controls
- support user-prioritized semantic dimensions

## 0.6 — Multi-reference and runtime adapters

- front/side/back reference fusion with explicit confidence
- React Three Fiber adapter
- optional GLB export after procedural generation
- physics adapters for Rapier and Cannon
- animation helpers for pivots, sockets, bend chains, and material states
- deterministic destruction and debris helpers

## 1.0 criteria

- stable ObjectSculptSpec and Sculpt DNA schemas
- documented migration policy
- Linux, macOS, and Windows image-processing paths
- reproducible examples for botanical, hard-surface, architectural, and scene-layer challenges
- automated marketplace validation
- complete installation, security, contribution, and release documentation

## Not planned

- claiming exact photogrammetry from one image
- silently downloading third-party mesh packs
- accepting variants that bypass base sculpt or visual evidence gates
- replacing technical artists for production assets that require manual topology, UV, rigging, or fabrication accuracy

## Proposing roadmap changes

Open a feature request describing:

1. the user problem
2. why existing spec fields or scripts are insufficient
3. the expected workflow and output
4. compatibility and migration impact
5. how the result can be verified
