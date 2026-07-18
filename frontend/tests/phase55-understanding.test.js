const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const Module = require('node:module');
const esbuild = require('esbuild');

const root = path.resolve(__dirname, '..');
const card = fs.readFileSync(path.join(root, 'components', 'understanding', 'ProblemUnderstandingCard.tsx'), 'utf8');
const home = fs.readFileSync(path.join(root, 'components', 'HomeClient.tsx'), 'utf8');
const {
  buildRevisionApprovalPatch,
  buildTextbookCorrectionPatch,
  cloneTextbookParse,
  mergeTextbookCorrectionPatches,
} = require('../lib/textbookCorrections');

test('Phase 55 understanding card exposes graph, evidence, and authority boundary', () => {
  for (const label of ['대상', '운동 구간', '명시 조건', '추론 조건', '구할 값', '검증 경고']) {
    assert.match(card, new RegExp(label));
  }
  assert.match(card, /deterministic solver/);
  assert.match(card, /aria-live="polite"/);
  assert.match(card, /aria-label="운동 구간 순서"/);
  assert.match(card, /구조 수정 적용/);
  assert.match(card, /onCorrect/);
  for (const scope of ['entity', 'segment', 'event', 'fact-binding', 'relation', 'query-binding', 'initial-friction-condition']) {
    assert.match(card, new RegExp(`data-correction=\\"${scope}\\"`));
  }
  assert.match(card, /data-correction="candidate-selection"/);
  assert.match(card, /type="checkbox"/);
  assert.match(card, /candidate_id} system type/);
});

test('Phase 55 correction controls render as native keyboard controls', () => {
  const parse = {
    status: 'accepted', requires_approval: true, approval_fingerprint: 'revision-1',
    entities: [{ entity_id: 'a', kind: 'particle', label: 'A', aliases: [] }],
    segments: [{ segment_id: 's1', order: 1, actor_ids: ['a'], motion_model_candidates: ['constant_acceleration_1d'], start_event_id: null, end_event_id: null, relevance: 'target', evidence_quote: 'A' }],
    motion_segments: [{ segment_id: 's1', order: 1, actor_ids: ['a'], motion_model_candidates: ['constant_acceleration_1d'], start_event_id: null, end_event_id: null, relevance: 'target', evidence_quote: 'A' }],
    events: [], explicit_facts: [], relations: [], queries: [{ query_id: 'q1', output_key: 'acceleration', subject_id: 'a', segment_id: 's1', event_id: null, component: 'magnitude' }],
    assumption_proposals: [], accepted_assumptions: [], warnings: [],
    interpretation_candidates: [{ candidate_id: 'c1', system_type: 'constant_acceleration_1d', subtype: null, target_segment_ids: ['s1'], fact_ids: [], query_ids: ['q1'], assumption_ids: [], reason_code: 'test' }],
  };
  const entry = `
    const React = require('react');
    const { renderToStaticMarkup } = require('react-dom/server');
    const Card = require('./components/understanding/ProblemUnderstandingCard.tsx').default;
    module.exports = () => renderToStaticMarkup(React.createElement(Card, {
      parse: ${JSON.stringify(parse)}, loading: false, onApprove() {}, onCorrect() {}
    }));
  `;
  const built = esbuild.buildSync({
    stdin: { contents: entry, resolveDir: root, sourcefile: 'phase55-render.tsx', loader: 'tsx' },
    bundle: true, platform: 'node', format: 'cjs', target: 'node20', write: false,
    jsx: 'automatic',
    external: ['react', 'react-dom/server'],
  }).outputFiles[0].text;
  const compiled = new Module(path.join(root, 'tests', 'phase55-rendered.cjs'), module);
  compiled.filename = path.join(root, 'tests', 'phase55-rendered.cjs');
  compiled.paths = module.paths;
  compiled._compile(built, compiled.filename);
  const markup = compiled.exports();
  assert.match(markup, /aria-live="polite"/);
  assert.match(markup, /<button[^>]*>이 해석으로 풀기<\/button>/);
  assert.match(markup, /type="checkbox"/);
  assert.match(markup, /aria-label="c1 system type"/);
});

test('confirm approval is revision-bound and sent through the existing solve request', () => {
  assert.match(card, /approval_fingerprint/);
  assert.match(home, /textbook_parse_approval/);
  assert.match(home, /fingerprint/);
  assert.match(home, /textbook_parse_correction/);
  assert.match(home, /buildRevisionApprovalPatch\(/);
  assert.match(home, /current\.approvalFingerprint/);
  assert.match(home, /mergeTextbookCorrectionPatches\(previous, correction\)/);
});

test('corrected revision is replayed together with approval in one API payload', () => {
  const correction = { operations: [{ collection: 'queries', id: 'q1', set: { subject_id: 'b' } }] };
  assert.deepEqual(buildRevisionApprovalPatch('revision-123', correction, 'revision-123'), {
    textbook_parse_approval: { fingerprint: 'revision-123' },
    textbook_parse_correction: correction,
  });
  assert.deepEqual(buildRevisionApprovalPatch('revision-456', null), {
    textbook_parse_approval: { fingerprint: 'revision-456' },
  });
});

test('two corrections merge cumulatively from the original revision and last field wins', () => {
  const first = {
    operations: [{ collection: 'queries', id: 'q1', set: { segment_id: 's2', subject_id: 'a' } }],
  };
  const second = {
    operations: [
      { collection: 'queries', id: 'q1', set: { subject_id: 'b' } },
      { collection: 'entities', id: 'b', set: { label: 'Cart B' } },
    ],
  };
  assert.deepEqual(mergeTextbookCorrectionPatches(first, second), {
    operations: [
      { collection: 'queries', id: 'q1', set: { segment_id: 's2', subject_id: 'b' } },
      { collection: 'entities', id: 'b', set: { label: 'Cart B' } },
    ],
  });
});

test('approval carries cumulative correction and blocks a stale correction fingerprint', () => {
  const cumulative = {
    operations: [
      { collection: 'queries', id: 'q1', set: { segment_id: 's2', subject_id: 'b' } },
    ],
  };
  assert.deepEqual(buildRevisionApprovalPatch('latest', cumulative, 'latest'), {
    textbook_parse_approval: { fingerprint: 'latest' },
    textbook_parse_correction: cumulative,
  });
  assert.throws(
    () => buildRevisionApprovalPatch('latest', cumulative, 'stale'),
    /stale textbook correction fingerprint/,
  );
  assert.throws(
    () => buildRevisionApprovalPatch('latest', cumulative),
    /stale textbook correction fingerprint/,
  );
  assert.deepEqual(buildRevisionApprovalPatch('latest', { operations: [] }, 'stale'), {
    textbook_parse_approval: { fingerprint: 'latest' },
  });
});

test('problem text changes reset the bound correction state on keyboard and symbol input', () => {
  assert.match(home, /current\?\.problemText === nextText \? current : null/);
  assert.match(home, /replaceProblemText\(out\.examples\[0\]\.problem_text\)/);
  assert.match(home, /onChange=\{\(e\) => \{/);
  assert.match(home, /onInsert=\{\(nextText\) => \{/);
  assert.equal((home.match(/setText\(/g) || []).length, 1);
});

test('structural correction builder covers every safe editable binding without numeric edits', () => {
  const original = {
    entities: [{ entity_id: 'a', kind: 'person', label: 'A', aliases: [] }],
    motion_segments: [{ segment_id: 's1', order: 1, actor_ids: ['a'], motion_model_candidates: ['unknown'], start_event_id: 'e1', end_event_id: null, relevance: 'target' }],
    events: [{ event_id: 'e1', kind: 'start', subject_ids: ['a'], segment_id: 's1' }],
    explicit_facts: [{ fact_id: 'f1', semantic_key: 'distance', raw_value: '5', raw_unit: 'm', subject_id: 'a', segment_id: 's1', event_id: null, temporal_role: 'interval', direction: 'positive', relevance: 'solver_input', evidence_quote: '5m' }],
    relations: [{ relation_id: 'r1', kind: 'contact_with', entity_ids: ['a', 'b'], segment_id: 's1' }],
    queries: [{ query_id: 'q1', output_key: 'distance', subject_id: 'a', segment_id: 's1', event_id: null, component: 'magnitude' }],
    assumption_proposals: [{ assumption_id: 'u1', kind: 'starts_from_rest', subject_id: 'a', segment_id: 's1', proposed_semantic_key: 'initial_velocity', proposed_value: '0', proposed_unit: 'm/s', reason: 'start' }],
    interpretation_candidates: [{ candidate_id: 'c1', system_type: 'old', subtype: null, target_segment_ids: ['s1'], fact_ids: ['f1'], query_ids: ['q1'], assumption_ids: ['u1'], reason_code: 'old' }],
  };
  const edited = cloneTextbookParse(original);
  edited.entities[0].kind = 'particle';
  edited.motion_segments[0].order = 2;
  edited.events[0].kind = 'release';
  edited.explicit_facts[0].subject_id = 'b';
  edited.explicit_facts[0].direction = 'negative';
  edited.relations[0].kind = 'slides_on';
  edited.queries[0].event_id = 'e1';
  edited.assumption_proposals[0].kind = 'frictionless';
  edited.interpretation_candidates[0].target_segment_ids = ['s2'];
  edited.interpretation_candidates[0].system_type = 'constant_acceleration_1d';
  edited.interpretation_candidates[0].fact_ids = [];
  // Even if a compromised UI draft mutates values/evidence, they are outside
  // the client and server structural whitelists.
  edited.explicit_facts[0].raw_value = '999';
  edited.explicit_facts[0].raw_unit = 's';
  edited.explicit_facts[0].evidence_quote = 'invented';

  const patch = buildTextbookCorrectionPatch(original, edited);
  assert.deepEqual(patch.operations.map((item) => item.collection), [
    'entities', 'motion_segments', 'events', 'explicit_facts', 'relations',
    'queries', 'assumption_proposals', 'interpretation_candidates',
  ]);
  const factSet = patch.operations.find((item) => item.collection === 'explicit_facts').set;
  assert.deepEqual(factSet, { subject_id: 'b', direction: 'negative' });
  assert.equal(JSON.stringify(patch).includes('999'), false);
  assert.equal(JSON.stringify(patch).includes('invented'), false);
  const candidateSet = patch.operations.find((item) => item.collection === 'interpretation_candidates').set;
  assert.equal(candidateSet.system_type, 'constant_acceleration_1d');
  assert.deepEqual(candidateSet.fact_ids, []);
});
