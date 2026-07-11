'use client';

import { List } from './Card';

// 기본 화면용 컴팩트 검산 요약: 통과/실패 한 줄 + 항목.
// 에러가 있으면 그것부터 보여준다.
export default function VerificationPanel({ verification, compact = false }: { verification: any; compact?: boolean }) {
  if (!verification) return null;
  const errors: string[] = verification.errors ?? [];
  const items = [verification.dimension_summary, ...(verification.checks ?? []), ...(verification.warnings ?? [])].filter(Boolean);
  const shown = compact ? items.slice(0, 3) : items;
  const residualPassed = items.some((item: string) => item.startsWith('역대입:') && item.endsWith('✓'));
  const residualSkipped = items.some((item: string) => item.includes('역대입 검산:') && (item.includes('미지원') || item.includes('생략')));
  const status = errors.length
    ? `검산 실패 ${errors.length}건`
    : residualPassed
      ? `검산 통과 · 독립 잔차 포함 · ${items.length}개 확인`
      : residualSkipped
        ? `기본 검증 통과 · 역대입 미지원/생략 · ${items.length}개 확인`
        : `기본 검증 통과 · ${items.length}개 확인`;
  return (
    <div>
      {compact && (
        <p className="col-label" style={{ marginBottom: 8 }}>
          {status}
        </p>
      )}
      <List items={shown} errorItems={errors} />
      {compact && items.length > shown.length ? (
        <p className="empty" style={{ marginTop: 6 }}>나머지 {items.length - shown.length}개는 아래 ‘자세히 보기’에 있습니다.</p>
      ) : null}
    </div>
  );
}
