import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import test from 'node:test';
import {
  allocateEphemeralPort,
  verifySourceFingerprint,
  waitForServer,
} from './capture.mjs';

function listen(server, port) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', resolve);
  });
}

function close(server) {
  return new Promise((resolve, reject) => server.close((error) => (
    error ? reject(error) : resolve()
  )));
}

test('capture allocation avoids an occupied legacy port', async () => {
  const occupied = createServer((_request, response) => response.end('occupied'));
  let ownsLegacyPort = false;
  try {
    await listen(occupied, 4176);
    ownsLegacyPort = true;
  } catch (error) {
    if (error.code !== 'EADDRINUSE') throw error;
  }
  try {
    const allocated = await allocateEphemeralPort();
    assert.notEqual(allocated, 4176);
  } finally {
    if (ownsLegacyPort) await close(occupied);
  }
});

test('source fingerprint rejects a stale server', async () => {
  const stale = createServer((request, response) => {
    if (
      request.url
      === '/threejs-sculpt-dna/brick/__brick-source-fingerprint.txt'
    ) {
      response.end('stale-worktree-fingerprint');
      return;
    }
    response.end('ready');
  });
  await listen(stale, 0);
  const address = stale.address();
  try {
    await assert.rejects(
      verifySourceFingerprint(
        `http://127.0.0.1:${address.port}`,
        'current-worktree-fingerprint',
      ),
      /source fingerprint mismatch/i,
    );
  } finally {
    await close(stale);
  }
});

test('readiness fails immediately when the spawned server exits', async () => {
  const child = spawn(process.execPath, ['--eval', 'process.exit(23)'], {
    stdio: 'ignore',
  });
  await assert.rejects(
    waitForServer('http://127.0.0.1:1', child, () => 'intentional exit'),
    /exited before capture readiness.*intentional exit/i,
  );
});
