export type ClarificationInputField = {
  symbol: string;
  label: string;
  unit: string;
  input_type?: 'number' | string;
  required?: boolean;
};

export type ClarificationOptionInput = {
  id: string;
  patch: Record<string, unknown>;
  needs_value?: string | null;
  input_fields?: ClarificationInputField[];
};

export function fieldValueKey(optionId: string, symbol: string): string;
export function isFiniteNumericInput(raw: string): boolean;
export function canSubmitClarification(
  option: ClarificationOptionInput,
  values: Record<string, string>,
): boolean;
export function buildClarifyPatch(
  option: ClarificationOptionInput,
  values: Record<string, string>,
): Record<string, unknown>;
