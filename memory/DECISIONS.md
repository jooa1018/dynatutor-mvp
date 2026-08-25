# DECISIONS — append-only ledger

Rules: only user-confirmed decisions are recorded. Nothing is edited or deleted. A changed decision gets a **new** entry that `supersedes D-xxx`, and the old entry receives exactly one added line: `↳ superseded by D-yyy (date)`. Sequential ids, never reused. (Full protocol: ballast decision-ledger skill.)

---

## D-001 · Adopt the ballast memory structure — 2026-08-23 (user, project setup)

This project uses `memory/` as its durable brain: decisions in this ledger, unresolved items in OPEN-QUESTIONS, per-session notes in SESSION-LOG. Standing decisions are followed without relitigating; changes go through the supersede protocol.

<!-- Append new entries below. Example of a superseded pair:

## D-002 · Weekly report goes out Fridays — 2026-01-10 (user, chat)

↳ superseded by D-005 (2026-02-01)

## D-005 · Weekly report moves to Mondays — 2026-02-01 (user, chat)

Supersedes D-002. Fridays kept slipping into the weekend; Monday forces the week to start closed-loop.
-->

## D-002 · Execute Phase 56 autonomously to an evidence-backed terminal state — 2026-08-23 (user, long-goal handoff)

Continue on `codex/phase56-generic-mechanics-engine` and PR #17 without asking for routine reversible implementation choices. Follow current repository/executable evidence first, then the latest Phase 56 disposition and project contracts. Finish Stage 7 before starting Stage 8, preserve all physics, evaluation, provenance, privacy, gold-isolation, population, threshold, and official-v1 protections, and stop only at evidence-backed COMPLETE or a genuinely external BLOCKED state after independent work is exhausted. The unavailable historical exact augmentation manifest must not be reconstructed or replaced; any supplemental campaign keeps a separate identity and provenance. Validated atomic commits may be pushed to the current branch and PR, but do not merge `main`, make irreversible production changes, spend paid resources, or publish an external release without existing explicit contract authority.
