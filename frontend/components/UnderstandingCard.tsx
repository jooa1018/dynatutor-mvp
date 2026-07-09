'use client';

import { useEffect, useMemo, useState } from 'react';
import { Section, List } from './Card';

const UNIT_HINTS: Record<string, string> = {
  m: 'kg', m1: 'kg', m2: 'kg', F: 'N', s: 'm', x: 'm', h: 'm', h0: 'm', yf: 'm',
  v: 'm/s', v0: 'm/s', v1: 'm/s', v2: 'm/s', vf: 'm/s', a: 'm/s^2', t: 's',
  theta: 'deg', mu: '', mu_k: '', mu_s: '', k: 'N/m', R: 'm', r: 'm', omega: 'rad/s', alpha: 'rad/s^2',
  tau: 'N*m', I: 'kg*m^2', W: 'J', e: '', vA: 'm/s', vB: 'm/s', aA: 'm/s^2', aB: 'm/s^2',
};

const LABELS: Record<string, string> = {
  m: '질량 m', m1: '질량 m1', m2: '질량 m2', F: '힘 F', s: '이동거리/변위 s', x: '변형량 x', h: '높이 h',
  v: '속도 v', v0: '초속도 v0', v1: '충돌 전 속도 v1', v2: '충돌 전 속도 v2', vf: '최종속도 vf',
  a: '가속도 a', t: '시간 t', theta: '각도 θ', mu: '마찰계수 μ', mu_k: '운동마찰계수 μk', mu_s: '정지마찰계수 μs',
  k: '스프링 상수 k', R: '반지름 R', r: '거리 r', omega: '각속도 ω', alpha: '각가속도 α', tau: '토크 τ', I: '관성모멘트 I', W: '일 W', e: '반발계수 e',
};

const OUTPUTS = [
  ['acceleration', '가속도'], ['tension', '장력'], ['final_velocity', '최종 속도'], ['distance', '이동거리/변위'],
  ['time', '시간'], ['work', '일'], ['force', '힘'], ['range', '사거리'], ['max_height', '최대높이'],
  ['post_collision_velocity', '충돌 후 속도'], ['angular_velocity', '각속도'], ['angular_acceleration', '각가속도'],
  ['friction_force', '마찰력'], ['normal_force', '수직항력'], ['elastic_energy', '탄성 에너지'],
  ['initial_velocity', '초속도'], ['mass', '질량'], ['kinetic_energy', '운동에너지'], ['potential_energy', '위치에너지'],
  ['v1_after', '충돌 후 v1'], ['v2_after', '충돌 후 v2'], ['tangential_velocity', '접선 속도'], ['centripetal_acceleration', '구심 가속도'],
];

function systemLabel(st?: string) {
  const map: Record<string, string> = {
    pulley_table_hanging: '수평 테이블 + 매달린 물체', pulley_atwood: '양쪽 매달린 도르래', pulley_incline_hanging: '경사면 + 매달린 물체',
    particle_on_incline: '경사면 위 물체', constant_force_work: '일-힘-변위', constant_acceleration_1d: '등가속도 직선운동',
    collision_1d: '1차원 충돌', projectile_motion: '포물선 운동', plane_rigid_body_velocity: '평면강체 속도',
  };
  return map[st ?? ''] ?? st ?? '확인 필요';
}

function frictionLabel(ft?: string | null, flags?: Record<string, boolean>) {
  if (ft === 'none' || flags?.no_friction) return '마찰 없음';
  if (ft === 'kinetic') return '운동마찰 있음';
  if (ft === 'static') return '정지마찰 있음';
  if (ft === 'unspecified') return '마찰 있음(종류 미지정)';
  return '확인 필요';
}

type Row = { symbol: string; label: string; value: string; unit: string; removed?: boolean };

export default function UnderstandingCard({ data, loading, onApply }: { data: any; loading: boolean; onApply: (patch: any) => void }) {
  const canonical = data?.diagnosis?.canonical ?? {};
  const knowns = canonical.knowns ?? {};
  const [rows, setRows] = useState<Row[]>([]);
  const [requested, setRequested] = useState<string[]>([]);
  const [frictionType, setFrictionType] = useState<string>('');

  useEffect(() => {
    setRows(Object.entries(knowns)
      .filter(([symbol]) => symbol !== 'g')
      .map(([symbol, q]: [string, any]) => ({
        symbol,
        label: LABELS[symbol] ?? symbol,
        value: q?.value ?? '',
        unit: q?.unit ?? UNIT_HINTS[symbol] ?? '',
      })));
    setRequested(canonical.requested_outputs ?? []);
    setFrictionType(canonical.friction_type ?? (canonical.flags?.no_friction ? 'none' : ''));
  }, [data]);

  const readable = useMemo(() => {
    const items = [
      `구조: ${systemLabel(canonical.system_type)}`,
      `마찰: ${frictionLabel(canonical.friction_type, canonical.flags)}`,
      `구할 것: ${(canonical.requested_outputs ?? []).map((x: string) => OUTPUTS.find(([id]) => id === x)?.[1] ?? x).join(', ') || '자동 판단'}`,
    ];
    if ((canonical.missing_info ?? []).length) items.push(`확인 필요: ${canonical.missing_info.join(', ')}`);
    return items;
  }, [data]);

  function updateRow(i: number, patch: Partial<Row>) {
    const next = [...rows];
    next[i] = { ...next[i], ...patch };
    setRows(next);
  }

  // Phase 41: 추출되지 않은 물리량을 사용자가 직접 추가 (예: 누락된 v2=0)
  const [addSymbol, setAddSymbol] = useState('');
  const addable = Object.keys(LABELS).filter((sym) => !rows.some((r) => r.symbol === sym));

  function addRow() {
    if (!addSymbol || rows.some((r) => r.symbol === addSymbol)) return;
    setRows([...rows, {
      symbol: addSymbol,
      label: LABELS[addSymbol] ?? addSymbol,
      value: '',
      unit: UNIT_HINTS[addSymbol] ?? '',
    }]);
    setAddSymbol('');
  }

  function toggleOutput(id: string) {
    setRequested((cur) => cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);
  }

  function apply() {
    const set_knowns = rows
      .filter((r) => !r.removed && r.value !== '' && !Number.isNaN(Number(r.value)))
      .map((r) => ({ symbol: r.symbol, value: Number(r.value), unit: r.unit, label: r.label }));
    const remove_knowns = rows.filter((r) => r.removed).map((r) => r.symbol);
    const patch: any = { set_knowns, remove_knowns, requested_outputs: requested };
    if (frictionType) patch.friction_type = frictionType;
    onApply(patch);
  }

  return (
    <Section label="앱이 이해한 조건">
      <List items={readable} />
      <details className="step" style={{ marginTop: 12 }}>
        <summary><span className="step-title">잘못 해석된 조건 직접 수정하기</span></summary>
        <div className="cards" style={{ marginTop: 12 }}>
          {rows.map((r, i) => (
            <div className="ex" key={r.symbol}>
              <div className="token-row" style={{ alignItems: 'center' }}>
                <label className="field-label" style={{ minWidth: 92, margin: 0 }}>{r.label}</label>
                <input type="text" inputMode="decimal" value={r.value} disabled={r.removed} onChange={(e) => updateRow(i, { value: e.target.value })} />
                <input type="text" value={r.unit} disabled={r.removed} onChange={(e) => updateRow(i, { unit: e.target.value })} aria-label={`${r.label} 단위`} />
                <button className="mini-btn" onClick={() => updateRow(i, { removed: !r.removed })}>{r.removed ? '되살리기' : '제거'}</button>
              </div>
            </div>
          ))}
        </div>

        <div className="token-row" style={{ marginTop: 12, alignItems: 'center' }}>
          <select className="select" value={addSymbol} onChange={(e) => setAddSymbol(e.target.value)} aria-label="추가할 물리량 선택">
            <option value="">누락된 값 추가…</option>
            {addable.map((sym) => <option key={sym} value={sym}>{LABELS[sym]}</option>)}
          </select>
          <button className="mini-btn" onClick={addRow} disabled={!addSymbol}>추가</button>
        </div>

        <div style={{ marginTop: 14 }}>
          <p className="col-label">마찰 조건</p>
          <select className="select" value={frictionType} onChange={(e) => setFrictionType(e.target.value)}>
            <option value="">확인 필요/원문 유지</option>
            <option value="none">마찰 없음</option>
            <option value="kinetic">운동마찰 있음</option>
            <option value="static">정지마찰 있음</option>
            <option value="unspecified">마찰 있음(종류 미지정)</option>
          </select>
        </div>

        <div style={{ marginTop: 14 }}>
          <p className="col-label">구할 것</p>
          <div className="chips">
            {OUTPUTS.map(([id, label]) => (
              <label className="chip" key={id} style={{ cursor: 'pointer' }}>
                <input type="checkbox" checked={requested.includes(id)} onChange={() => toggleOutput(id)} /> {label}
              </label>
            ))}
          </div>
        </div>

        <div className="mini-actions">
          <button className="btn primary" disabled={loading} onClick={apply}>수정한 조건으로 다시 풀기</button>
        </div>
      </details>
    </Section>
  );
}
