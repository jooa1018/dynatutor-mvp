function beautify(expr: string) {
  return expr
    .replaceAll('theta_ddot', 'θ̈')
    .replaceAll('theta_dot', 'θ̇')
    .replaceAll('theta', 'θ')
    .replaceAll('omega', 'ω')
    .replaceAll('alpha', 'α')
    .replaceAll('sqrt', '√')
    .replaceAll('r_dot', 'ṙ')
    .replaceAll('r_ddot', 'r̈')
    .replaceAll('^2', '²')
    .replaceAll('^3', '³');
}

export function MathBlock({ items }: { items?: string[] }) {
  if (!items || items.length === 0) return <p className="empty">표시할 공식이 없습니다.</p>;
  return (
    <div className="chips">
      {items.map((item, i) => (
        <span className="chip" key={`${item}-${i}`}>{beautify(item)}</span>
      ))}
    </div>
  );
}
