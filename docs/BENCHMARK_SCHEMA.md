# DynaTutor Benchmark Schema

Phase 20 benchmark cases use this common schema.

## Positive derived case

```json
{
  "id": "os_projectile_range_001",
  "source_family": "OpenStax University Physics style derived",
  "license_note": "Derived-style numerical benchmark for testing; no original problem wording or solution text copied.",
  "derivation_note": "DynaTutor-created derived-style benchmark; no original wording copied.",
  "topic": "projectile_motion",
  "problem_ko": "속력 12m/s, 각도 25도 로 발사한 포물체의 사거리는?",
  "expected_solver": "projectile_motion",
  "expected_ok": true,
  "expected_numeric": 11.242,
  "tolerance": 0.00001,
  "must_not_use_llm_for_answer": true
}
```

## Negative case

```json
{
  "id": "neg_ambiguous_pulley_001",
  "source_family": "FOSSEE/OpenStax/MIT negative control",
  "license_note": "Negative benchmark created by DynaTutor; no source wording copied.",
  "derivation_note": "Designed to ensure the engine asks for missing physics information instead of hallucinating a solution.",
  "topic": "ambiguous_pulley",
  "problem_ko": "m1=2kg, m2=3kg가 줄과 도르래로 연결되어 있다. 가속도는?",
  "expected_ok": false,
  "expected_reason_contains": ["도르래 구조"],
  "must_not_use_llm_for_answer": true
}
```

## Rules

```text
1. Do not copy original textbook/source wording.
2. Do not copy external solution text.
3. Prefer fresh Korean problem statements.
4. Include source_family as a broad source-family inspiration label.
5. Include license_note and derivation_note.
6. Mark must_not_use_llm_for_answer=true.
7. Positive cases must check expected_solver.
8. Numeric oracle is optional but recommended for stable closed-form outputs.
9. Negative cases must be expected_ok=false.
```
