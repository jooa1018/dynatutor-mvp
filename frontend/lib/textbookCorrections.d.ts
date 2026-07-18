export const EDITABLE_FIELDS: Readonly<Record<string, readonly string[]>>;
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
