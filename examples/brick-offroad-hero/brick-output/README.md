# Brick Off-Road Explorer Output

Reusable procedural Three.js vehicle output with no imported mesh assets.

```js
import { createBrickOffroad } from './createBrickOffroad.js';

const explorer = createBrickOffroad({
  seed: 20260712,
  variant: 'brick-offroad-v001',
  stage: 'full',
});

scene.add(explorer.root);
explorer.runtime.nodes['left-door-pivot'].rotation.y = 0.35;
explorer.update(performance.now() * 0.001);
```

Live `Object3D` references stay in `result.runtime`; `root.userData` contains only serializable IDs and provenance. The factory exposes four wheel pivots, two steering pivots, four suspension anchors, hinged hood/doors/tailgate, roof sockets, collider metadata, and semantic destruction groups.

`brick-variant-config.json` mirrors every material and repetition mutation from the three production ObjectSculptSpec variants. The capture manifest hashes that config, all three variant specs, and their production manifest.

Call `explorer.dispose()` after removing the asset.
