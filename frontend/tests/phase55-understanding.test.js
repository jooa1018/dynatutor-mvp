const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const card = fs.readFileSync(path.join(root, 'components', 'understanding', 'ProblemUnderstandingCard.tsx'), 'utf8');
const home = fs.readFileSync(path.join(root, 'components', 'HomeClient.tsx'), 'utf8');

test('Phase 55 understanding card exposes graph, evidence, and authority boundary', () => {
  for (const label of ['대상', '운동 구간', '명시 조건', '추론 조건', '구할 값', '검증 경고']) {
    assert.match(card, new RegExp(label));
  }
  assert.match(card, /deterministic solver/);
  assert.match(card, /aria-live="polite"/);
  assert.match(card, /aria-label="운동 구간 순서"/);
});

test('confirm approval is revision-bound and sent through the existing solve request', () => {
  assert.match(card, /approval_fingerprint/);
  assert.match(home, /textbook_parse_approval/);
  assert.match(home, /fingerprint/);
});
