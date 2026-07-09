'use client';

// 지원 가능한 문제 유형 안내. solver 목록 하드코딩 대신 카테고리 요약으로 유지보수 부담을 줄인다.
const GROUPS: { title: string; items: string[] }[] = [
  { title: '입자 동역학', items: ['경사면 (마찰 유/무)', '도르래 (Atwood · 테이블 · 경사면 · 관성 있는 도르래)', '단일 질점 F=ma', '등가속도 직선운동'] },
  { title: '일 · 에너지 · 운동량', items: ['일 W=Fs·cosθ', '일-에너지 정리', '용수철 에너지/진동', '충격량-운동량', '1차원 충돌 (탄성 · 비탄성 · 반발계수)'] },
  { title: '회전 · 원운동', items: ['고정축 회전 (τ=Iα)', '순수 구름 에너지', '수직 원운동', '평면/경사 커브 주행'] },
  { title: '포물선 · 고급', items: ['포물선 운동 (높이 차 포함)', '극좌표 운동', '평면강체 속도/가속도', '회전좌표계 코리올리', '상대 가속도'] },
];

export default function SupportedTypesCard() {
  return (
    <details className="step" style={{ marginTop: 14 }}>
      <summary><span className="step-title">이 앱이 풀 수 있는 문제 유형 보기</span></summary>
      <div className="two-col" style={{ marginTop: 10 }}>
        {GROUPS.map((g) => (
          <div key={g.title}>
            <p className="col-label">{g.title}</p>
            <ul className="list">
              {g.items.map((it) => <li key={it}>{it}</li>)}
            </ul>
          </div>
        ))}
      </div>
      <p className="empty" style={{ marginTop: 10 }}>
        값이 빠졌거나 해석이 갈리는 문제는 실패 대신 선택지를 되물어봅니다. 자연어 문장(예: “정지해 있는 물체”, “힘 방향으로 5m 이동”)도 이해합니다.
      </p>
    </details>
  );
}
