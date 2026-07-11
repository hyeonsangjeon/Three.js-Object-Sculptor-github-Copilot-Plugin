# Repolis Hero Tree Output

Reusable procedural Three.js output for the Repolis application.

```js
import { createRepolisHero } from './createRepolisHero.js';

const hero = createRepolisHero({
  seed: 20260711,
  variant: 'golden-canopy',
  stage: 'full',
});

scene.add(hero.root);

// Live Object3D maps stay outside userData so cloning and serialization remain safe.
const leftBranch = hero.runtime.nodes['left-foundation'];

function animate(time) {
  hero.update(time * 0.001);
}
```

The factory imports no mesh asset. It generates curve-swept branches, independent bark PBR maps, foliage, moss, ground details, energy paths, sockets, colliders, and destruction groups at runtime.

Call `hero.dispose()` when removing the asset.
