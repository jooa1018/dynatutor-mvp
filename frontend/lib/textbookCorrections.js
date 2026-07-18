const EDITABLE_FIELDS = Object.freeze({
  entities: ['kind', 'label', 'aliases'],
  motion_segments: ['order', 'actor_ids', 'motion_model_candidates', 'start_event_id', 'end_event_id', 'relevance'],
  events: ['kind', 'subject_ids', 'segment_id'],
  explicit_facts: ['semantic_key', 'subject_id', 'segment_id', 'event_id', 'temporal_role', 'direction', 'relevance'],
  relations: ['kind', 'entity_ids', 'segment_id'],
  queries: ['output_key', 'subject_id', 'segment_id', 'event_id', 'component'],
  assumption_proposals: ['kind', 'subject_id', 'segment_id', 'proposed_semantic_key', 'reason'],
  interpretation_candidates: ['target_segment_ids'],
});

const ID_FIELDS = Object.freeze({
  entities: 'entity_id',
  motion_segments: 'segment_id',
  events: 'event_id',
  explicit_facts: 'fact_id',
  relations: 'relation_id',
  queries: 'query_id',
  assumption_proposals: 'assumption_id',
  interpretation_candidates: 'candidate_id',
});

function cloneTextbookParse(parse) {
  return JSON.parse(JSON.stringify(parse || {}));
}

function sameValue(left, right) {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

function buildTextbookCorrectionPatch(original, edited) {
  const operations = [];
  for (const [collection, fields] of Object.entries(EDITABLE_FIELDS)) {
    const idField = ID_FIELDS[collection];
    const beforeById = new Map((original?.[collection] || []).map((item) => [item[idField], item]));
    for (const item of edited?.[collection] || []) {
      const before = beforeById.get(item[idField]);
      if (!before) continue;
      const updates = {};
      for (const field of fields) {
        if (!sameValue(before[field], item[field])) updates[field] = item[field];
      }
      if (Object.keys(updates).length) {
        operations.push({ collection, id: item[idField], set: updates });
      }
    }
  }
  return { operations };
}

module.exports = {
  EDITABLE_FIELDS,
  buildTextbookCorrectionPatch,
  cloneTextbookParse,
};
