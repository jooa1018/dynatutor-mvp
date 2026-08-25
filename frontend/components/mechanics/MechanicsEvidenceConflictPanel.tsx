'use client';

import type {
  EvidenceConfirmation,
  EvidenceConflict,
  FigureObservation,
} from '../../lib/mechanicsMultimodal';

type Props = Readonly<{
  conflicts: readonly EvidenceConflict[];
  observations: readonly FigureObservation[];
  confirmations: readonly EvidenceConfirmation[];
  onChange: (value: readonly EvidenceConfirmation[]) => void;
  disabled?: boolean;
}>;

function sourceSummary(sourceId: string, observations: readonly FigureObservation[]): string {
  const observation = observations.find((item) => item.evidence_id === sourceId || item.observation_id === sourceId);
  if (!observation) return sourceId.startsWith('text') ? `문제 문장 근거 · ${sourceId}` : `근거 · ${sourceId}`;
  const label = observation.observed_label ?? observation.observed_value ?? observation.observation_kind ?? sourceId;
  const source = observation.evidence_origin?.startsWith('FIGURE') ? '그림 근거' : '문제 문장 근거';
  return `${source} · ${String(label)}`;
}

export function MechanicsEvidenceConflictPanel({
  conflicts,
  observations,
  confirmations,
  onChange,
  disabled = false,
}: Props) {
  function choose(conflict: EvidenceConflict, candidateIndex: number) {
    const chosenSourceId = conflict.candidate_source_ids[candidateIndex];
    const chosenFingerprint = conflict.candidate_fingerprints[candidateIndex];
    if (!chosenSourceId || !chosenFingerprint) return;
    const next: EvidenceConfirmation = {
      conflict_id: conflict.conflict_id,
      conflict_fingerprint: conflict.fingerprint,
      chosen_source_id: chosenSourceId,
      chosen_candidate_fingerprint: chosenFingerprint,
    };
    onChange([
      ...confirmations.filter((item) => item.conflict_id !== conflict.conflict_id),
      next,
    ]);
  }

  if (!conflicts.length) return null;

  return (
    <section aria-labelledby="mechanics-evidence-conflicts" className="mechanics-conflicts">
      <div>
        <h3 id="mechanics-evidence-conflicts">글과 그림이 서로 다릅니다</h3>
        <p>
          신뢰도 점수로 자동 선택하지 않습니다. 문제에 실제로 적힌 근거를 확인해야 풀이를 계속할 수 있습니다.
        </p>
      </div>

      {conflicts.map((conflict, conflictIndex) => {
        const selected = confirmations.find((item) => item.conflict_id === conflict.conflict_id);
        return (
          <fieldset key={conflict.conflict_id} className="mechanics-conflict-card">
            <legend>충돌 {conflictIndex + 1}</legend>
            {conflict.candidate_source_ids.map((sourceId, index) => {
              const fingerprint = conflict.candidate_fingerprints[index];
              const checked = selected?.chosen_source_id === sourceId
                && selected?.chosen_candidate_fingerprint === fingerprint;
              return (
                <label key={`${sourceId}:${fingerprint}`} className="mechanics-conflict-option">
                  <input
                    type="radio"
                    name={`conflict-${conflict.conflict_id}`}
                    checked={checked}
                    disabled={disabled}
                    onChange={() => choose(conflict, index)}
                  />
                  <span>
                    <b>{sourceSummary(sourceId, observations)}</b>
                    <small>후보 {index + 1}</small>
                  </span>
                </label>
              );
            })}
          </fieldset>
        );
      })}
    </section>
  );
}
