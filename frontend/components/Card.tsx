import type { ReactNode } from 'react';

export function Section({ label, children, className = '' }: { label: string; children: ReactNode; className?: string }) {
  return (
    <section className={`section ${className}`.trim()}>
      <p className="eyebrow">{label}</p>
      {children}
    </section>
  );
}

export function List({ items, errorItems = [] }: { items?: string[]; errorItems?: string[] }) {
  const normal = items ?? [];
  if (!normal.length && !errorItems.length) return <p className="empty">표시할 항목이 없습니다.</p>;
  return (
    <ul className="list">
      {normal.map((x, i) => <li key={`n-${i}`}>{x}</li>)}
      {errorItems.map((x, i) => <li className="err" key={`e-${i}`}>{x}</li>)}
    </ul>
  );
}
