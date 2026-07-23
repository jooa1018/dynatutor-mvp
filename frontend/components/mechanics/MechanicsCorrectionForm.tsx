'use client';

import { useMemo, useState } from 'react';
import type { ChangeEvent } from 'react';

import { mechanicsClientRequestId } from '../../lib/mechanicsMultimodal';
import type {
  FigureObservation,
  MechanicsMultimodalResponse,
  SourceCorrectionOperation,
} from '../../lib/mechanicsMultimodal';

type Props = Readonly<{
  response: MechanicsMultimodalResponse;
  disabled?: boolean;
  onApply: (operations: readonly SourceCorrectionOperation[]) => Promise<boolean>;
}>;

type JsonRecord = Record<string, unknown>;

function records(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.filter((item): item is JsonRecord => Boolean(item) && typeof item === 'object') : [];
}

function text(value: unknown): string {
  return value === null || value === undefined ? '' : String(value);
}

function operation(kind: string, payload: JsonRecord): SourceCorrectionOperation {
  return { kind, operation_id: mechanicsClientRequestId('operation'), ...payload };
}

export function MechanicsCorrectionForm({ response, disabled = false, onApply }: Props) {
  const draft = response.draft ?? {};
  const quantities = useMemo(() => records(draft.quantities), [draft]);
  const entities = useMemo(() => records(draft.entities), [draft]);
  const geometry = useMemo(() => records(draft.geometry), [draft]);
  const queries = useMemo(() => records(draft.queries), [draft]);
  const assumptions = useMemo(() => records(draft.assumptions), [draft]);
  const [queue, setQueue] = useState<readonly SourceCorrectionOperation[]>([]);
  const [quantityId, setQuantityId] = useState(text(quantities[0]?.quantity_id));
  const selectedQuantity = quantities.find((item) => text(item.quantity_id) === quantityId);
  const [rawValue, setRawValue] = useState(text(selectedQuantity?.raw_value));
  const [rawUnit, setRawUnit] = useState(text(selectedQuantity?.raw_unit));
  const [directionSign, setDirectionSign] = useState('1');
  const [observationId, setObservationId] = useState(text(response.observations[0]?.observation_id));
  const [entityId, setEntityId] = useState(text(entities[0]?.entity_id));
  const [relationId, setRelationId] = useState(text(geometry[0]?.relation_id));
  const selectedRelation = geometry.find((item) => text(item.relation_id) === relationId);
  const [relationKind, setRelationKind] = useState(text(selectedRelation?.kind));
  const [relationParticipants, setRelationParticipants] = useState('');
  const [queryId, setQueryId] = useState(text(queries[0]?.query_id));
  const selectedQuery = queries.find((item) => text(item.query_id) === queryId);
  const [querySubject, setQuerySubject] = useState(text((selectedQuery?.target as JsonRecord | undefined)?.subject_id));
  const [queryUnit, setQueryUnit] = useState(text(selectedQuery?.output_unit));
  const [applying, setApplying] = useState(false);

  function enqueue(next: SourceCorrectionOperation) {
    setQueue((current) => [...current, next]);
  }

  function chooseQuantity(nextId: string) {
    setQuantityId(nextId);
    const selected = quantities.find((item) => text(item.quantity_id) === nextId);
    setRawValue(text(selected?.raw_value));
    setRawUnit(text(selected?.raw_unit));
    const direction = selected?.direction as JsonRecord | undefined;
    setDirectionSign(text(direction?.sign || 1));
  }

  function chooseRelation(nextId: string) {
    setRelationId(nextId);
    const selected = geometry.find((item) => text(item.relation_id) === nextId);
    setRelationKind(text(selected?.kind));
    setRelationParticipants(Array.isArray(selected?.participant_ids) ? selected.participant_ids.map(text).join(', ') : '');
  }

  function chooseQuery(nextId: string) {
    setQueryId(nextId);
    const selected = queries.find((item) => text(item.query_id) === nextId);
    setQuerySubject(text((selected?.target as JsonRecord | undefined)?.subject_id));
    setQueryUnit(text(selected?.output_unit));
  }

  async function applyQueue() {
    if (!queue.length || applying || disabled) return;
    setApplying(true);
    try {
      if (await onApply(queue)) setQueue([]);
    } finally {
      setApplying(false);
    }
  }

  return (
    <section className="mechanics-correction" aria-labelledby="mechanics-correction-title">
      <h3 id="mechanics-correction-title">앱이 이해한 조건 수정</h3>
      <p>수정은 원문·그림 근거 계층만 바꾸며, 방정식·solver·root·검산·최종 답은 직접 수정할 수 없습니다.</p>

      {response.observations.length ? (
        <div className="mechanics-correction-group">
          <b>그림 근거 승인 또는 제외</b>
          {response.observations.map((item: FigureObservation) => {
            const evidenceId = text(item.evidence_id ?? item.observation_id);
            return (
              <div key={evidenceId} className="mechanics-correction-row">
                <span>{text(item.observed_label ?? item.observation_kind ?? evidenceId)}</span>
                <button type="button" className="mini-btn" disabled={disabled} onClick={() => enqueue(operation('accept_evidence', { evidence_id: evidenceId }))}>승인</button>
                <button type="button" className="mini-btn" disabled={disabled} onClick={() => enqueue(operation('reject_evidence', { evidence_id: evidenceId }))}>제외</button>
                {Array.isArray(item.alternatives) ? item.alternatives.map((alternative) => {
                  const alternativeRecord = alternative as JsonRecord;
                  return (
                    <button
                      type="button"
                      className="mini-btn"
                      key={text(alternativeRecord.alternative_id)}
                      disabled={disabled}
                      onClick={() => enqueue(operation('choose_alternative', {
                        observation_id: text(item.observation_id),
                        alternative_id: text(alternativeRecord.alternative_id),
                      }))}
                    >
                      대안 {text(alternativeRecord.alternative_id)}
                    </button>
                  );
                }) : null}
              </div>
            );
          })}
        </div>
      ) : null}

      {quantities.length ? (
        <fieldset className="mechanics-correction-group">
          <legend>수치·단위·방향</legend>
          <label>물리량
            <select value={quantityId} onChange={(event: ChangeEvent<HTMLSelectElement>) => chooseQuantity(event.target.value)} disabled={disabled}>
              {quantities.map((item) => <option key={text(item.quantity_id)} value={text(item.quantity_id)}>{text(item.role)} · {text(item.quantity_id)}</option>)}
            </select>
          </label>
          <label>값 <input value={rawValue} onChange={(event: ChangeEvent<HTMLInputElement>) => setRawValue(event.target.value)} disabled={disabled} /></label>
          <label>단위 <input value={rawUnit} onChange={(event: ChangeEvent<HTMLInputElement>) => setRawUnit(event.target.value)} disabled={disabled} /></label>
          <label>축 방향
            <select value={directionSign} onChange={(event: ChangeEvent<HTMLSelectElement>) => setDirectionSign(event.target.value)} disabled={disabled}>
              <option value="1">양의 방향</option><option value="-1">음의 방향</option>
            </select>
          </label>
          <div className="mini-actions">
            <button type="button" className="mini-btn" disabled={disabled || !quantityId || !rawValue || !rawUnit} onClick={() => enqueue(operation('replace_quantity_value', { quantity_id: quantityId, raw_value: rawValue, raw_unit: rawUnit }))}>값 수정 추가</button>
            <button type="button" className="mini-btn" disabled={disabled || !quantityId || !rawUnit} onClick={() => enqueue(operation('replace_unit', { quantity_id: quantityId, raw_unit: rawUnit }))}>단위 수정 추가</button>
            <button type="button" className="mini-btn" disabled={disabled || !quantityId} onClick={() => {
              const old = selectedQuantity?.direction as JsonRecord | undefined;
              enqueue(operation('replace_direction', { quantity_id: quantityId, direction: { kind: 'axis', frame_id: text(old?.frame_id), axis: text(old?.axis || 'x'), sign: Number(directionSign) } }));
            }}>방향 수정 추가</button>
          </div>
        </fieldset>
      ) : null}

      {response.observations.length && entities.length ? (
        <fieldset className="mechanics-correction-group">
          <legend>그림 라벨과 물체 연결</legend>
          <select aria-label="그림 관찰" value={observationId} onChange={(event: ChangeEvent<HTMLSelectElement>) => setObservationId(event.target.value)} disabled={disabled}>
            {response.observations.map((item) => <option key={text(item.observation_id)} value={text(item.observation_id)}>{text(item.observed_label ?? item.observation_id)}</option>)}
          </select>
          <select aria-label="대상 물체" value={entityId} onChange={(event: ChangeEvent<HTMLSelectElement>) => setEntityId(event.target.value)} disabled={disabled}>
            {entities.map((item) => <option key={text(item.entity_id)} value={text(item.entity_id)}>{text(item.label ?? item.entity_id)}</option>)}
          </select>
          <button type="button" className="mini-btn" disabled={disabled || !observationId || !entityId} onClick={() => enqueue(operation('bind_label_to_entity', { observation_id: observationId, entity_id: entityId }))}>연결 수정 추가</button>
        </fieldset>
      ) : null}

      {geometry.length ? (
        <fieldset className="mechanics-correction-group">
          <legend>관계 수정</legend>
          <select aria-label="관계" value={relationId} onChange={(event: ChangeEvent<HTMLSelectElement>) => chooseRelation(event.target.value)} disabled={disabled}>
            {geometry.map((item) => <option key={text(item.relation_id)} value={text(item.relation_id)}>{text(item.kind)} · {text(item.relation_id)}</option>)}
          </select>
          <input aria-label="관계 종류" value={relationKind} onChange={(event: ChangeEvent<HTMLInputElement>) => setRelationKind(event.target.value)} disabled={disabled} />
          <input aria-label="관계 참여 ID" value={relationParticipants} onChange={(event: ChangeEvent<HTMLInputElement>) => setRelationParticipants(event.target.value)} disabled={disabled} />
          <button type="button" className="mini-btn" disabled={disabled || !selectedRelation} onClick={() => {
            if (!selectedRelation) return;
            enqueue(operation('replace_relation', { relation: { ...selectedRelation, kind: relationKind, participant_ids: relationParticipants.split(',').map((item) => item.trim()).filter(Boolean) } }));
          }}>관계 수정 추가</button>
        </fieldset>
      ) : null}

      {queries.length ? (
        <fieldset className="mechanics-correction-group">
          <legend>구할 물리량 수정</legend>
          <select aria-label="질의" value={queryId} onChange={(event: ChangeEvent<HTMLSelectElement>) => chooseQuery(event.target.value)} disabled={disabled}>
            {queries.map((item) => <option key={text(item.query_id)} value={text(item.query_id)}>{text(item.query_id)}</option>)}
          </select>
          <input aria-label="질의 대상 물체" value={querySubject} onChange={(event: ChangeEvent<HTMLInputElement>) => setQuerySubject(event.target.value)} disabled={disabled} />
          <input aria-label="출력 단위" value={queryUnit} onChange={(event: ChangeEvent<HTMLInputElement>) => setQueryUnit(event.target.value)} disabled={disabled} />
          <button type="button" className="mini-btn" disabled={disabled || !selectedQuery} onClick={() => {
            if (!selectedQuery) return;
            const target = (selectedQuery.target as JsonRecord | undefined) ?? {};
            enqueue(operation('replace_query', { query: { ...selectedQuery, output_unit: queryUnit, target: { ...target, subject_id: querySubject } } }));
          }}>질의 수정 추가</button>
        </fieldset>
      ) : null}

      {assumptions.length ? (
        <fieldset className="mechanics-correction-group">
          <legend>가정 승인 또는 거부</legend>
          {assumptions.map((item) => (
            <div key={text(item.assumption_id)} className="mechanics-correction-row">
              <span>{text(item.reason ?? item.assumption_id)}</span>
              <button type="button" className="mini-btn" disabled={disabled} onClick={() => enqueue(operation('confirm_assumption', { assumption_id: text(item.assumption_id) }))}>승인</button>
              <button type="button" className="mini-btn" disabled={disabled} onClick={() => enqueue(operation('reject_assumption', { assumption_id: text(item.assumption_id) }))}>거부</button>
            </div>
          ))}
        </fieldset>
      ) : null}

      <div className="mechanics-correction-queue" aria-live="polite">
        <b>적용 대기 수정: {queue.length}개</b>
        {queue.length ? <ol>{queue.map((item) => <li key={item.operation_id}>{item.kind}</li>)}</ol> : null}
        <div className="mini-actions">
          <button type="button" className="btn primary" disabled={!queue.length || disabled || applying} onClick={applyQueue}>{applying ? '재검증 중…' : '수정 후 전체 재검증'}</button>
          <button type="button" className="btn ghost" disabled={!queue.length || disabled || applying} onClick={() => setQueue([])}>대기 수정 지우기</button>
        </div>
      </div>
    </section>
  );
}
