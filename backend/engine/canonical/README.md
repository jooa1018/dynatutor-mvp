# CanonicalProblem v2

Phase 43 adds an internal, provenance-rich canonical contract without changing the
student API or the legacy solver inputs.

## Runtime boundary

`extract_problem()` still returns `engine.models.CanonicalProblem`. Existing
solvers continue to consume:

- `knowns`
- `flags`
- `requested_outputs`
- the existing system/subtype and compatibility metadata

The additional `canonical_v2` field is internal and is deliberately omitted from
`CanonicalProblemModel`. Clarification patches rebuild v2 so facts, assumptions,
parse candidates, and the fingerprint cannot remain stale.

## Data contracts

`ExtractedFact` records:

- deterministic fact ID and kind;
- subject and physical symbol;
- normalized value, unit, and dimension;
- direction when available;
- source text and half-open raw-text span;
- provenance category and confidence;
- explicit/normalized/inferred/assumed/defaulted/conflicting status;
- source representations or conflicting alternatives;
- the legacy compatibility key when one exists.

`AssumptionRecord` separates model/default/user-confirmed assumptions from
explicit conditions. An explicit phrase such as “공기저항을 무시” is a condition
fact, while an unstated projectile air-resistance rule is a visible
`solver_default` assumption.

`ParseCandidate` retains the fact IDs, system-type candidate, score, warnings,
missing information, and conflicts for each interpretation. Phase 43 stores
alternatives but does not change the Phase 46 routing-score policy.

## Provenance policy

| Status | Meaning |
|---|---|
| `explicit` | Direct user text or confirmed user patch |
| `normalized` | Source representation converted by a deterministic unit/domain rule |
| `inferred` | Deterministic domain inference such as “at rest” → zero velocity |
| `assumed` | Reserved for a fact introduced as an explicit modeling assumption |
| `defaulted` | Engine default such as gravity 9.81 m/s² |
| `conflicting` | Two non-equivalent explicit values were retained |

No value absent from the raw text is labeled `explicit`. Unit normalization
recovers the original representation and span from `raw_text` even when the
legacy normalizer converted it before quantity extraction.

## Serialization and fingerprint

`CanonicalProblemV2.to_json()` and `from_json()` provide a validated round
trip. The fingerprint is SHA-256 over canonical JSON excluding the fingerprint
itself. Dictionary and collection order are canonicalized, so reordering facts,
assumptions, requested outputs, or candidates does not change it. Tampered
serialized content with a stale fingerprint is rejected.

## Compatibility adapter

`build_canonical_v2()` upgrades the completed legacy object.
`to_legacy_problem()` recreates the v1 compatibility view, including Quantity
values/source text, flags, requested outputs, and routing metadata. This is
covered by solver-route regression tests.

## Deliberate Phase 43 limits

- It does not broaden Korean grammar or repair the existing `v0=<multi-digit>`
  parser ambiguity; that belongs to Phase 44.
- It does not change routing margins or clarification policy; that belongs to
  Phase 46.
- It does not build the typed frame/vector/constraint model; that belongs to
  Phase 45.
- Subject assignment uses current compatibility symbols (`m1`, `m2`, point A/B,
  pulley symbols). Richer discourse/entity resolution is deferred to Phase 44.
