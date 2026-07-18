'use client';

import { useEffect, useState } from 'react';
import { Section, List } from '../Card';

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
  const [entityLabel, setEntityLabel] = useState('');
  const [querySegment, setQuerySegment] = useState('');
  useEffect(() => {
    setEntityLabel(parse?.entities?.[0]?.label ?? '');
    setQuerySegment(parse?.queries?.[0]?.segment_id ?? '');
  }, [parse]);
  if (!parse) return null;
  const segments = [...(parse.segments ?? [])].sort((a: any, b: any) => a.order - b.order);
  const directFacts = (parse.explicit_facts ?? []).filter((fact: any) => ['solver_input', 'constraint'].includes(fact.relevance));
  const contextFacts = (parse.explicit_facts ?? []).filter((fact: any) => ['context_only', 'unused'].includes(fact.relevance));
  const assumptions = parse.accepted_assumptions ?? [];
  const canApprove = parse.requires_approval && parse.approval_fingerprint && ['accepted', 'accepted_with_visible_assumptions'].includes(parse.status);

  function correctStructure() {
    const operations: any[] = [];
    const entity = parse.entities?.[0];
    const query = parse.queries?.[0];
    const candidate = parse.interpretation_candidates?.[0];
    if (entity && entityLabel && entityLabel !== entity.label) {
      operations.push({ collection: 'entities', id: entity.entity_id, set: { label: entityLabel } });
    }
    if (query && querySegment && querySegment !== query.segment_id) {
      operations.push({ collection: 'queries', id: query.query_id, set: { segment_id: querySegment } });
      if (candidate) operations.push({ collection: 'interpretation_candidates', id: candidate.candidate_id, set: { target_segment_ids: [querySegment] } });
    }
    if (operations.length) onCorrect({ operations });
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
        <div className="two-col" style={{ marginTop: 12 }}>
          <label>
            <span className="field-label">대상 이름</span>
            <input value={entityLabel} onChange={(event) => setEntityLabel(event.target.value)} aria-label="구조화 대상 이름" />
          </label>
          <label>
            <span className="field-label">질문 대상 운동 구간</span>
            <select value={querySegment} onChange={(event) => setQuerySegment(event.target.value)} aria-label="질문 대상 운동 구간">
              {segments.map((segment: any) => <option key={segment.segment_id} value={segment.segment_id}>{segment.segment_id}</option>)}
            </select>
          </label>
        </div>
        <div className="mini-actions">
          <button className="mini-btn" disabled={loading} onClick={correctStructure}>구조 수정 적용</button>
        </div>
      </details>
    </Section>
  );
}
