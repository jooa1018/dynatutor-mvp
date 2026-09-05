'use strict';
// Real panel callbacks with controlled hooks/API promises, NOT solver or browser
// evidence. Backend revisions/receipts remain the mathematical authority.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('typescript');
const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname,
  '../components/mechanics/MechanicsMultimodalPanel.tsx'), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const response = (id) => ({ terminal: 'solved', revision_id: id,
  verified_answer: { value_si: 1 }, conflicts: [], corrections_applied: [], draft: {} });
function harness(overrides = {}) {
  let cursor = 0, tree, pendingEffects = [], props;
  const hooks = [], accepted = [], authErrors = [];
  const react = {
    useState(initial) {
      const i = cursor++;
      if (!(i in hooks)) hooks[i] = initial;
      return [hooks[i], (next) => { hooks[i] = typeof next === 'function' ? next(hooks[i]) : next; }];
    },
    useRef(initial) { const i = cursor++; if (!(i in hooks)) hooks[i] = { current: initial }; return hooks[i]; },
    useMemo(fn) { cursor++; return fn(); },
    useEffect(fn, deps) {
      const i = cursor++, old = hooks[i];
      if (!old || deps.some((d, n) => d !== old.deps[n])) pendingEffects.push(() => {
        if (old?.cleanup) old.cleanup();
        hooks[i] = { deps, cleanup: fn() };
      });
    },
  };
  class ApiAuthError extends Error {}
  const api = { ...overrides };
  const jsx = (type, childProps) => ({ type, props: childProps || {} });
  const compiledModule = { exports: {} };
  vm.runInNewContext(compiled, { exports: compiledModule.exports, module: compiledModule,
    require(name) {
      if (name === 'react') return react;
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name === '../../lib/api') return { ApiAuthError };
      if (name === '../../lib/mechanicsMultimodal') return api;
      const component = path.basename(name); return { [component]: component };
    },
  });
  props = { problemText: 'A', onVerifiedResult: (r) => accepted.push(r), onAuthError: (e) => authErrors.push(e) };
  function render() {
    cursor = 0; pendingEffects = [];
    tree = compiledModule.exports.MechanicsMultimodalPanel(props);
    const effects = pendingEffects;
    for (const effect of effects) effect();
    if (effects.length) { cursor = 0; pendingEffects = []; tree = compiledModule.exports.MechanicsMultimodalPanel(props); }
  }
  function all(predicate) {
    const out = [];
    function walk(node) {
      if (Array.isArray(node)) { node.forEach(walk); return; }
      if (!node || typeof node !== 'object') return;
      if (predicate(node)) out.push(node); walk(node.props?.children);
    }
    walk(tree); return out;
  }
  render();
  return { render, all, accepted, authErrors, ApiAuthError,
    edit(text) { props = { ...props, problemText: text }; render(); },
    button: () => all((n) => n.type === 'button' && n.props.className === 'btn primary')[0],
    unmount() { for (const hook of hooks) if (hook?.cleanup) hook.cleanup(); },
  };
}
test('generic late response cannot publish an old revision after the problem changed', async () => {
  const pending = deferred(), ui = harness({ requestMechanicsMultimodalEvidence: () => pending.promise });
  const run = ui.button().props.onClick(); ui.render(); ui.edit('B');
  pending.resolve(response('A')); await run; ui.render();
  assert.equal(ui.accepted.length, 0);
  assert.equal(ui.all((n) => n.props.className === 'mechanics-verified-result').length, 0);
});
test('generic same-tick duplicate start invokes the provider only once', async () => {
  const pending = deferred(); let calls = 0;
  const ui = harness({ requestMechanicsMultimodalEvidence: () => { calls++; return pending.promise; } });
  const button = ui.button(); const a = button.props.onClick(), b = button.props.onClick();
  pending.resolve(response('A')); await Promise.all([a, b]);
  assert.equal(calls, 1);
});
test('generic old finally cannot release a newer request after editing', async () => {
  const first = deferred(), second = deferred(); let calls = 0;
  const ui = harness({ requestMechanicsMultimodalEvidence: () => (++calls === 1 ? first : second).promise });
  const a = ui.button().props.onClick(); ui.render(); ui.edit('B');
  const b = ui.button().props.onClick(); ui.render();
  first.resolve(response('A')); await a; ui.render();
  const stillLoading = ui.button().props.disabled;
  second.resolve(response('B')); await b; ui.render();
  assert.equal(calls, 2); assert.equal(stillLoading, true);
  assert.deepEqual(ui.accepted.map((r) => r.revision_id), ['B']);
});
test('generic obsolete auth errors and unmounted completions are ignored', async () => {
  const pending = deferred(), ui = harness({ requestMechanicsMultimodalEvidence: () => pending.promise });
  const run = ui.button().props.onClick(); ui.edit('B'); ui.unmount();
  pending.reject(new ui.ApiAuthError('obsolete'));
  await run; ui.render();
  assert.equal(ui.authErrors.length, 0);
});
test('generic stale correction cannot claim success for an edited problem', async () => {
  const pending = deferred();
  const ui = harness({ requestMechanicsMultimodalEvidence: async () => response('A'),
    correctMechanicsMultimodalRevision: () => pending.promise });
  await ui.button().props.onClick(); ui.render();
  const correction = ui.all((n) => n.type === 'MechanicsCorrectionForm')[0].props.onApply([]);
  ui.edit('B'); pending.resolve(response('corrected-A'));
  assert.equal(await correction, false);
  assert.deepEqual(ui.accepted.map((r) => r.revision_id), ['A']);
});
