import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

import {
  SEOUL_REFERENCE_CAMERA_VIEW,
  createSeoulPalaceHero,
} from '../seoul-output/createSeoulPalaceHero.js';


const variant = {
  id: 'seed-contract-test',
  seed: '1996682606581385420',
  roofRoughness: 0.72,
  roofAccent: '#315B52',
  courtyardRoughness: 0.9,
  courtyardTone: '#C7AB77',
  treeDensity: 560,
  cityDensity: 148,
  mountainForestDensity: 720,
  mountainRockDensity: 46,
};


test('default blockout preserves action pivots, sockets, and aliases', () => {
  const hero = createSeoulPalaceHero();
  try {
    assert.equal(hero.stats.stage, 'blockout');
    assert.equal(hero.stats.sockets, 14);
    assert.equal(hero.stats.colliders, 27);
    assert.equal(
      Object.keys(hero.root.userData.sculptRuntime.semanticNodeAliases).length,
      33,
    );
    for (const [semanticId, targetId] of Object.entries(
      hero.root.userData.sculptRuntime.semanticNodeAliases,
    )) {
      assert.ok(hero.runtime.nodes[semanticId], semanticId);
      assert.ok(
        hero.runtime.nodes[targetId] ?? hero.runtime.meshes[targetId],
        targetId,
      );
    }
    const expectedParents = {
      'outer-gate-left-hinge': 'outer-gate-west-leaf-pivot',
      'outer-gate-right-hinge': 'outer-gate-east-leaf-pivot',
      'inner-gate-left-hinge': 'inner-gate-west-leaf-pivot',
      'inner-gate-right-hinge': 'inner-gate-east-leaf-pivot',
      'main-hall-roof-apex': 'main-hall-roof',
    };
    for (const [socketId, parentNodeId] of Object.entries(expectedParents)) {
      const socket = hero.runtime.sockets[socketId];
      assert.equal(socket.parent.userData.sculptId, parentNodeId);
      assert.equal(socket.userData.socket.parentNodeId, parentNodeId);
    }
    const hingedMeshes = Object.values(hero.runtime.meshes).filter(
      (mesh) => mesh.userData.attachment?.contactType === 'hinged',
    );
    assert.equal(hingedMeshes.length, 4);
    for (const mesh of hingedMeshes) {
      assert.ok(
        hero.runtime.sockets[mesh.userData.attachment.parentSocket],
        `${mesh.userData.sculptId} must resolve its hinge socket`,
      );
    }
    const referenceSocket = hero.runtime.sockets.ReferenceCamera;
    assert.deepEqual(
      referenceSocket.position.toArray(),
      [...SEOUL_REFERENCE_CAMERA_VIEW.position],
    );
    const expectedCamera = new THREE.PerspectiveCamera();
    expectedCamera.position.fromArray(SEOUL_REFERENCE_CAMERA_VIEW.position);
    expectedCamera.lookAt(...SEOUL_REFERENCE_CAMERA_VIEW.target);
    assert.ok(referenceSocket.quaternion.angleTo(expectedCamera.quaternion) < 1e-12);
    hero.setGateOpen(1);
    assert.notEqual(
      hero.runtime.nodes['outer-gate-west-leaf-pivot'].rotation.y,
      0,
    );
    assert.notEqual(
      hero.runtime.nodes['inner-gate-east-leaf-pivot'].rotation.y,
      0,
    );
  } finally {
    hero.dispose();
  }
});


test('variant seed fallback uses exact unsigned decimal low bits', () => {
  const hero = createSeoulPalaceHero({ variant });
  try {
    assert.equal(hero.stats.seed, 1987840204);
    assert.equal(hero.stats.variantId, variant.id);
  } finally {
    hero.dispose();
  }
});
