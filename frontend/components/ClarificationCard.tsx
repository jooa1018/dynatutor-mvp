'use client';

import { useState } from 'react';

// 값 입력이 필요한 선택지에 단위를 함께 표시한다. 예: 가속도 [   ] m/s²
const UNIT_LABELS: Record<string, string> = {
  deg: '°', '': '', 'm/s': 'm/s', 'm/s^2': 'm/s²', 'rad/s': 'rad/s', 'rad/s^2': 'rad/s²',
  m: 'm', kg: 'kg', N: 'N', 'N/m': 'N/m', s: 's', J: 'J', 'N*m': 'N·m', 'kg*m^2': 'kg·m²',
};

type ClarifyOption = {
  id: string;
  label: string;
  description?: string;
  patch: any;
  needs_value?: string | null;
};

type Props = {
  clarification: { question: string; why?: string | null; options: ClarifyOption[] };
  loading: boolean;
  onChoose: (patch: any) => void;
};

export default function ClarificationCard({ clarification, loading, onChoose }: Props) {
  const [values, setValues] = useState<Record<string, string>>({});

  return (
    <div className="clarify-card">
      <p className="clarify-q">{clarification.question}</p>
      {clarification.why ? <p className="step-body" style={{ marginLeft: 0 }}>{clarification.why}</p> : null}
      <div className="cards">
        {clarification.options.map((opt) => {
          const unitRaw = opt.patch?.set_known?.unit ?? '';
          const unit = UNIT_LABELS[unitRaw] ?? unitRaw;
          const raw = values[opt.id] ?? '';
          const invalid = !raw.trim() || Number.isNaN(Number(raw));
          return (
            <div className="ex clarify-opt" key={opt.id}>
              <b>{opt.label}</b>
              {opt.description ? <p>{opt.description}</p> : null}
              {opt.needs_value ? (
                <div className="token-row" style={{ marginTop: 9, alignItems: 'center' }}>
                  <input
                    type="text"
                    inputMode="decimal"
                    placeholder={`${opt.needs_value} 값`}
                    value={raw}
                    onChange={(e) => setValues({ ...values, [opt.id]: e.target.value })}
                    aria-label={`${opt.label} 값 입력${unit ? ` (단위 ${unit})` : ''}`}
                  />
                  {unit ? <span className="chip" aria-hidden="true">{unit}</span> : null}
                  <button
                    className="btn ghost"
                    disabled={loading || invalid}
                    onClick={() => onChoose({ ...opt.patch, set_known: { ...opt.patch.set_known, value: Number(raw) } })}
                  >이 값으로 풀기</button>
                </div>
              ) : (
                <div className="mini-actions">
                  <button className="mini-btn" disabled={loading} onClick={() => onChoose(opt.patch)}>이렇게 풀기</button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
