'use client';

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function FinalAnswers({ data }: { data: any }) {
  const isVerified = Boolean(data?.ok && data?.verification?.passed);
  if (!isVerified) {
    return <p className="unsupported">{data?.unsupported_reason ?? '검증을 통과하지 못해 숫자 답을 표시하지 않습니다.'}</p>;
  }
  const answers = data?.answers ?? [];
  if (answers.length) {
    return (
      <div>
        {answers.map((ans: any, idx: number) => (
          <div className="ans-line" key={`${ans.symbol ?? ans.label ?? idx}-${idx}`}>
            <span className="ans-sym">{ans.symbol ?? '·'}</span>
            <span className="ans-val">{ans.display}</span>
          </div>
        ))}
      </div>
    );
  }
  if (data?.answer) {
    return (
      <div className="ans-line">
        <span className="ans-sym">·</span>
        <span className="ans-val">{data.answer.display}</span>
      </div>
    );
  }
  return <p className="unsupported">{data?.unsupported_reason}</p>;
}

export default function AnswerCard({ data, onSave }: { data: any; onSave: () => void }) {
  const isVerified = Boolean(data?.ok && data?.verification?.passed);
  const checks: string[] = data?.verification?.checks ?? [];
  const residualPassed = checks.some((item) => item.startsWith('역대입:') && item.endsWith('✓'));
  const verificationLabel = residualPassed
    ? '검증됨 · 차원·타당성·역대입 통과'
    : '검증됨 · 차원·타당성 통과 (역대입 미지원/생략)';
  return (
    <div className={data.ok ? 'answer-block' : 'answer-block failed'}>
      <div className="badge-line">
        {isVerified ? (
          <span className="verified"><CheckIcon />{verificationLabel}</span>
        ) : (
          <span className="verified bad">{data.ok ? '검증 경고 있음' : '풀이 보류'}</span>
        )}
        {isVerified ? <button className="mini-btn" onClick={onSave}>오답노트 저장</button> : null}
      </div>
      <FinalAnswers data={data} />
      <p className="ans-cap"><b>solver</b> {data.diagnosis?.selected_solver ?? '없음'} · <b>신뢰도</b> {data.diagnosis?.canonical?.confidence}</p>
    </div>
  );
}
