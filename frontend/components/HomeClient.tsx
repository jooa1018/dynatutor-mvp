'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  aiExplain, ApiAuthError, feedbackProblem, getLLMStatus, getPracticeSet,
  getRecordStats, getStudyDashboard, listExamples, listRecords, markRecordReview,
  patchRecord, saveLocalRecord, saveRecord, solveProblem, listLocalRecords,
  reviewLocalRecord, toggleLocalFavorite, deleteLocalRecord, deleteRecord,
} from '../lib/api';
import { Section, List } from './Card';
import ClarificationCard from './ClarificationCard';
import NotebookPanel, { RecordCard } from './NotebookPanel';
import SolveResult from './SolveResult';
import SupportedTypesCard from './SupportedTypesCard';
import TokenSettings from './TokenSettings';
import SymbolPad from './SymbolPad';
import UnderstandingCard from './UnderstandingCard';
import ProblemUnderstandingCard from './understanding/ProblemUnderstandingCard';
import { buildRevisionApprovalPatch } from '../lib/textbookCorrections';

type ExampleProblem = {
  id: string;
  title: string;
  category: string;
  difficulty: string;
  problem_text: string;
  learning_goal: string;
  tags: string[];
  expected_solver: string;
};

type ViewKey = 'solve' | 'study' | 'examples' | 'notebook';

const VIEWS: { key: ViewKey; label: string }[] = [
  { key: 'solve', label: '풀기' },
  { key: 'study', label: '복습' },
  { key: 'examples', label: '예제' },
  { key: 'notebook', label: '오답노트' },
];

const fallbackExamples: ExampleProblem[] = [
  {
    id: 'fallback-incline',
    title: '마찰 없는 경사면',
    category: '입자 동역학',
    difficulty: '입문',
    problem_text: '질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.',
    learning_goal: '경사면 방향 중력 성분을 연습합니다.',
    tags: ['경사면', 'F=ma'],
    expected_solver: 'incline_no_friction',
  },
];

export default function HomeClient() {
  const [view, setView] = useState<ViewKey>('solve');
  const [examples, setExamples] = useState<ExampleProblem[]>(fallbackExamples);
  const [category, setCategory] = useState('전체');
  const [text, setText] = useState(fallbackExamples[0].problem_text);
  const [student, setStudent] = useState('');
  const [data, setData] = useState<any>(null);
  const [feedback, setFeedback] = useState<any>(null);
  const [records, setRecords] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [llmStatus, setLlmStatus] = useState<any>(null);
  const [study, setStudy] = useState<any>(null);
  const [practiceSet, setPracticeSet] = useState<any>(null);
  const [aiExplanation, setAiExplanation] = useState<any>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [tokenModal, setTokenModal] = useState(false);
  const [wakeMessage, setWakeMessage] = useState('');
  const [textbookCorrection, setTextbookCorrection] = useState<any>(null);

  // 401 응답은 어디서 나든 토큰 안내 모달로 이어진다.
  function handleError(e: any, fallbackMsg: string) {
    if (e instanceof ApiAuthError || e?.name === 'ApiAuthError') {
      setTokenModal(true);
      setError(e.message);
      return;
    }
    setError(`${e?.message ?? fallbackMsg} 백엔드 서버 주소, 토큰, Render cold start, CORS 설정을 확인하세요.`);
  }

  useEffect(() => {
    listExamples().then((out) => {
      if (out.examples?.length) {
        setExamples(out.examples);
        setText(out.examples[0].problem_text);
      }
    }).catch(() => {});
    refreshNotebook();
    refreshStudy();
    getLLMStatus().then(setLlmStatus).catch(() => {});
    getPracticeSet('개인 학습 드릴', '전체', 6).then(setPracticeSet).catch(() => {});
  }, []);

  const categories = useMemo(() => ['전체', ...Array.from(new Set(examples.map((e) => e.category)))], [examples]);
  const filteredExamples = category === '전체' ? examples : examples.filter((e) => e.category === category);
  const backendConnected = Boolean(stats) || Boolean(llmStatus) || Boolean(study);

  async function run(problemOverride?: string, clarifyPatch?: any, canonicalPatch?: any) {
    const problem = problemOverride ?? text;
    setView('solve');
    setLoading(true);
    setError('');
    setToast('');
    setWakeMessage('');
    const wakeTimer = window.setTimeout(() => {
      setWakeMessage('서버를 깨우는 중입니다. 무료 Render 서버라 첫 요청은 조금 걸릴 수 있습니다. 자동으로 다시 시도하고 있어요.');
    }, 2500);
    if (canonicalPatch?.textbook_parse_correction) {
      setTextbookCorrection(canonicalPatch.textbook_parse_correction);
    } else if (!canonicalPatch?.textbook_parse_approval) {
      setTextbookCorrection(null);
    }
    try {
      const out = await solveProblem(problem, student, clarifyPatch ?? null, canonicalPatch ?? null);
      setText(problem);
      setData(out);
      setAiExplanation(null);
      if (student.trim()) setFeedback(await feedbackProblem(problem, student));
      else setFeedback(null);
    } catch (e: any) {
      handleError(e, '오류가 발생했습니다.');
    } finally {
      window.clearTimeout(wakeTimer);
      setWakeMessage('');
      setLoading(false);
    }
  }


  async function runAIExplanation(forceTemplate = false) {
    if (!text.trim()) return;
    setAiLoading(true);
    setToast('');
    setError('');
    try {
      const out = await aiExplain(text, student, forceTemplate);
      setAiExplanation(out);
      if (!out.used_llm) setToast('LLM 대신 안전 템플릿 설명을 표시했습니다.');
    } catch (e: any) {
      handleError(e, 'AI 설명 생성 중 오류가 발생했습니다.');
    } finally {
      setAiLoading(false);
    }
  }

  async function save() {
    if (!data) return;
    if (!data.ok || !data.verification?.passed) {
      setToast('검증을 통과한 풀이만 오답노트에 저장할 수 있습니다.');
      return;
    }
    const payload = {
      problem_text: text,
      student_solution: student || null,
      solver: data.diagnosis?.selected_solver,
      answer_display: data.answers?.length ? data.answers.map((a: any) => a.display).join(' / ') : data.answer?.display ?? data.unsupported_reason,
      problem_type: data.diagnosis?.canonical?.system_type,
      tags: [data.diagnosis?.canonical?.system_type, data.diagnosis?.selected_solver, 'local-study'].filter(Boolean),
      raw_result: data,
      difficulty: data.diagnosis?.canonical?.system_type?.includes('coriolis') || data.diagnosis?.canonical?.system_type?.includes('rigid') ? '상급' : '미지정',
      source: 'engine',
    };
    try {
      const record = await saveRecord(payload);
      setToast(`오답노트에 저장했습니다. #${record.id}`);
      await refreshNotebook();
      await refreshStudy();
    } catch (e: any) {
      const local = saveLocalRecord(payload);
      if (local) {
        setRecords([local, ...listLocalRecords().filter((r: any) => r.id !== local.id)]);
        setToast('서버 DB 저장은 실패했지만 이 브라우저 localStorage에 임시 저장했습니다. 중요한 기록은 export로 백업하세요.');
      }
      handleError(e, '저장에 실패했습니다.');
    }
  }


  async function refreshStudy() {
    try { setStudy(await getStudyDashboard()); } catch {}
  }

  async function refreshNotebook() {
    try {
      const [recordOut, statOut] = await Promise.all([listRecords(), getRecordStats()]);
      setRecords([...(recordOut.records ?? []), ...listLocalRecords()]);
      setStats(statOut);
    } catch (e: any) {
      setRecords(listLocalRecords());
      handleError(e, '오답노트/API 연결에 실패했습니다. 원격 모드라면 개인용 접근 토큰을 확인하세요.');
    }
  }

  async function reviewRecord(id: number, correct: boolean) {
    // local_only 기록(음수 id)은 서버 API 대신 localStorage에서 처리한다 (Phase 40).
    if (id < 0) {
      reviewLocalRecord(id, correct);
      setToast(correct ? '복습 결과: 정답으로 기록했습니다. (이 기기 저장)' : '복습 결과: 다시 볼 문제로 기록했습니다. (이 기기 저장)');
      await refreshNotebook();
      return;
    }
    try {
      await markRecordReview(id, correct);
      setToast(correct ? '복습 결과: 정답으로 기록했습니다.' : '복습 결과: 다시 볼 문제로 기록했습니다.');
      await refreshNotebook();
      await refreshStudy();
    } catch (e: any) {
      handleError(e, '복습 기록에 실패했습니다.');
    }
  }

  async function toggleFavorite(record: any) {
    if (record.local_only || record.id < 0) {
      toggleLocalFavorite(record.id);
      await refreshNotebook();
      return;
    }
    try {
      await patchRecord(record.id, { favorite: !record.favorite });
      await refreshNotebook();
      await refreshStudy();
    } catch (e: any) {
      handleError(e, '즐겨찾기 변경에 실패했습니다.');
    }
  }

  async function removeRecord(record: any) {
    if (record.local_only || record.id < 0) {
      deleteLocalRecord(record.id);
      setToast('이 기기에 저장된 기록을 삭제했습니다.');
      await refreshNotebook();
      return;
    }
    try {
      await deleteRecord(record.id);
      setToast(`기록 #${record.id}을 삭제했습니다.`);
      await refreshNotebook();
      await refreshStudy();
    } catch (e: any) {
      handleError(e, '기록 삭제에 실패했습니다.');
    }
  }

  async function loadPractice(practiceCategory = '개인 학습 드릴', difficulty = '전체') {
    try { setPracticeSet(await getPracticeSet(practiceCategory, difficulty, 6)); } catch (e: any) { handleError(e, '연습 세트를 불러오지 못했습니다.'); }
  }

  return (
    <div className="app">
      {tokenModal && (
        <TokenSettings
          asModal
          message="원격 백엔드가 개인용 접근 토큰을 요구합니다 (401). 서버에 설정한 DYNATUTOR_ACCESS_TOKEN 값을 입력하면 이 기기에 저장됩니다."
          onSaved={() => { setTokenModal(false); setError(''); refreshNotebook(); refreshStudy(); }}
          onClose={() => setTokenModal(false)}
        />
      )}

      <header className="topbar">
        <div className="wordmark">Dyna<b>Tutor</b></div>
        <div className="status">
          <span className="pill"><span className={backendConnected ? 'dot' : 'dot off'}></span>{backendConnected ? '백엔드 연결됨' : '백엔드 확인 중'}</span>
          <span className="pill"><span className={llmStatus?.enabled ? 'dot' : 'dot off'}></span>LLM {llmStatus?.enabled ? 'ON' : 'OFF'}</span>
        </div>
      </header>

      <div className="segwrap">
        <nav className="seg" aria-label="화면 전환">
          {VIEWS.map((v) => (
            <button key={v.key} className={view === v.key ? 'active' : ''} onClick={() => setView(v.key)}>{v.label}</button>
          ))}
        </nav>
      </div>

      <main>
        {view === 'solve' && (
          <section>
            <label className="field-label" htmlFor="problem-input">문제 <i>(Ctrl+Enter로 바로 풀기)</i></label>
            <textarea
              id="problem-input"
              className="main"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !loading) {
                  e.preventDefault();
                  run();
                }
              }}
            />
            <SymbolPad targetId="problem-input" onInsert={setText} />

            <div className="row-gap">
              <label className="field-label" htmlFor="student-input">내 풀이 <i>(선택)</i></label>
              <textarea id="student-input" className="mini" placeholder="예: mg = ma 라서 a = g 라고 생각했습니다" value={student} onChange={(e) => setStudent(e.target.value)} />
            </div>

            <div className="actions">
              <button className="btn primary" onClick={() => run()} disabled={loading}>{loading ? '푸는 중…' : '문제 풀기'}</button>
              <button className="btn ghost" onClick={() => runAIExplanation(false)} disabled={aiLoading}>{aiLoading ? '설명 생성 중…' : 'AI 설명'}</button>
            </div>

            <SupportedTypesCard />

            <p className="notice ok">무료 배포 모드에서는 서버 재시작/재배포 시 오답노트·복습 기록이 사라질 수 있습니다. 중요한 기록은 export로 백업하고, 서버 저장 실패 시 이 브라우저에 임시 기록을 남깁니다.</p>
            {wakeMessage && <p className="notice ok">{wakeMessage}</p>}
            {error && <p className="notice err">{error}</p>}
            {toast && <p className="notice ok">{toast}</p>}

            {data && (
              <ProblemUnderstandingCard
                parse={data.textbook_parse}
                loading={loading}
                onApprove={(fingerprint) => run(text, null, buildRevisionApprovalPatch(fingerprint, textbookCorrection))}
                onCorrect={(correction) => {
                  setTextbookCorrection(correction);
                  return run(text, null, { textbook_parse_correction: correction });
                }}
              />
            )}

            {data && (
              <UnderstandingCard
                data={data}
                loading={loading}
                onApply={(patch) => run(text, null, patch)}
              />
            )}

            {data?.clarification && (
              <ClarificationCard
                clarification={data.clarification}
                loading={loading}
                onChoose={(patch) => run(text, patch)}
              />
            )}

            {data && <SolveResult data={data} feedback={feedback} onSave={save} />}

            {aiExplanation && (
              <Section label="AI 설명">
                <div className="ai-meta">
                  <span className="chip">{aiExplanation.provider}</span>
                  <span className="chip">{aiExplanation.model ?? 'no model'}</span>
                  <span className="chip">{aiExplanation.integrity_passed ? 'Guard 통과' : 'Guard 대체'}</span>
                  <button className="mini-btn" onClick={() => runAIExplanation(true)} disabled={aiLoading}>템플릿으로 보기</button>
                </div>
                <article className="ai-body">{aiExplanation.explanation}</article>
                <div className="locked">
                  <p className="col-label">잠긴 사실 — AI는 공식과 숫자를 결정하지 않습니다</p>
                  <List items={[
                    `유형: ${aiExplanation.locked_facts?.problem_type ?? '-'}`,
                    `solver: ${aiExplanation.locked_facts?.selected_solver ?? '-'}`,
                    ...((aiExplanation.locked_facts?.answers ?? []).map((a: any) => a.display)),
                    ...(aiExplanation.integrity_warnings ?? []),
                  ].filter(Boolean)} />
                </div>
              </Section>
            )}
          </section>
        )}

        {view === 'study' && (
          <section>
            <div className="stat-row">
              <div className="stat"><b>{stats?.total ?? 0}</b><span>저장된 문제</span></div>
              <div className="stat"><b>{stats?.due_today ?? 0}</b><span>오늘 복습</span></div>
              <div className="stat"><b>{stats?.favorite_count ?? 0}</b><span>즐겨찾기</span></div>
            </div>

            <Section label="오늘 할 일" className="tight">
              <List items={(study?.daily_plan ?? []).map((x: any) => `${x.title}: ${x.body}`)} />
            </Section>

            <Section label="오늘 복습할 문제">
              {study?.due_records?.length ? study.due_records.slice(0, 4).map((r: any) => (
                <RecordCard key={r.id} record={r} onRun={(p) => run(p)} onReview={reviewRecord} onFavorite={toggleFavorite} onDelete={removeRecord} />
              )) : <p className="empty">오늘 마감된 복습 문제가 없습니다. 아래 드릴을 눌러 연습을 시작하세요.</p>}
            </Section>

            <Section label="추천 연습 세트">
              <div className="mini-actions" style={{ marginTop: 0, marginBottom: 12 }}>
                <button className="mini-btn" onClick={() => loadPractice('개인 학습 드릴', '전체')}>개인 드릴</button>
                <button className="mini-btn" onClick={() => loadPractice('한국어 파서 강화', '전체')}>한국어 드릴</button>
              </div>
              <div className="cards">
                {(practiceSet?.examples ?? study?.recommended_examples ?? []).slice(0, 6).map((ex: any) => (
                  <button className="ex" key={ex.id} onClick={() => run(ex.problem_text)}>
                    <div className="ex-top"><span className="tag cat">{ex.category}</span><span className="tag diff">{ex.difficulty}</span></div>
                    <b>{ex.title}</b>
                    <p>{ex.learning_goal}</p>
                  </button>
                ))}
              </div>
            </Section>
          </section>
        )}

        {view === 'examples' && (
          <section>
            <div className="filter-row" role="tablist" aria-label="예제 분류">
              {categories.map((c) => (
                <button key={c} className={c === category ? 'filter active' : 'filter'} onClick={() => setCategory(c)}>{c}</button>
              ))}
            </div>
            <div className="cards">
              {filteredExamples.map((ex) => (
                <button className="ex" key={ex.id} onClick={() => run(ex.problem_text)}>
                  <div className="ex-top"><span className="tag cat">{ex.category}</span><span className="tag diff">{ex.difficulty}</span></div>
                  <b>{ex.title}</b>
                  <p>{ex.learning_goal}</p>
                  <div className="chips">{ex.tags.map((tag) => <span className="chip" key={tag}>{tag}</span>)}</div>
                </button>
              ))}
            </div>
          </section>
        )}

        {view === 'notebook' && (
          <section>
            <p className="notice ok">Render 무료 배포에서 서버 DB는 /tmp 기반이라 재시작 때 사라질 수 있습니다. 서버 저장 실패 시 브라우저 localStorage 기록을 함께 표시합니다.</p>
            <NotebookPanel
              stats={stats}
              records={records}
              onRun={(p) => run(p)}
              onReview={reviewRecord}
              onFavorite={toggleFavorite}
              onDelete={removeRecord}
              onExportError={(e) => handleError(e, '백업 다운로드에 실패했습니다.')}
            />
            <TokenSettings onSaved={() => { refreshNotebook(); refreshStudy(); }} />
          </section>
        )}
      </main>
    </div>
  );
}
