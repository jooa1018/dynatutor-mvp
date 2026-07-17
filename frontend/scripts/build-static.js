#!/usr/bin/env node
const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const root = path.resolve(__dirname, '..');
const outDir = path.join(root, 'out');
const binDir = path.join(root, 'node_modules', '.bin');
const isWin = process.platform === 'win32';
const tscBin = path.join(binDir, isWin ? 'tsc.cmd' : 'tsc');

function run(cmd, args) {
  const res = spawnSync(cmd, args, { cwd: root, stdio: 'inherit' });
  if (res.status !== 0) process.exit(res.status ?? 1);
}

function copyDir(src, dest) {
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

run(tscBin, ['--noEmit', '--pretty', 'false']);
fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(path.join(outDir, 'assets'), { recursive: true });
copyDir(path.join(root, 'public'), outDir);

esbuild.buildSync({
  entryPoints: [path.join(root, 'src', 'main.tsx')],
  bundle: true,
  outfile: path.join(outDir, 'assets', 'app.js'),
  format: 'iife',
  platform: 'browser',
  target: ['es2020'],
  jsx: 'automatic',
  minify: true,
  sourcemap: false,
  define: {
    'process.env.NEXT_PUBLIC_DYNATUTOR_API_BASE': JSON.stringify(process.env.NEXT_PUBLIC_DYNATUTOR_API_BASE || ''),
    'process.env.NEXT_PUBLIC_API_BASE': JSON.stringify(process.env.NEXT_PUBLIC_API_BASE || ''),
  },
  loader: { '.css': 'css' },
  logLevel: 'info',
});

// Phase 54: Rapier2D runtime is a separate bundle so the main app stays free
// of Rapier/WASM. The frontend injects this script only when the user opens
// the visualization; WASM compiles only inside load().
esbuild.buildSync({
  entryPoints: [path.join(root, 'src', 'vizRapierRuntime.ts')],
  bundle: true,
  outfile: path.join(outDir, 'assets', 'viz-rapier.js'),
  format: 'iife',
  platform: 'browser',
  target: ['es2020'],
  minify: true,
  sourcemap: false,
  logLevel: 'info',
});

const html = `<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover" />
    <title>DynaTutor</title>
    <meta name="description" content="아이폰14에 최적화한 개인용 동역학 문제풀이 튜터" />
    <meta name="application-name" content="DynaTutor" />
    <meta name="theme-color" content="#FBFBFD" />
    <meta name="format-detection" content="telephone=no" />
    <link rel="manifest" href="/manifest.webmanifest" />
    <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
    <link rel="stylesheet" href="/assets/app.css" />
  </head>
  <body>
    <div id="root"></div>
    <script src="/assets/app.js"></script>
  </body>
</html>
`;
fs.writeFileSync(path.join(outDir, 'index.html'), html);
fs.writeFileSync(path.join(outDir, '404.html'), html);
console.log('DynaTutor static build: out/index.html generated.');
