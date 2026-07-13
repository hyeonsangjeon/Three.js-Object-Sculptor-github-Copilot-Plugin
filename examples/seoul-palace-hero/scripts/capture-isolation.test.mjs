import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import test from 'node:test';
import {
  allocateEphemeralPort,
  stopServer,
  verifySourceFingerprint,
  waitForServer,
} from './capture.mjs';

test('allocates a loopback ephemeral port', async () => {
  const port = await allocateEphemeralPort();
  assert.equal(Number.isInteger(port), true);
  assert.equal(port > 0, true);
});

test('rejects stale capture fingerprints', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response('served-fingerprint\n', { status: 200 });
  try {
    await assert.rejects(
      verifySourceFingerprint('http://127.0.0.1:1', 'expected-fingerprint'),
      /fingerprint mismatch/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('fails when the isolated server exits before readiness', async () => {
  const listeners = new Map();
  const server = {
    once(event, listener) {
      listeners.set(event, listener);
      queueMicrotask(() => listener(1, null));
    },
    removeListener(event) {
      listeners.delete(event);
    },
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('not ready'); };
  try {
    await assert.rejects(
      waitForServer('http://127.0.0.1:1', server, () => 'isolated failure'),
      /exited before capture readiness/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('does not signal or wait for an already exited server', async () => {
  const server = new EventEmitter();
  server.exitCode = 1;
  server.signalCode = null;
  server.kill = () => {
    throw new Error('already exited server must not be signalled');
  };
  await stopServer(server, 1);
});
