export const EDITABLE_FIELDS: Readonly<Record<string, readonly string[]>>;
export function cloneTextbookParse(parse: any): any;
export function buildTextbookCorrectionPatch(
  original: any,
  edited: any,
): { operations: Array<{ collection: string; id: string; set: Record<string, any> }> };
