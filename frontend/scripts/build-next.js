#!/usr/bin/env node
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const binDir = path.join(root, 'node_modules', '.bin');
const isWin = process.platform === 'win32';
const nextBin = path.join(binDir, isWin ? 'next.cmd' : 'next');
const tscBin = path.join(binDir, isWin ? 'tsc.cmd' : 'tsc');

function run(cmd, args) {
  const out = spawnSync(cmd, args, {
    cwd: root,
    stdio: 'inherit',
    env: {
      ...process.env,
      NEXT_PRIVATE_BUILD_WORKER: '1',
      NEXT_TELEMETRY_DISABLED: '1',
    },
  });
  if (out.status !== 0) process.exit(out.status ?? 1);
}

fs.rmSync(path.join(root, '.next'), { recursive: true, force: true });
fs.rmSync(path.join(root, 'out'), { recursive: true, force: true });
run(tscBin, ['--noEmit', '--pretty', 'false']);

// Next 15's normal static export can occasionally stall in the final tracing step
// on constrained Node 20 CI containers. Compile mode still produces the static
// out/ directory for this client-only Pages Router app and exits cleanly.
run(nextBin, ['build', '--experimental-build-mode', 'compile']);

const indexHtml = path.join(root, 'out', 'index.html');
if (!fs.existsSync(indexHtml)) {
  console.error('DynaTutor build failed: out/index.html was not generated.');
  process.exit(1);
}
console.log('DynaTutor build: out/index.html generated.');
