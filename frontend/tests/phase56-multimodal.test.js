const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), 'utf8');

const home = read('components', 'HomeClient.tsx');
const panel = read('components', 'mechanics', 'MechanicsMultimodalPanel.tsx');
const picker = read('components', 'mechanics', 'MechanicsImagePicker.tsx');
const viewer = read('components', 'mechanics', 'MechanicsEvidenceViewer.tsx');
const correction = read('components', 'mechanics', 'MechanicsCorrectionForm.tsx');
const client = read('lib', 'mechanicsMultimodal.ts');
const api = read('lib', 'api.ts');
const styles = `${read('styles', 'globals.css')}\n${read('styles', 'mechanics-stage6.css')}`;

test('official solve screen renders the Stage 6 panel against the existing problem text', () => {
  assert.match(home, /import \{ MechanicsMultimodalPanel \}/);
  assert.match(home, /<MechanicsMultimodalPanel/);
  assert.match(home, /problemText=\{text\}/);
  assert.match(home, /onAuthError=/);
  assert.match(home, /onVerifiedResult=/);
});

test('multimodal client reuses the authoritative API base, token, timeout, and error policy', () => {
  assert.match(client, /apiPostForm/);
  assert.match(client, /apiPostJson/);
  assert.match(client, /apiGetJson/);
  assert.doesNotMatch(client, /\bfetch\s*\(/);
  assert.match(client, /\/api\/mechanics\/multimodal\/evidence/);
  assert.match(api, /NEXT_PUBLIC_DYNATUTOR_API_BASE/);
  assert.match(api, /x-dynatutor-token/);
  assert.match(api, /ApiAuthError/);
  assert.match(api, /AbortController/);
});

test('image UX supports file selection, drag\/drop, paste, preview, remove, and replace without raw base64', () => {
  for (const marker of ['onDrop=', 'onPaste=', 'multiple', '미리보기', '교체', '삭제']) {
    assert.match(picker, new RegExp(marker));
  }
  assert.match(picker, /from 'next\/image'/);
  assert.doesNotMatch(picker, /<img\b/);
  assert.doesNotMatch(client, /data_base64/);
  assert.doesNotMatch(client, /FileReader/);
});

test('evidence, correction, and verified-answer boundaries are visible and source-only', () => {
  assert.match(viewer, /그림 근거 위치/);
  assert.match(viewer, /계산 권한이 없습니다/);
  for (const kind of [
    'accept_evidence', 'reject_evidence', 'replace_quantity_value', 'replace_unit',
    'replace_direction', 'bind_label_to_entity', 'replace_relation',
    'choose_alternative', 'replace_query', 'confirm_assumption', 'reject_assumption',
  ]) {
    assert.match(correction, new RegExp(`'${kind}'`));
  }
  assert.match(correction, /방정식·solver·root·검산·최종 답은 직접 수정할 수 없습니다/);
  assert.match(panel, /result\?\.terminal === 'solved' && verified/);
  assert.match(panel, /미검산 답은 표시하지 않습니다/);
  assert.match(panel, /executeMechanicsMultimodalRevision/);
});

test('Stage 6 styles include responsive, keyboard-focus, and reduced-motion safeguards', () => {
  assert.match(styles, /mechanics-multimodal-panel/);
  assert.match(styles, /:focus-visible/);
  assert.match(styles, /@media \(max-width:/);
  assert.match(styles, /prefers-reduced-motion/);
});
