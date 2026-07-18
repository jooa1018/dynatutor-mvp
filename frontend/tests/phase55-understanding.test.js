const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const card = fs.readFileSync(path.join(root, 'components', 'understanding', 'ProblemUnderstandingCard.tsx'), 'utf8');
const home = fs.readFileSync(path.join(root, 'components', 'HomeClient.tsx'), 'utf8');
const { buildTextbookCorrectionPatch, cloneTextbookParse } = require('../lib/textbookCorrections');

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
});

test('confirm approval is revision-bound and sent through the existing solve request', () => {
  assert.match(card, /approval_fingerprint/);
  assert.match(home, /textbook_parse_approval/);
  assert.match(home, /fingerprint/);
  assert.match(home, /textbook_parse_correction/);
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
    interpretation_candidates: [{ candidate_id: 'c1', target_segment_ids: ['s1'] }],
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
});
