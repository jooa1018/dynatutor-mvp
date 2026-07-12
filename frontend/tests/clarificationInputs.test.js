const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildClarifyPatch,
  canSubmitClarification,
  fieldValueKey,
} = require('../lib/clarificationInputs');

function vectorOption(prefix, unit) {
  const cap = prefix === 'v' ? 'V' : 'A';
  return {
    id: `provide_${prefix}A_vector`,
    patch: {
      input_contract: prefix === 'v' ? 'rigid_vA_vector' : 'rigid_aA_vector',
    },
    input_fields: [
      { symbol: `${prefix}Ax`, label: `A point ${cap} x`, unit, required: true },
      { symbol: `${prefix}Ay`, label: `A point ${cap} y`, unit, required: true },
    ],
  };
}

test('renders_two_inputs_for_vA_vector_logic', () => {
  assert.deepEqual(vectorOption('v', 'm/s').input_fields.map((field) => field.symbol), ['vAx', 'vAy']);
});

test('renders_two_inputs_for_aA_vector_logic', () => {
  assert.deepEqual(vectorOption('a', 'm/s^2').input_fields.map((field) => field.symbol), ['aAx', 'aAy']);
});

test('submits_set_knowns_with_both_values', () => {
  const option = vectorOption('v', 'm/s');
  const values = {
    [fieldValueKey(option.id, 'vAx')]: '3.5',
    [fieldValueKey(option.id, 'vAy')]: '-2',
  };

  assert.deepEqual(buildClarifyPatch(option, values), {
    input_contract: 'rigid_vA_vector',
    set_knowns: [
      { symbol: 'vAx', label: 'A point V x', unit: 'm/s', value: 3.5 },
      { symbol: 'vAy', label: 'A point V y', unit: 'm/s', value: -2 },
    ],
  });
});

test('disables_submit_when_one_component_is_missing', () => {
  const option = vectorOption('a', 'm/s^2');
  const values = {
    [fieldValueKey(option.id, 'aAx')]: '1',
  };

  assert.equal(canSubmitClarification(option, values), false);
  assert.throws(() => buildClarifyPatch(option, values));
});

test('keeps_single_value_clarification_backward_compatible', () => {
  const option = {
    id: 'provide_mu',
    patch: { set_known: { symbol: 'mu', unit: '' } },
    needs_value: 'mu',
  };
  const values = {
    [fieldValueKey(option.id, 'mu')]: '0.25',
  };

  assert.equal(canSubmitClarification(option, values), true);
  assert.deepEqual(buildClarifyPatch(option, values), {
    set_known: { symbol: 'mu', unit: '', value: 0.25 },
  });
});
