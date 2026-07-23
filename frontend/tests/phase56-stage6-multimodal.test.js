const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const Module = require('node:module');
const esbuild = require('esbuild');

const root = path.resolve(__dirname, '..');
const home = fs.readFileSync(path.join(root, 'components', 'HomeClient.tsx'), 'utf8');
const panel = fs.readFileSync(path.join(root, 'components', 'mechanics', 'MechanicsMultimodalPanel.tsx'), 'utf8');
const picker = fs.readFileSync(path.join(root, 'components', 'mechanics', 'MechanicsImagePicker.tsx'), 'utf8');
const conflicts = fs.readFileSync(path.join(root, 'components', 'mechanics', 'MechanicsEvidenceConflictPanel.tsx'), 'utf8');
const correction = fs.readFileSync(path.join(root, 'components', 'mechanics', 'MechanicsCorrectionForm.tsx'), 'utf8');
const viewer = fs.readFileSync(path.join(root, 'components', 'mechanics', 'MechanicsEvidenceViewer.tsx'), 'utf8');
const client = fs.readFileSync(path.join(root, 'lib', 'mechanicsMultimodal.ts'), 'utf8');

function renderPanel() {
  const entry = `
    const React = require('react');
    const { renderToStaticMarkup } = require('react-dom/server');
    const { MechanicsMultimodalPanel } = require('./components/mechanics/MechanicsMultimodalPanel.tsx');
    module.exports = () => renderToStaticMarkup(React.createElement(MechanicsMultimodalPanel, {
      problemText: 'A 2 kg mass is acted on by a 10 N force.',
      disabled: false,
      onAuthError() {},
      onVerifiedResult() {},
    }));
  `;
  const built = esbuild.buildSync({
    stdin: { contents: entry, resolveDir: root, sourcefile: 'phase56-stage6-render.tsx', loader: 'tsx' },
    bundle: true,
    platform: 'node',
    format: 'cjs',
    target: 'node20',
    write: false,
    jsx: 'automatic',
    external: ['react', 'react-dom/server'],
    plugins: [{
      name: 'next-image-test-stub',
      setup(build) {
        build.onResolve({ filter: /^next\/image$/ }, () => ({ path: 'next-image-stub', namespace: 'test' }));
        build.onLoad({ filter: /.*/, namespace: 'test' }, () => ({
          loader: 'js',
          contents: `const React = require('react'); module.exports = function Image(props) { return React.createElement('span', { role: 'img', 'aria-label': props.alt || 'image' }); };`,
        }));
      },
    }],
  }).outputFiles[0].text;
  const compiled = new Module(path.join(root, 'tests', 'phase56-stage6-rendered.cjs'), module);
  compiled.filename = path.join(root, 'tests', 'phase56-stage6-rendered.cjs');
  compiled.paths = module.paths;
  compiled._compile(built, compiled.filename);
  return compiled.exports();
}

test('official solve screen renders the Stage 6 panel with existing text state', () => {
  assert.match(home, /import \{ MechanicsMultimodalPanel \}/);
  assert.match(home, /<MechanicsMultimodalPanel/);
  assert.match(home, /problemText=\{text\}/);
  assert.match(home, /onAuthError=/);
  const markup = renderPanel();
  assert.match(markup, /글과 그림으로 풀기/);
  assert.match(markup, /문제 그림/);
  assert.match(markup, /글\+그림 분석하고 풀기|Generic 경로로 분석하고 풀기/);
});

test('multimodal client reuses shared base URL, auth, timeout, and error policy', () => {
  assert.match(client, /apiPostForm/);
  assert.match(client, /apiPostJson/);
  assert.match(client, /\/api\/mechanics\/multimodal\/evidence/);
  assert.match(client, /new FormData\(\)/);
  assert.doesNotMatch(client, /\bfetch\s*\(/);
  assert.doesNotMatch(client, /endpoint\s*:/);
  assert.doesNotMatch(client, /data_base64/);
});

test('picker, evidence, conflict, correction, and verified-answer boundaries are present', () => {
  for (const token of ['onDrop', 'onPaste', 'multiple', '미리보기', '교체', '삭제']) {
    assert.match(picker, new RegExp(token));
  }
  assert.match(conflicts, /신뢰도 점수로 자동 선택하지 않습니다/);
  assert.match(conflicts, /type="radio"/);
  assert.match(viewer, /그림 근거 위치/);
  assert.match(viewer, /mechanics-overlay-region/);
  for (const operation of [
    'accept_evidence', 'reject_evidence', 'replace_quantity_value', 'replace_unit',
    'replace_direction', 'bind_label_to_entity', 'replace_relation',
    'choose_alternative', 'replace_query', 'confirm_assumption', 'reject_assumption',
  ]) {
    assert.match(correction, new RegExp(operation));
  }
  assert.match(panel, /result\?\.terminal === 'solved' && verified/);
  assert.match(panel, /미검산 답은 표시하지 않습니다/);
});
