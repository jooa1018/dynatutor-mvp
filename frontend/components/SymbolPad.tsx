'use client';

import { useState } from 'react';

// 문제 입력용 수학·물리 기호 팔레트.
// 키보드로 치기 어려운 기호를 탭 한 번으로 커서 위치에 삽입한다.
// 여기 있는 모든 표기는 백엔드 정규화기가 이해하는 것만 넣는다
// (θ→각도, ω₀→omega0, ²→^2 등 — test_phase39_usability가 왕복을 보증).

type Group = { name: string; items: { show: string; insert?: string; hint?: string }[] };

const GROUPS: Group[] = [
  {
    name: '기호',
    items: [
      { show: 'θ', hint: '각도' },
      { show: 'ω', hint: '각속도' },
      { show: 'α', hint: '각가속도' },
      { show: 'μ', hint: '마찰계수' },
      { show: 'τ', hint: '토크' },
      { show: 'Δ', hint: '변화량' },
      { show: '°', hint: '도' },
      { show: '²', hint: '제곱' },
      { show: '√', hint: '루트' },
      { show: '·', hint: '곱' },
      { show: '±' },
      { show: '→' },
    ],
  },
  {
    name: '표기',
    items: [
      { show: 'v₀=', hint: '초속도' },
      { show: 'ω₀=', hint: '초기 각속도' },
      { show: 'm₁=', hint: '질량 1' },
      { show: 'm₂=', hint: '질량 2' },
      { show: 'θ=' },
      { show: 'μ=' },
      { show: 'k=', hint: '용수철 상수' },
      { show: 'F=' },
      { show: 'I=', hint: '관성모멘트' },
      { show: 'e=', hint: '반발계수' },
    ],
  },
  {
    name: '단위',
    items: [
      { show: 'm/s' },
      { show: 'm/s²' },
      { show: 'rad/s' },
      { show: 'rad/s²' },
      { show: 'kg' },
      { show: 'N' },
      { show: 'N/m' },
      { show: 'N·m' },
      { show: 'kg·m²' },
      { show: 'J' },
      { show: 'cm' },
      { show: '초' },
    ],
  },
];

type Props = {
  // 대상 textarea를 찾아 커서 위치에 삽입한다.
  targetId: string;
  onInsert: (nextValue: string) => void;
};

export default function SymbolPad({ targetId, onInsert }: Props) {
  const [group, setGroup] = useState(0);

  function insert(token: string) {
    const el = document.getElementById(targetId) as HTMLTextAreaElement | null;
    if (!el) return;
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    // 단위는 숫자 뒤에 자연스럽게 붙도록, 기호/표기는 앞에 공백이 없으면 그대로.
    const next = el.value.slice(0, start) + token + el.value.slice(end);
    onInsert(next);
    // React 상태 반영 후 커서를 삽입 끝으로.
    requestAnimationFrame(() => {
      el.focus();
      const pos = start + token.length;
      el.setSelectionRange(pos, pos);
    });
  }

  return (
    <div className="symbolpad" aria-label="수학 기호 팔레트">
      <div className="symbolpad-tabs" role="tablist">
        {GROUPS.map((g, i) => (
          <button
            key={g.name}
            role="tab"
            aria-selected={i === group}
            className={i === group ? 'symbolpad-tab active' : 'symbolpad-tab'}
            onClick={() => setGroup(i)}
          >{g.name}</button>
        ))}
      </div>
      <div className="symbolpad-keys">
        {GROUPS[group].items.map((it) => (
          <button
            key={it.show}
            type="button"
            className="symbolpad-key"
            title={it.hint}
            aria-label={it.hint ? `${it.show} (${it.hint})` : it.show}
            onMouseDown={(e) => e.preventDefault() /* textarea 포커스 유지 */}
            onClick={() => insert(it.insert ?? it.show)}
          >{it.show}</button>
        ))}
      </div>
    </div>
  );
}
