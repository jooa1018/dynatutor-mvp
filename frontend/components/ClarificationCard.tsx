'use client';

import { useState } from 'react';
import {
  buildClarifyPatch,
  canSubmitClarification,
  fieldValueKey,
} from '../lib/clarificationInputs';

const UNIT_LABELS: Record<string, string> = {
  deg: '°', '': '', 'm/s': 'm/s', 'm/s^2': 'm/s²', 'rad/s': 'rad/s', 'rad/s^2': 'rad/s²',
  m: 'm', kg: 'kg', N: 'N', 'N/m': 'N/m', s: 's', J: 'J', 'N*m': 'N·m', 'kg*m^2': 'kg·m²',
};

type ClarifyInputField = {
  symbol: string;
  label: string;
  unit: string;
  input_type?: string;
  required?: boolean;
};

type ClarifyOption = {
  id: string;
  label: string;
  description?: string;
  patch: Record<string, any>;
  needs_value?: string | null;
  input_fields?: ClarifyInputField[];
};

type Props = {
  clarification: { question: string; why?: string | null; options: ClarifyOption[] };
  loading: boolean;
  onChoose: (patch: any) => void;
};

function InputUnit({ unit }: { unit: string }) {
  const display = UNIT_LABELS[unit] ?? unit;
  return display ? <span className="chip" aria-hidden="true">{display}</span> : null;
}

export default function ClarificationCard({ clarification, loading, onChoose }: Props) {
  const [values, setValues] = useState<Record<string, string>>({});

  function updateValue(optionId: string, symbol: string, value: string) {
    setValues((current) => ({
      ...current,
      [fieldValueKey(optionId, symbol)]: value,
    }));
  }

  return (
    <div className="clarify-card">
      <p className="clarify-q">{clarification.question}</p>
      {clarification.why ? <p className="step-body" style={{ marginLeft: 0 }}>{clarification.why}</p> : null}
      <div className="cards">
        {clarification.options.map((opt) => {
          const fields = opt.input_fields ?? [];
          const valid = canSubmitClarification(opt, values);
          const legacySymbol = opt.needs_value ?? '';
          const legacyUnitRaw = opt.patch?.set_known?.unit ?? '';
          const legacyRaw = values[fieldValueKey(opt.id, legacySymbol)] ?? '';

          return (
            <div className="ex clarify-opt" key={opt.id}>
              <b>{opt.label}</b>
              {opt.description ? <p>{opt.description}</p> : null}

              {fields.length ? (
                <>
                  <div className="clarify-input-grid">
                    {fields.map((field) => {
                      const key = fieldValueKey(opt.id, field.symbol);
                      return (
                        <label className="clarify-input-field" key={field.symbol}>
                          <span>{field.label}</span>
                          <div className="token-row">
                            <input
                              type="text"
                              inputMode="decimal"
                              placeholder={`${field.symbol} 값`}
                              value={values[key] ?? ''}
                              onChange={(event) => updateValue(opt.id, field.symbol, event.target.value)}
                              aria-label={`${field.label} 입력 (단위 ${UNIT_LABELS[field.unit] ?? field.unit})`}
                            />
                            <InputUnit unit={field.unit} />
                          </div>
                        </label>
                      );
                    })}
                  </div>
                  <div className="mini-actions">
                    <button
                      className="btn ghost"
                      disabled={loading || !valid}
                      onClick={() => onChoose(buildClarifyPatch(opt, values))}
                    >입력한 성분으로 풀기</button>
                  </div>
                </>
              ) : opt.needs_value ? (
                <div className="token-row" style={{ marginTop: 9, alignItems: 'center' }}>
                  <input
                    type="text"
                    inputMode="decimal"
                    placeholder={`${opt.needs_value} 값`}
                    value={legacyRaw}
                    onChange={(event) => updateValue(opt.id, legacySymbol, event.target.value)}
                    aria-label={`${opt.label} 값 입력`}
                  />
                  <InputUnit unit={legacyUnitRaw} />
                  <button
                    className="btn ghost"
                    disabled={loading || !valid}
                    onClick={() => onChoose(buildClarifyPatch(opt, values))}
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
