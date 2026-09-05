'use strict';

// Executes HomeClient's real event handlers with controlled hook/API/timer
// doubles. This is a UI state regression test, NOT a solver, React DOM, browser,
// fresh public-evaluation or MVRG result. No API/provider is contacted.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../components/HomeClient.tsx'), 'utf8');
const compiled = ts.transpileModule(source, {
  fileName: 'HomeClient.tsx',
  compilerOptions: {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.ReactJSX,
  },
  reportDiagnostics: true,
});
assert.equal((compiled.diagnostics || []).filter((d) => d.category === ts.DiagnosticCategory.Error).length, 0);

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const tick = () => new Promise((resolve) => setImmediate(resolve));
const solved = (id) => ({
  ok: true, verification: { passed: true },
  diagnosis: { selected_solver: 'test-double' },
  answer: { display: id }, test_run_id: id,
});

function harness(overrides = {}) {
  const hooks = [];
  const effects = [];
  const cleanups = [];
  const timers = new Map();
  const saves = [];
  let cursor = 0, mounted = false, tree, timerId = 0;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in hooks)) hooks[index] = typeof initial === 'function' ? initial() : initial;
      return [hooks[index], (value) => {
        hooks[index] = typeof value === 'function' ? value(hooks[index]) : value;
      }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in hooks)) hooks[index] = { current: initial };
      return hooks[index];
    },
    useMemo(fn) { cursor++; return fn(); },
    useEffect(fn) { cursor++; if (!mounted) effects.push(fn); },
  };
  const api = {
    ApiAuthError: class ApiAuthError extends Error {},
    listExamples: async () => ({ examples: [] }),
    listRecords: async () => ({ records: [] }),
    listLocalRecords: () => [],
    getRecordStats: async () => ({}),
    getStudyDashboard: async () => ({}),
    getLLMStatus: async () => ({}),
    getPracticeSet: async () => ({}),
    feedbackProblem: async () => ({ feedback: 'test-double' }),
    saveRecord: async (payload) => { saves.push(payload); return { id: saves.length }; },
    ...overrides,
  };
  const jsx = (type, props) => ({ type, props: props || {} });
  const module = { exports: {} };
  const context = vm.createContext({
    exports: module.exports, module,
    window: {
      setTimeout(fn) { const id = ++timerId; timers.set(id, fn); return id; },
      clearTimeout(id) { timers.delete(id); },
    },
    require(name) {
      if (name === 'react') return react;
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === '../lib/api') return api;
      if (name === '../lib/textbookCorrections') return {
        buildRevisionApprovalPatch: (fingerprint) => ({ textbook_parse_approval: { fingerprint } }),
        mergeTextbookCorrectionPatches: (previous, next) => ({ ...previous, ...next }),
      };
      const component = path.basename(name);
      return { default: component, Section: 'Section', List: 'List',
        RecordCard: 'RecordCard', MechanicsMultimodalPanel: 'MechanicsMultimodalPanel' };
    },
  });
  vm.runInContext(compiled.outputText, context, { filename: 'HomeClient.compiled.cjs' });
  function render() {
    cursor = 0;
    tree = module.exports.default();
    if (!mounted) {
      mounted = true;
      for (const effect of effects) { const cleanup = effect(); if (cleanup) cleanups.push(cleanup); }
    }
    return tree;
  }
  function all(predicate) {
    const found = [];
    function walk(node) {
      if (Array.isArray(node)) { node.forEach(walk); return; }
      if (!node || typeof node !== 'object') return;
      if (predicate(node)) found.push(node);
      walk(node.props?.children);
    }
    walk(tree);
    return found;
  }
  function input(id, value) {
    all((n) => n.props.id === id)[0].props.onChange({ target: { value } });
    render();
  }
  render();
  return {
    render, all, input, saves, api,
    result: () => all((n) => n.type === 'SolveResult')[0],
    problem: () => all((n) => n.props.id === 'problem-input')[0].props.value,
    solveButton: () => all((n) => n.type === 'button' && n.props.className === 'btn primary')[0],
    aiButton: () => all((n) => n.type === 'button' && n.props.className === 'btn ghost')[0],
    notices: () => all((n) => n.type === 'p' && n.props.className?.startsWith('notice')).map((n) => n.props.children).join('\n'),
    flushTimers: () => { for (const fn of [...timers.values()]) fn(); render(); },
    unmount: () => cleanups.forEach((fn) => fn()),
  };
}

test('a late solve cannot restore the old problem or show its result after editing', async () => {
  const pending = deferred();
  const ui = harness({ solveProblem: () => pending.promise });
  ui.input('problem-input', 'A');
  const running = ui.solveButton().props.onClick();
  ui.input('problem-input', 'B');
  pending.resolve(solved('A'));
  await running; ui.render();
  assert.equal(ui.problem(), 'B');
  assert.equal(ui.result(), undefined);
});

test('editing a completed problem clears all result actions before another solve', async () => {
  const ui = harness({ solveProblem: async () => solved('A') });
  ui.input('problem-input', 'A');
  await ui.solveButton().props.onClick(); ui.render();
  assert.ok(ui.result());
  ui.input('problem-input', 'B');
  assert.equal(ui.result(), undefined);
  assert.equal(ui.all((n) => n.type === 'UnderstandingCard').length, 0);
});

test('same-tick duplicate solve clicks invoke the API only once', async () => {
  const pending = deferred(); let calls = 0;
  const ui = harness({ solveProblem: () => { calls++; return pending.promise; } });
  const button = ui.solveButton();
  const one = button.props.onClick();
  const two = button.props.onClick();
  pending.resolve(solved('A')); await Promise.all([one, two]);
  assert.equal(calls, 1);
});

test('an old finally block cannot clear a newer run busy state or cold-start notice', async () => {
  const first = deferred(), second = deferred(); let calls = 0;
  const ui = harness({ solveProblem: () => (++calls === 1 ? first : second).promise });
  ui.input('problem-input', 'A'); const a = ui.solveButton().props.onClick();
  ui.input('problem-input', 'B'); const b = ui.solveButton().props.onClick();
  ui.flushTimers();
  first.resolve(solved('A')); await a; ui.render();
  assert.equal(ui.solveButton().props.disabled, true);
  assert.match(ui.notices(), /서버를 깨우는 중/);
  second.resolve(solved('B')); await b; ui.render();
  assert.equal(ui.result().props.data.test_run_id, 'B');
  assert.equal(ui.solveButton().props.disabled, false);
});

test('an obsolete authorization error does not open a token dialog for the new input', async () => {
  const pending = deferred();
  const ui = harness({ solveProblem: () => pending.promise });
  const running = ui.solveButton().props.onClick();
  ui.input('problem-input', 'B');
  pending.reject(new ui.api.ApiAuthError('old unauthorized'));
  await running; ui.render();
  assert.equal(ui.all((n) => n.type === 'TokenSettings' && n.props.asModal).length, 0);
  assert.doesNotMatch(ui.notices(), /old unauthorized/);
});

test('a failed retry does not leave the previous successful answer displayed', async () => {
  let calls = 0;
  const ui = harness({ solveProblem: async () => {
    if (++calls === 1) return solved('first');
    throw new Error('current request failed');
  } });
  await ui.solveButton().props.onClick(); ui.render();
  assert.ok(ui.result());
  await ui.solveButton().props.onClick(); ui.render();
  assert.equal(ui.result(), undefined);
  assert.match(ui.notices(), /current request failed/);
});

test('student edits invalidate an in-flight feedback/result binding', async () => {
  const pending = deferred();
  const ui = harness({ solveProblem: async () => solved('A'), feedbackProblem: () => pending.promise });
  ui.input('student-input', 'old work');
  const running = ui.solveButton().props.onClick();
  await tick(); ui.render();
  ui.input('student-input', 'new work');
  pending.resolve({ feedback: 'old feedback' }); await running; ui.render();
  assert.equal(ui.result(), undefined);
});

test('saved result uses exactly the input and student snapshot that produced it', async () => {
  const ui = harness({ solveProblem: async () => solved('snapshot-A') });
  ui.input('problem-input', 'A'); ui.input('student-input', 'work A');
  await ui.solveButton().props.onClick(); ui.render();
  await ui.result().props.onSave();
  assert.equal(ui.saves.length, 1);
  assert.equal(ui.saves[0].problem_text, 'A');
  assert.equal(ui.saves[0].student_solution, 'work A');
  assert.equal(ui.saves[0].raw_result.test_run_id, 'snapshot-A');
});

test('a retained save handler is rejected after its input has been edited', async () => {
  const ui = harness({ solveProblem: async () => solved('A') });
  ui.input('problem-input', 'A');
  await ui.solveButton().props.onClick(); ui.render();
  const oldSave = ui.result().props.onSave;
  ui.input('problem-input', 'B'); await oldSave();
  assert.equal(ui.saves.length, 0);
});

test('failed verification is never admitted to notebook storage', async () => {
  const ui = harness({ solveProblem: async () => ({ ...solved('unverified'), verification: { passed: false } }) });
  await ui.solveButton().props.onClick(); ui.render();
  await ui.result().props.onSave();
  assert.equal(ui.saves.length, 0);
});

test('late initial examples do not overwrite a user edit', async () => {
  const pending = deferred();
  const ui = harness({ listExamples: () => pending.promise });
  ui.input('problem-input', 'my draft');
  pending.resolve({ examples: [{ id: 'late', problem_text: 'default from server', category: 'test', tags: [] }] });
  await tick(); ui.render();
  assert.equal(ui.problem(), 'my draft');
});

test('old AI output and finally cannot overwrite a newer explanation request', async () => {
  const first = deferred(), second = deferred(); let calls = 0;
  const ui = harness({ aiExplain: () => (++calls === 1 ? first : second).promise });
  ui.input('problem-input', 'A'); const a = ui.aiButton().props.onClick();
  ui.input('problem-input', 'B'); const b = ui.aiButton().props.onClick();
  first.resolve({ explanation: 'old', used_llm: true }); await a; ui.render();
  assert.equal(ui.aiButton().props.disabled, true);
  assert.equal(ui.all((n) => n.type === 'article').length, 0);
  second.resolve({ explanation: 'new', used_llm: true }); await b; ui.render();
  assert.equal(ui.all((n) => n.type === 'article')[0].props.children, 'new');
});
