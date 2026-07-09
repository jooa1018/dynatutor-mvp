'use client';

import { Section, List } from './Card';
import { MathBlock } from './MathBlock';
import AnswerCard from './AnswerCard';
import VerificationPanel from './VerificationPanel';
import SafeSvg from './SafeSvg';

function KnownValues({ knowns }: { knowns: Record<string, any> }) {
  const entries = Object.entries(knowns ?? {}).filter(([k]) => k !== 'g');
  if (!entries.length) return <p className="empty">추출된 값이 아직 없습니다.</p>;
  return (
    <div className="chips">
      {entries.map(([key, q]) => <span className="chip" key={key}>{key} = {q.value} {q.unit ?? ''}</span>)}
    </div>
  );
}

function PhysicalModelView({ model }: { model: any }) {
  if (!model) return <p className="empty">물리 모델 정보가 없습니다.</p>;
  const bodies = model.bodies ?? [];
  const forces = model.forces ?? [];
  const constraints = model.constraints ?? [];
  return (
    <div>
      <dl className="kv">
        <dt>방정식 준비</dt><dd>{model.equations_ready ? '가능' : '추가 조건 필요'}</dd>
        <dt>모델 신뢰도</dt><dd>{model.model_confidence}</dd>
      </dl>
      <div className="two-col" style={{ marginTop: 14 }}>
        <div>
          <p className="col-label">물체</p>
          <List items={bodies.map((b: any) => `${b.id}: ${b.name} · ${b.role}${b.mass_value ? ` · ${b.mass_value}${b.mass_unit ?? ''}` : ''}${b.shape ? ` · ${b.shape}` : ''}`)} />
        </div>
        <div>
          <p className="col-label">힘</p>
          <List items={forces.slice(0, 8).map((f: any) => `${f.body_id}: ${f.symbol} ${f.direction}${f.magnitude_expr ? ` (${f.magnitude_expr})` : ''}`)} />
        </div>
        <div>
          <p className="col-label">제약조건</p>
          <List items={constraints.map((c: any) => `${c.kind}: ${c.equation ?? c.description}`)} />
        </div>
        <div>
          <p className="col-label">좌표축</p>
          <List items={Object.entries(model.coordinates?.positive_directions ?? {}).map(([k, v]) => `${k}: ${String(v)}`)} />
        </div>
      </div>
      {model.missing_info?.length ? <p className="unsupported" style={{ marginTop: 12 }}>추가 조건: {model.missing_info.join(', ')}</p> : null}
    </div>
  );
}

// 기본 화면: 최종 답 → 핵심 개념 → 풀이 3단계 → 검산 요약 → 자주 하는 실수 1개.
// 나머지 정보는 전부 "자세히 보기" 아래로 접는다.
export default function SolveResult({ data, feedback, onSave }: { data: any; feedback: any; onSave: () => void }) {
  const steps: any[] = data.steps ?? [];
  const coreSteps = steps.slice(0, 3);
  const restSteps = steps.slice(3);
  const firstMistake: string | undefined = (data.common_mistakes ?? [])[0];
  // 물리 모델은 response.physical_model(패치 반영본)을 우선 사용한다.
  const physicalModel = data.physical_model ?? data.diagnosis?.physical_model;

  return (
    <>
      <AnswerCard data={data} onSave={onSave} />

      {data.concept_summary ? (
        <Section label="핵심 개념" className="tight">
          <p className="step-body" style={{ margin: 0 }}>{data.concept_summary}</p>
        </Section>
      ) : null}

      <Section label={restSteps.length ? `풀이 (핵심 ${coreSteps.length}단계)` : '풀이'}>
        {coreSteps.length ? coreSteps.map((s: any, i: number) => (
          <details className="step" key={i} open={i < 2}>
            <summary><span className="step-num">{i + 1}</span><span className="step-title">{s.title}</span></summary>
            <p className="step-body">{s.body}</p>
            {s.math && <code className="math">{s.math}</code>}
          </details>
        )) : <p className="empty">계산 단계가 아직 없습니다.</p>}
      </Section>

      <Section label="검산">
        <VerificationPanel verification={data.verification} compact />
      </Section>

      {firstMistake ? (
        <Section label="자주 하는 실수" className="tight">
          <List items={[firstMistake]} />
        </Section>
      ) : null}

      <details className="step" style={{ marginTop: 18 }}>
        <summary><span className="step-title">자세히 보기 — 전체 풀이 · 물리 모델 · 자유물체도 · 공식</span></summary>
        <div style={{ marginTop: 6 }}>
          {restSteps.length ? (
            <Section label={`나머지 풀이 단계 (${restSteps.length})`}>
              {restSteps.map((s: any, i: number) => (
                <details className="step" key={i}>
                  <summary><span className="step-num">{coreSteps.length + i + 1}</span><span className="step-title">{s.title}</span></summary>
                  <p className="step-body">{s.body}</p>
                  {s.math && <code className="math">{s.math}</code>}
                </details>
              ))}
            </Section>
          ) : null}

          <Section label="개념 · 공식">
            <MathBlock items={data.equation_sheet ?? data.diagnosis?.applicable_equations} />
          </Section>

          <Section label="문제 구조">
            <dl className="kv">
              <dt>유형</dt><dd>{data.diagnosis?.canonical?.system_type}</dd>
              <dt>세부</dt><dd>{data.diagnosis?.canonical?.subtype ?? '-'}</dd>
            </dl>
            <KnownValues knowns={data.diagnosis?.canonical?.knowns ?? {}} />
          </Section>

          <Section label="식 선택">
            <div className="two-col">
              <div>
                <p className="col-label">사용할 식</p>
                <List items={data.diagnosis?.applicable_equations} />
              </div>
              <div>
                <p className="col-label no">쓰면 안 되는 식</p>
                <List items={data.diagnosis?.not_applicable_equations} />
              </div>
            </div>
          </Section>

          <Section label="물리 모델">
            <PhysicalModelView model={physicalModel} />
          </Section>

          <Section label="자유물체도">
            <SafeSvg svg={data.diagnosis?.fbd_diagram_svg} />
            <List items={data.diagnosis?.fbd_annotations} />
          </Section>

          <Section label="요약">
            <List items={data.teacher_summary} />
          </Section>

          {(data.common_mistakes ?? []).length > 1 ? (
            <Section label="자주 하는 실수 (전체)">
              <List items={data.common_mistakes} />
            </Section>
          ) : null}

          <Section label="복습 팁">
            <List items={data.study_tips} />
          </Section>
        </div>
      </details>

      {feedback && (
        <Section label="내 풀이 피드백">
          <div className="two-col">
            <div><p className="col-label">좋은 점</p><List items={feedback.good_points} /></div>
            <div><p className="col-label no">빠진 점</p><List items={feedback.missing_points} /></div>
            <div><p className="col-label no">오개념</p><List items={feedback.misconceptions} /></div>
            <div><p className="col-label">수정 순서</p><List items={feedback.corrected_steps} /></div>
          </div>
        </Section>
      )}
    </>
  );
}
