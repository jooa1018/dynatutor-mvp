# Phase 6 Notes — Optional LLM Teacher Layer

Phase 6 adds an optional LLM explanation layer without turning the LLM into the physics engine.

## Design rule

```text
Solver decides physics.
Verification checks the answer.
LLM only explains locked facts.
```

## New backend modules

```text
backend/engine/llm/
├─ client.py       # OpenAI-compatible or mock provider
├─ guardrails.py   # locked-fact builder and numeric integrity checks
├─ prompt.py       # strict tutor prompt builder
├─ service.py      # optional LLM orchestration
└─ template.py     # no-cost fallback explanation
```

## New API endpoints

```text
GET  /explain/status
POST /explain/ai
```

## Runtime modes

- No API key: template explanation only, no external call.
- `LLM_PROVIDER=mock`: mock LLM path for UI and integration tests.
- `LLM_PROVIDER=openai`: calls `/v1/responses` on the configured base URL.
- `force_template=true`: never calls external LLM.

## Guardrail behavior

The LLM receives a prompt containing locked facts:

- problem type
- selected solver
- final answer
- extracted values
- usable equations
- forbidden equations
- solved steps
- verification checks

After response, DynaTutor runs a lightweight integrity check:

- final answer numbers should remain visible
- suspicious new numbers are flagged
- if the check fails, the app shows the deterministic fallback explanation instead

This is not a mathematical proof, but it prevents the most common failure mode: fluent explanation that quietly changes the answer.
