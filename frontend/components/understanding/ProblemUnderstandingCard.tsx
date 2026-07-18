'use client';

import { useEffect, useState } from 'react';
import { Section, List } from '../Card';
import { buildTextbookCorrectionPatch, cloneTextbookParse } from '../../lib/textbookCorrections';

const STATUS_LABELS: Record<string, string> = {
  accepted: '검증된 해석',
  accepted_with_visible_assumptions: '가정을 표시하고 검증된 해석',
  needs_confirmation: '조건 확인 필요',
  needs_figure: '그림 정보 필요',
  insufficient_information: '조건 부족',
  solver_gap: '지원 solver 없음',
  parser_unavailable: '구조화 parser 사용 불가',
  parser_error: '구조화 오류',
};

function factText(fact: any) {
  return `${fact.semantic_key}: ${fact.raw_value}${fact.raw_unit ? ` ${fact.raw_unit}` : ''} · ${fact.subject_id}${fact.segment_id ? ` / ${fact.segment_id}` : ''}`;
}

export default function ProblemUnderstandingCard({
  parse,
  loading,
  onApprove,
  onCorrect,
}: {
  parse: any;
  loading: boolean;
  onApprove: (fingerprint: string) => void;
  onCorrect: (patch: any) => void;
}) {
  const [draft, setDraft] = useState<any>(null);
  useEffect(() => {
    if (!parse) return setDraft(null);
    setDraft(cloneTextbookParse({
      ...parse,
      motion_segments: parse.motion_segments ?? parse.segments ?? [],
    }));
  }, [parse]);
  if (!parse) return null;
  const segments = [...(parse.segments ?? [])].sort((a: any, b: any) => a.order - b.order);
  const directFacts = (parse.explicit_facts ?? []).filter((fact: any) => ['solver_input', 'constraint'].includes(fact.relevance));
  const contextFacts = (parse.explicit_facts ?? []).filter((fact: any) => ['context_only', 'unused'].includes(fact.relevance));
  const assumptions = parse.accepted_assumptions ?? [];
  const canApprove = parse.requires_approval && parse.approval_fingerprint && ['accepted', 'accepted_with_visible_assumptions'].includes(parse.status);

  const draftSegments = draft?.motion_segments ?? [];
  const entityIds = (draft?.entities ?? []).map((item: any) => item.entity_id);
  const segmentIds = draftSegments.map((item: any) => item.segment_id);
  const eventIds = (draft?.events ?? []).map((item: any) => item.event_id);

  function setField(collection: string, index: number, field: string, value: any) {
    setDraft((current: any) => {
      const next = cloneTextbookParse(current);
      next[collection][index][field] = value;
      return next;
    });
  }

  function csv(value: string) {
    return value.split(',').map((item) => item.trim()).filter(Boolean);
  }

  function correctStructure() {
    const original = cloneTextbookParse({
      ...parse,
      motion_segments: parse.motion_segments ?? parse.segments ?? [],
    });
    const prepared = cloneTextbookParse(draft);
    const queriesById = new Map<string, any>((prepared.queries ?? []).map((item: any) => [item.query_id, item]));
    for (const candidate of prepared.interpretation_candidates ?? []) {
      const querySegments: string[] = candidate.query_ids
        .map((id: string) => queriesById.get(id)?.segment_id)
        .filter(Boolean);
      if (querySegments.length) candidate.target_segment_ids = Array.from(new Set<string>(querySegments));
    }
    const patch = buildTextbookCorrectionPatch(original, prepared);
    if (patch.operations.length) onCorrect(patch);
  }

  return (
    <Section label="앱이 이해한 문제">
      <p className="notice ok" role="status" aria-live="polite">
        {STATUS_LABELS[parse.status] ?? parse.status} · GPT는 구조만 만들고 답은 deterministic solver가 계산합니다.
      </p>
      <div className="two-col">
        <div>
          <p className="col-label">대상</p>
          <List items={(parse.entities ?? []).map((entity: any) => `${entity.label} (${entity.kind}, ${entity.entity_id})`)} />
        </div>
        <div>
          <p className="col-label">구할 값</p>
          <List items={(parse.queries ?? []).map((query: any) => `${query.output_key} · ${query.subject_id}${query.segment_id ? ` / ${query.segment_id}` : ''}`)} />
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        <p className="col-label">운동 구간</p>
        <ol aria-label="운동 구간 순서">
          {segments.map((segment: any) => (
            <li key={segment.segment_id}>
              <b>{segment.segment_id}</b> — {segment.motion_model_candidates.join(', ')} · {segment.relevance}
              <div className="empty">근거: “{segment.evidence_quote}”</div>
            </li>
          ))}
        </ol>
      </div>

      <div className="two-col" style={{ marginTop: 14 }}>
        <div>
          <p className="col-label">명시 조건</p>
          <List items={directFacts.map(factText)} />
        </div>
        <div>
          <p className="col-label">추론 조건</p>
          <List items={assumptions.map((item: any) => `${item.reason} (${item.proposed_value} ${item.proposed_unit})`)} />
        </div>
        <div>
          <p className="col-label">이번 계산에 직접 사용하지 않는 조건</p>
          <List items={contextFacts.map(factText)} />
        </div>
        <div>
          <p className="col-label">검증 경고</p>
          <List items={(parse.warnings ?? []).map((item: any) => `${item.code}: ${item.message}`)} />
        </div>
      </div>

      {canApprove ? (
        <div className="mini-actions">
          <button
            className="btn primary"
            disabled={loading}
            onClick={() => onApprove(parse.approval_fingerprint)}
          >
            이 해석으로 풀기
          </button>
          <span className="empty">조건 수정은 아래 ‘잘못 해석된 조건 직접 수정하기’를 이용하세요.</span>
        </div>
      ) : null}
      <details className="step" style={{ marginTop: 12 }}>
        <summary><span className="step-title">구조 조건 수정</span></summary>
        <p className="empty">수치·단위·원문 근거는 여기서 바꿀 수 없습니다. 아래 수정도 전체 schema와 물리 안전 gate를 다시 통과해야 합니다.</p>

        {(draft?.entities ?? []).map((entity: any, index: number) => (
          <div className="two-col" key={entity.entity_id} data-correction="entity">
            <label><span className="field-label">대상 이름 ({entity.entity_id})</span><input value={entity.label} onChange={(e) => setField('entities', index, 'label', e.target.value)} aria-label={`${entity.entity_id} 대상 이름`} /></label>
            <label><span className="field-label">대상 종류</span><input value={entity.kind} onChange={(e) => setField('entities', index, 'kind', e.target.value)} aria-label={`${entity.entity_id} 대상 종류`} /></label>
          </div>
        ))}

        {draftSegments.map((segment: any, index: number) => (
          <div className="two-col" key={segment.segment_id} data-correction="segment">
            <label><span className="field-label">구간 순서 ({segment.segment_id})</span><input type="number" min={1} max={8} value={segment.order} onChange={(e) => setField('motion_segments', index, 'order', Number(e.target.value))} aria-label={`${segment.segment_id} 구간 순서`} /></label>
            <label><span className="field-label">구간 대상 ID</span><input value={(segment.actor_ids ?? []).join(', ')} onChange={(e) => setField('motion_segments', index, 'actor_ids', csv(e.target.value))} aria-label={`${segment.segment_id} 구간 대상`} /></label>
            <label><span className="field-label">운동 모델</span><input value={(segment.motion_model_candidates ?? []).join(', ')} onChange={(e) => setField('motion_segments', index, 'motion_model_candidates', csv(e.target.value))} aria-label={`${segment.segment_id} 운동 모델`} /></label>
            <label><span className="field-label">구간 관련성</span><select value={segment.relevance} onChange={(e) => setField('motion_segments', index, 'relevance', e.target.value)} aria-label={`${segment.segment_id} 구간 관련성`}>{['target', 'required_context', 'context_only', 'unused'].map((value) => <option key={value}>{value}</option>)}</select></label>
            <label><span className="field-label">시작 사건</span><select value={segment.start_event_id ?? ''} onChange={(e) => setField('motion_segments', index, 'start_event_id', e.target.value || null)} aria-label={`${segment.segment_id} 시작 사건`}><option value="">없음</option>{eventIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
            <label><span className="field-label">종료 사건</span><select value={segment.end_event_id ?? ''} onChange={(e) => setField('motion_segments', index, 'end_event_id', e.target.value || null)} aria-label={`${segment.segment_id} 종료 사건`}><option value="">없음</option>{eventIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
          </div>
        ))}

        {(draft?.events ?? []).map((item: any, index: number) => (
          <div className="two-col" key={item.event_id} data-correction="event">
            <label><span className="field-label">사건 종류 ({item.event_id})</span><input value={item.kind} onChange={(e) => setField('events', index, 'kind', e.target.value)} aria-label={`${item.event_id} 사건 종류`} /></label>
            <label><span className="field-label">사건 대상 ID</span><input value={(item.subject_ids ?? []).join(', ')} onChange={(e) => setField('events', index, 'subject_ids', csv(e.target.value))} aria-label={`${item.event_id} 사건 대상`} /></label>
            <label><span className="field-label">사건 구간</span><select value={item.segment_id ?? ''} onChange={(e) => setField('events', index, 'segment_id', e.target.value || null)} aria-label={`${item.event_id} 사건 구간`}><option value="">없음</option>{segmentIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
          </div>
        ))}

        {(draft?.explicit_facts ?? []).map((item: any, index: number) => (
          <div className="two-col" key={item.fact_id} data-correction="fact-binding">
            <label><span className="field-label">조건 의미 ({item.fact_id})</span><input value={item.semantic_key} onChange={(e) => setField('explicit_facts', index, 'semantic_key', e.target.value)} aria-label={`${item.fact_id} 조건 의미`} /></label>
            <label><span className="field-label">조건 대상</span><select value={item.subject_id} onChange={(e) => setField('explicit_facts', index, 'subject_id', e.target.value)} aria-label={`${item.fact_id} 조건 대상`}>{entityIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
            <label><span className="field-label">조건 구간</span><select value={item.segment_id ?? ''} onChange={(e) => setField('explicit_facts', index, 'segment_id', e.target.value || null)} aria-label={`${item.fact_id} 조건 구간`}><option value="">없음</option>{segmentIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
            <label><span className="field-label">조건 사건</span><select value={item.event_id ?? ''} onChange={(e) => setField('explicit_facts', index, 'event_id', e.target.value || null)} aria-label={`${item.fact_id} 조건 사건`}><option value="">없음</option>{eventIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
            <label><span className="field-label">초기·최종 조건</span><input value={item.temporal_role} onChange={(e) => setField('explicit_facts', index, 'temporal_role', e.target.value)} aria-label={`${item.fact_id} 시간 역할`} /></label>
            <label><span className="field-label">방향</span><input value={item.direction} onChange={(e) => setField('explicit_facts', index, 'direction', e.target.value)} aria-label={`${item.fact_id} 방향`} /></label>
          </div>
        ))}

        {(draft?.relations ?? []).map((item: any, index: number) => (
          <div className="two-col" key={item.relation_id} data-correction="relation">
            <label><span className="field-label">관계 종류 ({item.relation_id})</span><input value={item.kind} onChange={(e) => setField('relations', index, 'kind', e.target.value)} aria-label={`${item.relation_id} 관계 종류`} /></label>
            <label><span className="field-label">관계 대상 ID</span><input value={(item.entity_ids ?? []).join(', ')} onChange={(e) => setField('relations', index, 'entity_ids', csv(e.target.value))} aria-label={`${item.relation_id} 관계 대상`} /></label>
            <label><span className="field-label">관계 구간</span><select value={item.segment_id ?? ''} onChange={(e) => setField('relations', index, 'segment_id', e.target.value || null)} aria-label={`${item.relation_id} 관계 구간`}><option value="">없음</option>{segmentIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
          </div>
        ))}

        {(draft?.queries ?? []).map((item: any, index: number) => (
          <div className="two-col" key={item.query_id} data-correction="query-binding">
            <label><span className="field-label">질문 물리량 ({item.query_id})</span><input value={item.output_key} onChange={(e) => setField('queries', index, 'output_key', e.target.value)} aria-label={`${item.query_id} 질문 물리량`} /></label>
            <label><span className="field-label">질문 대상</span><select value={item.subject_id} onChange={(e) => setField('queries', index, 'subject_id', e.target.value)} aria-label={`${item.query_id} 질문 대상`}>{entityIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
            <label><span className="field-label">질문 구간</span><select value={item.segment_id ?? ''} onChange={(e) => setField('queries', index, 'segment_id', e.target.value || null)} aria-label={`${item.query_id} 질문 구간`}><option value="">없음</option>{segmentIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
            <label><span className="field-label">질문 사건</span><select value={item.event_id ?? ''} onChange={(e) => setField('queries', index, 'event_id', e.target.value || null)} aria-label={`${item.query_id} 질문 사건`}><option value="">없음</option>{eventIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
            <label><span className="field-label">질문 방향 성분</span><input value={item.component} onChange={(e) => setField('queries', index, 'component', e.target.value)} aria-label={`${item.query_id} 질문 성분`} /></label>
          </div>
        ))}

        {(draft?.assumption_proposals ?? []).map((item: any, index: number) => (
          <div className="two-col" key={item.assumption_id} data-correction="initial-friction-condition">
            <label><span className="field-label">초기·마찰 가정 ({item.assumption_id})</span><input value={item.kind} onChange={(e) => setField('assumption_proposals', index, 'kind', e.target.value)} aria-label={`${item.assumption_id} 가정 종류`} /></label>
            <label><span className="field-label">가정 대상</span><select value={item.subject_id} onChange={(e) => setField('assumption_proposals', index, 'subject_id', e.target.value)} aria-label={`${item.assumption_id} 가정 대상`}>{entityIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
            <label><span className="field-label">가정 구간</span><select value={item.segment_id ?? ''} onChange={(e) => setField('assumption_proposals', index, 'segment_id', e.target.value || null)} aria-label={`${item.assumption_id} 가정 구간`}><option value="">없음</option>{segmentIds.map((id: string) => <option key={id}>{id}</option>)}</select></label>
            <label><span className="field-label">가정 의미</span><input value={item.proposed_semantic_key} onChange={(e) => setField('assumption_proposals', index, 'proposed_semantic_key', e.target.value)} aria-label={`${item.assumption_id} 가정 의미`} /></label>
          </div>
        ))}
        <div className="mini-actions">
          <button className="mini-btn" disabled={loading} onClick={correctStructure}>구조 수정 적용</button>
        </div>
      </details>
    </Section>
  );
}
