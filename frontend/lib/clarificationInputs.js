function fieldValueKey(optionId, symbol) {
  return `${optionId}:${symbol}`;
}

function isFiniteNumericInput(raw) {
  if (typeof raw !== 'string' || !raw.trim()) return false;
  return Number.isFinite(Number(raw));
}

function canSubmitClarification(option, values) {
  const fields = option.input_fields || [];
  if (fields.length) {
    return fields.every((field) => (
      !field.required
      || isFiniteNumericInput(values[fieldValueKey(option.id, field.symbol)] || '')
    ));
  }
  if (option.needs_value) {
    return isFiniteNumericInput(
      values[fieldValueKey(option.id, option.needs_value)] || '',
    );
  }
  return true;
}

function buildClarifyPatch(option, values) {
  if (!canSubmitClarification(option, values)) {
    throw new Error('required clarification inputs are incomplete');
  }
  const fields = option.input_fields || [];
  if (fields.length) {
    return {
      ...option.patch,
      set_knowns: fields.map((field) => ({
        symbol: field.symbol,
        label: field.label,
        unit: field.unit,
        value: Number(values[fieldValueKey(option.id, field.symbol)]),
      })),
    };
  }
  if (option.needs_value) {
    return {
      ...option.patch,
      set_known: {
        ...option.patch.set_known,
        value: Number(values[fieldValueKey(option.id, option.needs_value)]),
      },
    };
  }
  return option.patch;
}

module.exports = {
  buildClarifyPatch,
  canSubmitClarification,
  fieldValueKey,
  isFiniteNumericInput,
};
