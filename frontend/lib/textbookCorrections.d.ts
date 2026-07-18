export const EDITABLE_FIELDS: Readonly<Record<string, readonly string[]>>;
export interface TextbookParseV2 {
  schema: 'dynatutor.textbook_parse';
  version: '2.0';
  parse_status: 'complete' | 'ambiguous' | 'insufficient_information' | 'needs_figure' | 'unsupported';
  entities: Array<Record<string, unknown>>;
  motion_segments: Array<Record<string, unknown>>;
  events: Array<Record<string, unknown>>;
  explicit_facts: Array<{
    fact_id: string;
    semantic_key: string;
    occurrence_index: number;
    quantity_occurrence_index: number;
    [key: string]: unknown;
  }>;
  relations: Array<Record<string, unknown>>;
  queries: Array<Record<string, unknown>>;
  assumption_proposals: Array<Record<string, unknown>>;
  interpretation_candidates: Array<{
    candidate_id: string;
    system_type: string;
    assumption_ids: string[];
    [key: string]: unknown;
  }>;
  auto_attached_assumption_ids?: string[];
  [key: string]: unknown;
}
export interface CandidateEvaluationV2 {
  candidate_id: string;
  auto_attached_assumption_ids: string[];
  effective_candidate: TextbookParseV2['interpretation_candidates'][number];
}
export function cloneTextbookParse(parse: any): any;
export function buildTextbookCorrectionPatch(
  original: any,
  edited: any,
): { operations: Array<{ collection: string; id: string; set: Record<string, any> }> };
export function mergeTextbookCorrectionPatches(
  previous?: { operations: Array<{ collection: string; id: string; set: Record<string, any> }> } | null,
  next?: { operations: Array<{ collection: string; id: string; set: Record<string, any> }> } | null,
): { operations: Array<{ collection: string; id: string; set: Record<string, any> }> };
export function buildRevisionApprovalPatch(
  fingerprint: string,
  correction?: { operations: Array<{ collection: string; id: string; set: Record<string, any> }> } | null,
  correctionFingerprint?: string | null,
): {
  textbook_parse_approval: { fingerprint: string };
  textbook_parse_correction?: { operations: Array<{ collection: string; id: string; set: Record<string, any> }> };
};
