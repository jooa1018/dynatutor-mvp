# Phase 57 reproducible public fixture set

This directory is the repository-contained public input for the distinct
`PHASE57_REPRODUCIBLE_PUBLIC_CONTINUATION_V1` campaign.

It contains only the corpus author's explicitly public, independently authored
files:

- `public_dev.jsonl` — 84 public development/regression cases;
- `public_adversarial.jsonl` — 16 public safety/binding cases;
- `schema.json` — the public case schema;
- `sanitized_manifest.json` — count/hash-only fixture identity.

It deliberately excludes the source ZIP, `public_all.jsonl`, the private
held-out manifest, and every private held-out case. The two JSONL files do
contain the intentionally public problem text, public case identifiers, and
public gold needed by the isolated post-runtime scorer. Their provenance fields
state that the cases were independently authored from abstract structures and
do not copy source problem text, numbers, or figures. These fixtures may be
used for public regression and development; they are not hidden-generalization
evidence.

Phase 56 Stage 7 remains historically `NOT_ACCEPTED`: this fixture set and any
Phase 57 result are a new, separately named measurement and cannot substitute
for the unavailable historical augmentation manifest.
