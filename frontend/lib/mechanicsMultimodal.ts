import { apiGetJson, apiPostForm, apiPostJson } from './api';

export const MECHANICS_IMAGE_LIMITS = Object.freeze({
  count: 4,
  bytesPerImage: 8 * 1024 * 1024,
  totalBytes: 20 * 1024 * 1024,
  mediaTypes: ['image/png', 'image/jpeg', 'image/webp'] as const,
});

export type MechanicsImageMediaType = (typeof MECHANICS_IMAGE_LIMITS.mediaTypes)[number];

export type MechanicsImageSelection = Readonly<{
  imageId: string;
  file: File;
  previewUrl: string;
}>;

export type EvidenceConflict = Readonly<{
  conflict_id: string;
  fingerprint: string;
  semantic_target_key: string;
  candidate_source_ids: readonly string[];
  candidate_fingerprints: readonly string[];
}>;

export type EvidenceConfirmation = Readonly<{
  conflict_id: string;
  conflict_fingerprint: string;
  chosen_source_id: string;
  chosen_candidate_fingerprint: string;
}>;

export type MultimodalTerminal =
  | 'ready'
  | 'confirmation_required'
  | 'blocked'
  | 'validation_rejected'
  | 'compiler_rejected'
  | 'solve_rejected'
  | 'solved';

export type FigureObservation = Readonly<Record<string, unknown> & {
  observation_id?: string;
  evidence_id?: string | null;
  image_id?: string;
  observation_kind?: string;
  observed_label?: string | null;
  observed_value?: string | null;
  unit_candidate?: string | null;
  evidence_origin?: string;
  policy_eligibility?: string;
  region?: Record<string, unknown>;
  alternatives?: readonly Record<string, unknown>[];
}>;

export type MechanicsRuntimeSummary = Readonly<{
  version?: string;
  terminal?: string;
  normalization_terminal?: string | null;
  validation_issue_codes?: readonly string[];
  compiler_status?: string | null;
  compiler_issue_codes?: readonly string[];
  solve_terminal?: string | null;
  solve_diagnostic_codes?: readonly string[];
  applied_law_ids?: readonly string[];
  equation_count?: number;
  candidate_count?: number;
  rejected_candidate_count?: number;
  verification_checks?: readonly Readonly<{ kind: string; status: string }>[];
  verified_answer?: Readonly<Record<string, unknown>> | null;
}>;

export type MechanicsMultimodalResponse = Readonly<{
  schema: 'dynatutor.mechanics_multimodal_response';
  version: '1.0';
  terminal: MultimodalTerminal;
  sanitized_images: readonly Readonly<{
    image_id: string;
    image_index: number;
    content_sha256: string;
    width: number;
    height: number;
    media_type: 'image/png';
  }>[];
  conflicts: readonly EvidenceConflict[];
  observations: readonly FigureObservation[];
  diagnostics: readonly string[];
  revision_id: string | null;
  parent_revision_id: string | null;
  revision_number: number | null;
  revision_fingerprint: string | null;
  expires_in_seconds: number | null;
  reconciliation_status: string | null;
  accepted_evidence_ids: readonly string[];
  rejected_evidence_ids: readonly string[];
  corrections_applied: readonly Record<string, unknown>[];
  draft: Record<string, unknown> | null;
  runtime: MechanicsRuntimeSummary | null;
  verified_answer: Record<string, unknown> | null;
}>;

export type SourceCorrectionOperation = Readonly<Record<string, unknown> & {
  kind: string;
  operation_id: string;
}>;

const SESSION_STORAGE_KEY = 'dynatutor_multimodal_session_id';

function randomId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}_${crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

export function mechanicsClientRequestId(prefix = 'request'): string {
  return randomId(prefix);
}

export function getMechanicsSessionId(): string {
  if (typeof window === 'undefined') return 'server-render';
  const existing = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;
  const created = randomId('session');
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, created);
  return created;
}

function sessionHeaders(): Record<string, string> {
  return { 'x-dynatutor-session': getMechanicsSessionId() };
}

export function validateMechanicsImages(files: readonly File[]): void {
  if (files.length > MECHANICS_IMAGE_LIMITS.count) {
    throw new Error(`그림은 최대 ${MECHANICS_IMAGE_LIMITS.count}개까지 첨부할 수 있습니다.`);
  }
  let total = 0;
  const references = new Set<File>();
  for (const file of files) {
    if (references.has(file)) throw new Error('같은 그림 파일을 중복으로 첨부할 수 없습니다.');
    references.add(file);
    if (!MECHANICS_IMAGE_LIMITS.mediaTypes.includes(file.type as MechanicsImageMediaType)) {
      throw new Error('PNG, JPEG, WebP 그림만 첨부할 수 있습니다.');
    }
    if (file.size <= 0 || file.size > MECHANICS_IMAGE_LIMITS.bytesPerImage) {
      throw new Error('각 그림은 8MB 이하여야 합니다.');
    }
    total += file.size;
  }
  if (total > MECHANICS_IMAGE_LIMITS.totalBytes) {
    throw new Error('첨부 그림의 전체 크기는 20MB 이하여야 합니다.');
  }
}

export async function requestMechanicsMultimodalEvidence(
  problemText: string,
  selections: readonly MechanicsImageSelection[],
  clientRequestId = mechanicsClientRequestId('evidence'),
): Promise<MechanicsMultimodalResponse> {
  validateMechanicsImages(selections.map((item) => item.file));
  if (!problemText.trim() && selections.length === 0) {
    throw new Error('문제 글 또는 그림을 하나 이상 입력해 주세요.');
  }
  const body = new FormData();
  body.set('problem_text', problemText.trim());
  body.set('client_request_id', clientRequestId);
  selections.forEach((item, index) => {
    body.set(`image_id_${index}`, item.imageId);
    body.append('images', item.file, item.file.name);
  });
  return apiPostForm<MechanicsMultimodalResponse>(
    '/api/mechanics/multimodal/evidence',
    body,
    sessionHeaders(),
  );
}

function requireRevision(response: MechanicsMultimodalResponse): { revisionId: string; fingerprint: string } {
  if (!response.revision_id || !response.revision_fingerprint) {
    throw new Error('서버 revision 정보가 없어 안전하게 계속할 수 없습니다.');
  }
  return { revisionId: response.revision_id, fingerprint: response.revision_fingerprint };
}

export async function confirmMechanicsMultimodalRevision(
  response: MechanicsMultimodalResponse,
  confirmations: readonly EvidenceConfirmation[],
  clientRequestId = mechanicsClientRequestId('confirm'),
): Promise<MechanicsMultimodalResponse> {
  const { revisionId, fingerprint } = requireRevision(response);
  return apiPostJson<MechanicsMultimodalResponse>(
    `/api/mechanics/multimodal/revisions/${encodeURIComponent(revisionId)}/confirm`,
    {
      revision_fingerprint: fingerprint,
      confirmations,
      client_request_id: clientRequestId,
    },
    sessionHeaders(),
  );
}

export async function correctMechanicsMultimodalRevision(
  response: MechanicsMultimodalResponse,
  operations: readonly SourceCorrectionOperation[],
  clientRequestId = mechanicsClientRequestId('correct'),
): Promise<MechanicsMultimodalResponse> {
  const { revisionId, fingerprint } = requireRevision(response);
  if (!operations.length) throw new Error('적용할 수정이 없습니다.');
  return apiPostJson<MechanicsMultimodalResponse>(
    `/api/mechanics/multimodal/revisions/${encodeURIComponent(revisionId)}/correct`,
    {
      schema: 'dynatutor.mechanics_correction_request',
      version: '1.0',
      request_id: clientRequestId,
      base_revision_id: revisionId,
      base_revision_fingerprint: fingerprint,
      operations,
      client_request_id: clientRequestId,
    },
    sessionHeaders(),
  );
}

export async function executeMechanicsMultimodalRevision(
  response: MechanicsMultimodalResponse,
  clientRequestId = mechanicsClientRequestId('execute'),
): Promise<MechanicsMultimodalResponse> {
  const { revisionId, fingerprint } = requireRevision(response);
  return apiPostJson<MechanicsMultimodalResponse>(
    `/api/mechanics/multimodal/revisions/${encodeURIComponent(revisionId)}/execute`,
    { revision_fingerprint: fingerprint, client_request_id: clientRequestId },
    sessionHeaders(),
  );
}

export async function getMechanicsMultimodalRevision(
  revisionId: string,
): Promise<MechanicsMultimodalResponse> {
  return apiGetJson<MechanicsMultimodalResponse>(
    `/api/mechanics/multimodal/revisions/${encodeURIComponent(revisionId)}`,
    sessionHeaders(),
  );
}
