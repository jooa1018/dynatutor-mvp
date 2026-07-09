'use client';

import { Section } from './Card';
import { downloadNotebookExport } from '../lib/api';

export function RecordCard({ record, onRun, onReview, onFavorite, onDelete }: {
  record: any;
  onRun: (problem: string) => void;
  onReview: (id: number, correct: boolean) => void;
  onFavorite: (record: any) => void;
  onDelete?: (record: any) => void;
}) {
  const isLocal = record.local_only || record.id < 0;
  return (
    <div className="rec">
      <div className="rec-head">
        <span className="rec-id">
          {isLocal ? <span className="chip local-badge" title="서버에 저장되지 않고 이 기기에만 있는 기록">이 기기</span> : `#${record.id} · `}
          {isLocal ? ` ${record.problem_type ?? ''}` : record.problem_type}{record.favorite ? ' ★' : ''}
        </span>
        {record.answer_display ? <span className="rec-ans">{record.answer_display}</span> : null}
      </div>
      <p>{record.problem_text}</p>
      {record.review_due !== undefined && (
        <p className="rec-meta">복습일 {record.review_due ?? '-'} · 숙련도 {record.mastery}/6 · {record.review_count}회 복습</p>
      )}
      <div className="mini-actions">
        <button className="mini-btn" onClick={() => onRun(record.problem_text)}>다시 풀기</button>
        <button className="mini-btn" onClick={() => onReview(record.id, true)}>정답</button>
        <button className="mini-btn" onClick={() => onReview(record.id, false)}>오답</button>
        <button className="mini-btn" onClick={() => onFavorite(record)}>{record.favorite ? '즐겨찾기 해제' : '즐겨찾기'}</button>
        {onDelete ? <button className="mini-btn danger" onClick={() => onDelete(record)}>삭제</button> : null}
      </div>
    </div>
  );
}

export default function NotebookPanel({ stats, records, onRun, onReview, onFavorite, onDelete, onExportError }: {
  stats: any;
  records: any[];
  onRun: (problem: string) => void;
  onReview: (id: number, correct: boolean) => void;
  onFavorite: (record: any) => void;
  onDelete?: (record: any) => void;
  onExportError: (e: any) => void;
}) {
  return (
    <>
      <Section label="통계" className="tight">
        <div className="stat-row" style={{ marginBottom: 0 }}>
          <div className="stat"><b>{stats?.total ?? 0}</b><span>저장된 문제</span></div>
          <div className="stat"><b>{stats?.due_today ?? 0}</b><span>오늘 복습</span></div>
          <div className="stat"><b>{stats?.favorite_count ?? 0}</b><span>즐겨찾기</span></div>
        </div>
        {stats?.top_tags ? (
          <div className="chips" style={{ marginTop: 12 }}>
            {Object.entries(stats.top_tags).map(([k, v]) => <span className="chip" key={k}>{k} · {String(v)}</span>)}
          </div>
        ) : null}
        <div className="mini-actions" style={{ marginTop: 12 }}>
          <button className="mini-btn" onClick={() => downloadNotebookExport().catch(onExportError)}>오답노트 백업 JSON 내려받기</button>
        </div>
      </Section>

      <Section label="최근 오답">
        {records.length ? records.slice(0, 8).map((r) => (
          <RecordCard key={r.id} record={r} onRun={onRun} onReview={onReview} onFavorite={onFavorite} onDelete={onDelete} />
        )) : <p className="empty">저장된 오답이 없습니다. 문제를 풀고 답 블록의 저장 버튼을 누르세요.</p>}
      </Section>
    </>
  );
}
