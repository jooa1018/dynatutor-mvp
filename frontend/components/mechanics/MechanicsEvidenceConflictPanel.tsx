"use client";

import {
  EvidenceConfirmation,
  EvidenceConflict,
} from "../../lib/mechanicsMultimodal";

type Props = Readonly<{
  conflicts: readonly EvidenceConflict[];
  confirmations: readonly EvidenceConfirmation[];
  onChange: (value: readonly EvidenceConfirmation[]) => void;
  disabled?: boolean;
}>;

export function MechanicsEvidenceConflictPanel({
  conflicts,
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
      ...confirmations.filter(
        (item) => item.conflict_id !== conflict.conflict_id,
      ),
      next,
    ]);
  }

  if (!conflicts.length) return null;

  return (
    <section aria-labelledby="mechanics-evidence-conflicts" className="space-y-4">
      <div>
        <h3 id="mechanics-evidence-conflicts" className="font-semibold">
          글과 그림이 서로 다릅니다
        </h3>
        <p className="text-sm text-slate-600">
          신뢰도 점수로 자동 선택하지 않습니다. 각 항목에서 실제 문제와 맞는 근거를 직접 확인해 주세요.
        </p>
      </div>

      {conflicts.map((conflict, conflictIndex) => {
        const selected = confirmations.find(
          (item) => item.conflict_id === conflict.conflict_id,
        );
        return (
          <fieldset key={conflict.conflict_id} className="rounded-md border p-4">
            <legend className="px-1 text-sm font-semibold">
              충돌 {conflictIndex + 1}
            </legend>
            <div className="space-y-2">
              {conflict.candidate_source_ids.map((sourceId, index) => {
                const fingerprint = conflict.candidate_fingerprints[index];
                const checked =
                  selected?.chosen_source_id === sourceId &&
                  selected?.chosen_candidate_fingerprint === fingerprint;
                return (
                  <label
                    key={`${sourceId}:${fingerprint}`}
                    className="flex cursor-pointer items-start gap-2 rounded border p-3"
                  >
                    <input
                      type="radio"
                      name={`conflict-${conflict.conflict_id}`}
                      checked={checked}
                      disabled={disabled}
                      onChange={() => choose(conflict, index)}
                    />
                    <span>
                      <span className="block text-sm font-medium">근거 {index + 1}</span>
                      <span className="block break-all text-xs text-slate-500">
                        {sourceId}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        );
      })}
    </section>
  );
}
