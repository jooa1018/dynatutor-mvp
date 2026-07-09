const RAW_API_BASE = process.env.NEXT_PUBLIC_DYNATUTOR_API_BASE ?? process.env.NEXT_PUBLIC_API_BASE ?? '';
const API_BASE = RAW_API_BASE.replace(/\/+$/, '');
const TOKEN_STORAGE_KEY = 'dynatutor_access_token';
const LOCAL_RECORDS_KEY = 'dynatutor_local_records';
const RETRYABLE_ERROR = '백엔드 서버에 연결하지 못했습니다. 백엔드 주소, 토큰, Render cold start, CORS 설정을 확인하세요.';

function getApiBase() {
  if (!API_BASE) {
    throw new Error('NEXT_PUBLIC_DYNATUTOR_API_BASE 환경변수가 설정되지 않았습니다. 배포된 FastAPI 백엔드 주소를 설정해 주세요.');
  }
  return API_BASE;
}

export function getAccessToken() {
  // 보안: NEXT_PUBLIC_* 환경변수는 번들에 포함되어 브라우저에 노출되므로 사용하지 않는다.
  // 토큰은 사용자가 앱의 토큰 설정에서 직접 입력한 값(localStorage)만 사용한다.
  if (typeof window === 'undefined') return '';
  return window.localStorage.getItem(TOKEN_STORAGE_KEY) || '';
}

export function setAccessToken(token: string) {
  if (typeof window === 'undefined') return;
  const clean = token.trim();
  if (clean) window.localStorage.setItem(TOKEN_STORAGE_KEY, clean);
  else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

function authHeaders(extra: Record<string, string> = {}) {
  const token = getAccessToken();
  return token ? { ...extra, 'x-dynatutor-token': token } : extra;
}

export class ApiAuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiAuthError';
  }
}

async function throwApiError(res: Response, path: string): Promise<never> {
  const detail = await safeError(res);
  if (res.status === 401) {
    throw new ApiAuthError(detail || '접근 토큰이 필요합니다. 토큰 설정에서 입력해 주세요.');
  }
  throw new Error(detail || `API 요청 실패: ${path}`);
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithRetry(url: string, init: RequestInit, attempts = 3): Promise<Response> {
  let lastError: any = null;
  for (let i = 0; i < attempts; i += 1) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), i === 0 ? 45000 : 25000);
    try {
      const res = await fetch(url, { ...init, signal: controller.signal });
      window.clearTimeout(timeout);
      return res;
    } catch (e: any) {
      window.clearTimeout(timeout);
      lastError = e;
      if (i < attempts - 1) await sleep(1200 + i * 1200);
    }
  }
  throw new Error(`${RETRYABLE_ERROR}${lastError?.name === 'AbortError' ? ' 첫 요청이 시간 초과되었습니다.' : ''}`);
}

async function postJson(path: string, body: unknown) {
  const res = await fetchWithRetry(`${getApiBase()}${path}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  });
  if (!res.ok) await throwApiError(res, path);
  return res.json();
}

async function getJson(path: string) {
  const res = await fetchWithRetry(`${getApiBase()}${path}`, { headers: authHeaders() });
  if (!res.ok) await throwApiError(res, path);
  return res.json();
}

async function safeError(res: Response) {
  try {
    const out = await res.json();
    return out.detail || out.message || '';
  } catch {
    return '';
  }
}

export async function solveProblem(problemText: string, studentSolution = '', clarifyPatch: any = null, canonicalPatch: any = null) {
  const body: any = { problem_text: problemText, student_solution: studentSolution };
  if (clarifyPatch) body.clarify_patch = clarifyPatch;
  if (canonicalPatch) body.canonical_patch = canonicalPatch;
  return postJson('/solve', body);
}

export async function feedbackProblem(problemText: string, studentSolution: string) {
  return postJson('/feedback', { problem_text: problemText, student_solution: studentSolution });
}

export async function saveRecord(payload: any) {
  return postJson('/records', payload);
}

export async function listRecords() {
  return getJson('/records?limit=30');
}

export async function getRecordStats() {
  return getJson('/records/stats');
}

export async function listExamples() {
  return getJson('/examples');
}

export async function getLLMStatus() {
  return getJson('/explain/status');
}

export async function aiExplain(problemText: string, studentSolution = '', forceTemplate = false) {
  return postJson('/explain/ai', {
    problem_text: problemText,
    student_solution: studentSolution,
    level: 'beginner',
    style: 'friendly',
    force_template: forceTemplate,
  });
}

export async function getStudyDashboard() {
  return getJson('/study/dashboard?limit=8');
}

export async function getPracticeSet(category = '전체', difficulty = '전체', count = 6) {
  const params = new URLSearchParams();
  if (category && category !== '전체') params.set('category', category);
  if (difficulty && difficulty !== '전체') params.set('difficulty', difficulty);
  params.set('count', String(count));
  return getJson(`/study/practice?${params.toString()}`);
}

export async function markRecordReview(recordId: number, correct: boolean, note = '') {
  return postJson(`/records/${recordId}/review`, { correct, note });
}

export async function patchRecord(recordId: number, payload: any) {
  const res = await fetchWithRetry(`${getApiBase()}/records/${recordId}`, {
    method: 'PATCH',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });
  if (!res.ok) await throwApiError(res, `/records/${recordId}`);
  return res.json();
}


export function saveLocalRecord(payload: any) {
  if (typeof window === 'undefined') return null;
  const existing = listLocalRecords();
  const record = {
    ...payload,
    id: -Date.now(),
    local_only: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  window.localStorage.setItem(LOCAL_RECORDS_KEY, JSON.stringify([record, ...existing].slice(0, 100)));
  return record;
}

export function listLocalRecords() {
  if (typeof window === 'undefined') return [] as any[];
  try {
    const raw = window.localStorage.getItem(LOCAL_RECORDS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [] as any[];
  }
}

function writeLocalRecords(records: any[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(LOCAL_RECORDS_KEY, JSON.stringify(records.slice(0, 100)));
}

// local_only 기록의 복습 처리 — 서버 API를 타지 않는다 (Phase 40).
export function reviewLocalRecord(id: number, correct: boolean) {
  const records = listLocalRecords();
  const next = records.map((r: any) => {
    if (r.id !== id) return r;
    const mastery = Math.max(0, Math.min(6, (r.mastery ?? 0) + (correct ? 1 : -1)));
    return {
      ...r,
      mastery,
      review_count: (r.review_count ?? 0) + 1,
      last_review_correct: correct,
      updated_at: new Date().toISOString(),
    };
  });
  writeLocalRecords(next);
  return next;
}

export function toggleLocalFavorite(id: number) {
  const next = listLocalRecords().map((r: any) => (r.id === id ? { ...r, favorite: !r.favorite, updated_at: new Date().toISOString() } : r));
  writeLocalRecords(next);
  return next;
}

export function deleteLocalRecord(id: number) {
  const next = listLocalRecords().filter((r: any) => r.id !== id);
  writeLocalRecords(next);
  return next;
}

export async function deleteRecord(recordId: number) {
  const res = await fetchWithRetry(`${getApiBase()}/records/${recordId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) await throwApiError(res, `/records/${recordId}`);
  return res.json();
}

export async function downloadNotebookExport() {
  // 보안: 토큰을 URL 쿼리로 붙이지 않는다 (서버/프록시 로그, 히스토리 유출 방지).
  // 헤더 인증으로 받아 localStorage 기록과 합쳐 blob 다운로드한다 (Phase 40).
  let serverData: any = null;
  let serverError: string | null = null;
  try {
    const res = await fetchWithRetry(`${getApiBase()}/records/export`, { headers: authHeaders() });
    if (!res.ok) await throwApiError(res, '/records/export');
    serverData = await res.json();
  } catch (e: any) {
    if (e instanceof ApiAuthError) throw e; // 토큰 문제는 모달 흐름으로
    serverError = e?.message ?? String(e);
  }
  const localRecords = listLocalRecords();
  if (!serverData && !localRecords.length) {
    throw new Error(serverError ? `서버 백업 실패(${serverError}) — 이 기기에 저장된 기록도 없습니다.` : '내보낼 기록이 없습니다.');
  }
  const combined = {
    ...(serverData ?? {}),
    exported_at: new Date().toISOString(),
    server_available: Boolean(serverData),
    ...(serverError ? { server_error: serverError } : {}),
    local_records: localRecords,
  };
  const blob = new Blob([JSON.stringify(combined, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `dynatutor_notebook_${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
