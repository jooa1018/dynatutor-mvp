# Phase 22 LLM Teacher Guardrail v2

Phase 22 strengthens the optional LLM teacher layer.

## Goal

The LLM may explain, but it must not solve independently.

Allowed:

```text
- explain locked solver results
- explain why a formula was chosen
- explain common mistakes
- rephrase verified StepCards
```

Forbidden:

```text
- change final answer
- change units
- introduce new numerical values
- use not-applicable equations
- assume missing conditions
- fabricate an answer for unsupported problems
```

## Updated files

```text
backend/app/schemas/llm.py
backend/engine/llm/guardrails.py
backend/engine/llm/prompt.py
backend/engine/llm/service.py
backend/engine/llm/template.py
```

## LockedFacts v2

`LockedFacts` now includes:

```text
problem_type
selected_solver
solver_ok
answer_display
answer_numbers
answer_unit
unsupported_reason
equations
not_applicable_equations
checks
known_values
allowed_numbers
steps
locked_hash
locked_facts_version = phase22
```

The `locked_hash` is a short deterministic hash of the locked facts payload. It
is included in the prompt and integrity report so a developer can confirm which
facts the LLM was supposed to obey.

## Prompt hardening

The LLM prompt now includes:

```text
LOCKED_FACTS_JSON
locked_hash
answer_display
allowed_numbers
not_applicable_equations
solver_ok
unsupported_reason
```

The prompt explicitly says:

```text
Do not introduce numbers outside LOCKED_FACTS_JSON.
Do not use not-applicable equations.
Do not create a numerical answer for unsupported problems.
Repeat answer_display in the final check section.
```

## Output validation

`validate_llm_explanation()` now checks:

```text
- final answer numbers are present
- final answer unit is present
- final-answer section or answer phrase exists
- new unapproved numbers are not introduced
- not-applicable equations are not used
- unsupported problems do not receive fake numeric answers
- phrases suggesting changed calculations or new assumptions are rejected
```

If validation fails:

```text
LLM output is not shown as the user-facing explanation.
DynaTutor falls back to the safe template explanation.
used_llm = false
displayed_source = template_fallback_after_guardrail
integrity_passed = false
```

## Response metadata

`AIExplainResponse` now includes:

```text
integrity_report
displayed_source
```

Possible `displayed_source` values:

```text
template
llm
template_fallback_after_guardrail
template_fallback_after_error
```

## Template fallback

The safe template explanation now ensures:

```text
### 마지막 확인
최종 답은 **answer_display** 입니다.
```

when a verified final answer exists.

## Tests

Added:

```text
backend/tests/test_phase22_llm_guardrail_v2.py
```

Validated:

```text
- LockedFacts includes hash, answer numbers, allowed numbers, not-applicable equations
- prompt includes LOCKED_FACTS_JSON and locked_hash
- safe explanation passes
- changed final number is rejected
- missing final answer is rejected
- not-applicable equation is rejected
- unsupported problem cannot receive fake numeric answer
- template endpoint reports integrity metadata
- mock LLM falls back when it omits the locked final answer
```

Test result:

```text
143 passed
```

## Important limitation

This guardrail is deterministic and useful, but it is not a proof of perfect
pedagogy. It blocks common dangerous failures and keeps the solver as the source
of truth.

Future improvements could add:

```text
- structured JSON LLM output
- sentence-by-sentence citation to StepCards
- formula AST comparison
- stronger unit-expression parser
```
