const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');

test('static browser bundle contains no unresolved process.env access', () => {
  const result = spawnSync(process.execPath, ['scripts/build-static.js'], {
    cwd: root,
    encoding: 'utf8',
  });

  assert.equal(result.status, 0, result.stderr || result.stdout);

  const bundle = fs.readFileSync(path.join(root, 'out', 'assets', 'app.js'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'out', 'index.html'), 'utf8');

  assert.doesNotMatch(bundle, /\bprocess\.env\./);
  assert.match(html, /<div id="root"><\/div>/);
  assert.match(html, /<script src="\/assets\/app\.js"><\/script>/);
});
