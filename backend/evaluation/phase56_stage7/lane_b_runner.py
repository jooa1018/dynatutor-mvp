"""Lane B: run one projected Draft through the real deterministic pipeline.

    MechanicsProblemDraftV1
      → LaneBAuthorityBundleV1 (evaluator-only assumption authority)
      → validate_draft
      → normalize_draft
      → authorize_validated_mechanics_ir
      → MechanicsCompiler.compile
      → solve_verified_equation_graph
      → independent verification
      → frozen RuntimeDomainSnapshotV1

The authority stage sits between projection and validation, outside any
complete-profile transaction: the bundle is built from and bound to the
projected Draft, verified against it before anything reads it, and the same
immutable authorization map is handed to **both** `validate_draft` and
`normalize_draft`.

Each stage records its own terminal.  Exceptions are never collapsed into a
single `runtime_failure`.  The snapshot carries no case identity, no gold, no
corpus text, no full Draft or IR, and no raw exception — only opaque
correlation, neutral terminal, fingerprints, counts, and bounded codes.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from engine.mechanics.compiler import (
    MechanicsCompiler,
    authorize_validated_mechanics_ir,
)
from engine.mechanics.compiler.contracts import has_course_scope_deferred_issue
from engine.mechanics.normalization import normalize_draft
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.validation import ValidationTerminal, validate_draft
from engine.mechanics.verification.contracts import MechanicsSolveTerminal

from evaluation.phase56_stage7.complete_profile_application import (
    close_projected_draft,
)
from evaluation.phase56_stage7.lane_b_authority import (
    LaneBAuthorityError,
    build_lane_b_authority_bundle,
    verify_lane_b_authority_bundle,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjection,
    DraftProjectionTerminal,
)


LANE_B_RUNNER_VERSION = "phase56-stage7-lane-b-runner-v2"

_MAX_DIAGNOSTIC_CODES = 24

# A diagnostic path names *which typed field* failed.  Every other segment is a
# record identity — an array index or an ID derived from a corpus role — so only
# the closed field vocabulary below survives; everything else becomes `*`.  The
# result aggregates a defect class without carrying corpus content.
_PATH_INDEX = re.compile(r"^\d+$")
_PATH_FIELDS: frozenset[str] = frozenset(
    {
        "assumption_policy_ref",
        "assumptions",
        "axes",
        "component",
        "constraints",
        "correction_id",
        "direction",
        "end_event_id",
        "entities",
        "equations",
        "events",
        "evidence_refs",
        "figure_dependency",
        "frame_id",
        "geometry",
        "generalized_coordinate_symbol_ids",
        "interactions",
        "interval_id",
        "interval_ids",
        "ir",
        "laws",
        "motion_intervals",
        "origin",
        "parent_frame_id",
        "participant_ids",
        "point_id",
        "point_ids",
        "points",
        "provenance",
        "quantities",
        "quantity_ids",
        "queries",
        "raw_unit",
        "raw_value",
        "reference_frames",
        "role",
        "shape",
        "source_evidence",
        "start_event_id",
        "state_conditions",
        "subject_id",
        "subject_ids",
        "symbol_id",
        "symbols",
        "target",
        "target_quantity_id",
        "unsupported_features",
    }
)


def canonical_diagnostic_path(path: object) -> str:
    """Reduce a diagnostic path to its typed-field shape, dropping identities."""

    text = str(path or "")
    if not text:
        return ""
    segments = []
    for segment in text.split("."):
        if segment in _PATH_FIELDS:
            segments.append(segment)
        elif _PATH_INDEX.fullmatch(segment):
            segments.append("N")
        else:
            segments.append("*")
    return ".".join(segments)


class LaneBTerminal(str, Enum):
    """Per-stage terminals; no stage collapses into another."""

    projection_rejected = "projection_rejected"
    needs_figure = "needs_figure"
    needs_confirmation = "needs_confirmation"
    insufficient_information = "insufficient_information"
    validation_rejected = "validation_rejected"
    normalization_rejected = "normalization_rejected"
    authorization_failed = "authorization_failed"
    compiler_unsupported = "compiler_unsupported"
    compiler_failure = "compiler_failure"
    solve_rejected = "solve_rejected"
    verification_rejected = "verification_rejected"
    solved = "solved"
    verified_unsupported = "verified_unsupported"


# The engine's own neutral validation terminals, kept distinct from a malformed
# Draft.  Anything absent here — `invalid` — stays `validation_rejected`.
_NEUTRAL_VALIDATION_TERMINALS: dict[ValidationTerminal, LaneBTerminal] = {
    ValidationTerminal.needs_figure: LaneBTerminal.needs_figure,
    ValidationTerminal.needs_confirmation: LaneBTerminal.needs_confirmation,
    ValidationTerminal.insufficient_information: (
        LaneBTerminal.insufficient_information
    ),
    ValidationTerminal.unsupported: LaneBTerminal.verified_unsupported,
}


def _codes(items: Any, attribute: str = "code") -> tuple[str, ...]:
    out: set[str] = set()
    for item in items or ():
        value = getattr(item, attribute, None)
        out.add(str(getattr(value, "value", value)))
    return tuple(sorted(out))[:_MAX_DIAGNOSTIC_CODES]


def _code_paths(items: Any) -> tuple[tuple[str, str], ...]:
    """Pair each diagnostic code with its identity-stripped typed-field path."""

    out: set[tuple[str, str]] = set()
    for item in items or ():
        code = getattr(item, "code", None)
        out.add(
            (
                str(getattr(code, "value", code)),
                canonical_diagnostic_path(getattr(item, "path", None)),
            )
        )
    return tuple(sorted(out))[:_MAX_DIAGNOSTIC_CODES]


def _text(value: object) -> str:
    return str(getattr(value, "value", value))


@dataclass(frozen=True, slots=True)
class LaneBResult:
    """Frozen, privacy-safe per-case runtime result."""

    execution_token: str
    terminal: LaneBTerminal
    version: str = LANE_B_RUNNER_VERSION
    validation_codes: tuple[str, ...] = ()
    validation_code_paths: tuple[tuple[str, str], ...] = ()
    normalization_terminal: str | None = None
    compiler_status: str | None = None
    compiler_codes: tuple[str, ...] = ()
    compiler_code_paths: tuple[tuple[str, str], ...] = ()
    solve_terminal: str | None = None
    solve_codes: tuple[str, ...] = ()
    calculation_fingerprint: str | None = None
    applied_law_ids: tuple[str, ...] = ()
    equation_count: int = 0
    candidate_count: int = 0
    rejected_candidate_count: int = 0
    verified_candidate_count: int = 0
    verification_checks: tuple[tuple[str, str], ...] = ()
    answer_value_si: float | None = None
    answer_query_symbol_id: str | None = None
    answer_unit: str | None = None
    answer_dimension: tuple[tuple[str, int], ...] = ()
    answer_shape: str | None = None
    answer_component: str | None = None
    answer_direction: str | None = None
    query_subject_id: str | None = None
    query_role: str | None = None
    stage_exception: str | None = None

    @property
    def solved(self) -> bool:
        return self.terminal is LaneBTerminal.solved


def _query_projection(draft: Any) -> dict[str, Any]:
    if not draft.queries:
        return {}
    query = draft.queries[0]
    target = query.target
    direction = getattr(target, "direction", None)
    return {
        "query_subject_id": target.subject_id,
        "query_role": _text(target.role),
        "answer_unit": query.output_unit,
        "answer_dimension": tuple(
            sorted(query.output_dimension.model_dump(exclude_defaults=True).items())
        ),
        "answer_shape": _text(query.shape),
        "answer_component": _text(getattr(target, "component", None)),
        "answer_direction": (
            _text(getattr(direction, "direction", None)) if direction is not None else None
        ),
    }


def run_lane_b_case(
    projection: DraftProjection, *, execution_token: str
) -> LaneBResult:
    """Execute one projected Draft through the deterministic pipeline."""

    if projection.terminal is DraftProjectionTerminal.needs_figure:
        return LaneBResult(execution_token, LaneBTerminal.needs_figure)
    if projection.terminal is DraftProjectionTerminal.insufficient_information:
        return LaneBResult(execution_token, LaneBTerminal.insufficient_information)
    if projection.terminal is not DraftProjectionTerminal.projected:
        return LaneBResult(execution_token, LaneBTerminal.projection_rejected)

    text = projection.problem_text
    # The authority stage: built from the projected Draft, bound to it by
    # fingerprint, and verified before anything reads it.  It runs outside the
    # complete-profile transaction below, so closure can consume authority but
    # never mint it.
    try:
        bundle = build_lane_b_authority_bundle(projection)
        if not verify_lane_b_authority_bundle(bundle, projection.draft):
            raise LaneBAuthorityError(
                "the authority bundle does not verify against its own draft"
            )
    except Exception as exc:
        return LaneBResult(
            execution_token,
            LaneBTerminal.authorization_failed,
            stage_exception=type(exc).__name__,
        )
    approved = bundle.approved_assumption_ids
    authority_map = bundle.authorization_map()
    # Complete-profile closure runs before validation and is transactional: the
    # Draft below is either the projection's own or one whole closed Draft, never
    # a partially attached one.  A profile that does not close leaves the Draft
    # exactly as projected.
    draft = close_projected_draft(
        projection.draft, approved_assumption_ids=approved
    ).draft
    query_fields = _query_projection(draft)

    validation = validate_draft(
        text,
        draft,
        approved_assumption_ids=approved,
        authorized_assumptions=authority_map,
    )
    validation_codes = _codes(validation.issues)
    if not validation.accepted:
        # A neutral validation terminal is a first-class blocked outcome, not a
        # rejection: the engine has decided the Draft needs a figure, a reader
        # decision, or information the source never states.  Collapsing those
        # onto `validation_rejected` would hide the difference between "this
        # Draft is malformed" and "this problem cannot be closed safely".
        return LaneBResult(
            execution_token,
            _NEUTRAL_VALIDATION_TERMINALS.get(
                validation.terminal, LaneBTerminal.validation_rejected
            ),
            validation_codes=validation_codes,
            validation_code_paths=_code_paths(validation.issues),
            **query_fields,
        )

    try:
        # The same immutable map validation received — never a copy, never a
        # different one.
        normalization = normalize_draft(
            text,
            draft,
            approved_assumption_ids=approved,
            authorized_assumptions=authority_map,
        )
    except Exception as exc:
        return LaneBResult(
            execution_token,
            LaneBTerminal.normalization_rejected,
            validation_codes=validation_codes,
            stage_exception=type(exc).__name__,
            **query_fields,
        )
    normalization_terminal = _text(normalization.terminal)
    if not normalization.accepted or normalization.ir is None:
        return LaneBResult(
            execution_token,
            LaneBTerminal.normalization_rejected,
            validation_codes=_codes(normalization.validation.issues),
            validation_code_paths=_code_paths(normalization.validation.issues),
            normalization_terminal=normalization_terminal,
            **query_fields,
        )
    fingerprint = normalization.calculation_fingerprint

    try:
        authorization = authorize_validated_mechanics_ir(normalization.ir)
    except Exception as exc:
        return LaneBResult(
            execution_token,
            LaneBTerminal.authorization_failed,
            normalization_terminal=normalization_terminal,
            calculation_fingerprint=fingerprint,
            stage_exception=type(exc).__name__,
            **query_fields,
        )

    try:
        compiled = MechanicsCompiler().compile(
            normalization.ir,
            validated_ir_authorization=authorization,
            approved_assumption_ids=approved,
        )
    except Exception as exc:
        return LaneBResult(
            execution_token,
            LaneBTerminal.compiler_failure,
            normalization_terminal=normalization_terminal,
            calculation_fingerprint=fingerprint,
            stage_exception=type(exc).__name__,
            **query_fields,
        )
    compiler_codes = _codes(compiled.issues)
    compiler_code_paths = _code_paths(compiled.issues)
    compiler_status = _text(compiled.status)
    if not compiled.compilable or compiled.graph is None:
        # A precise typed unsupported is a first-class outcome, not a failure.
        # A *course-scope deferred* unsupported is narrower still: the engine
        # proved from its own typed capability that the readout is out of the
        # course scope it declares, and that proof is what `verified_unsupported`
        # names.  It is never a family label — `has_course_scope_deferred_issue`
        # reads the compiler's own issue codes.
        if has_course_scope_deferred_issue(
            item.code for item in compiled.issues
        ):
            terminal = LaneBTerminal.verified_unsupported
        elif "unsupported" in compiler_status.casefold() or any(
            "unsupported" in code.casefold() for code in compiler_codes
        ):
            terminal = LaneBTerminal.compiler_unsupported
        else:
            terminal = LaneBTerminal.compiler_failure
        return LaneBResult(
            execution_token,
            terminal,
            normalization_terminal=normalization_terminal,
            compiler_status=compiler_status,
            compiler_codes=compiler_codes,
            compiler_code_paths=compiler_code_paths,
            calculation_fingerprint=fingerprint,
            **query_fields,
        )

    graph = compiled.graph
    law_ids = tuple(sorted({item.law_id for item in graph.applications}))
    try:
        solved = solve_verified_equation_graph(graph)
    except Exception as exc:
        return LaneBResult(
            execution_token,
            LaneBTerminal.solve_rejected,
            normalization_terminal=normalization_terminal,
            compiler_status=compiler_status,
            compiler_codes=compiler_codes,
            compiler_code_paths=compiler_code_paths,
            calculation_fingerprint=fingerprint,
            applied_law_ids=law_ids,
            equation_count=len(graph.equations),
            stage_exception=type(exc).__name__,
            **query_fields,
        )

    common = dict(
        normalization_terminal=normalization_terminal,
        compiler_status=compiler_status,
        compiler_codes=compiler_codes,
        compiler_code_paths=compiler_code_paths,
        solve_terminal=_text(solved.terminal),
        solve_codes=_codes(solved.diagnostics.entries),
        calculation_fingerprint=fingerprint,
        applied_law_ids=law_ids,
        equation_count=len(graph.equations),
        candidate_count=len(solved.candidate_set.candidates),
        rejected_candidate_count=len(solved.rejections),
        verified_candidate_count=len(solved.verified_candidates),
        **query_fields,
    )
    if solved.terminal is not MechanicsSolveTerminal.solved:
        return LaneBResult(execution_token, LaneBTerminal.solve_rejected, **common)
    if len(solved.verified_candidates) != 1:
        return LaneBResult(
            execution_token, LaneBTerminal.verification_rejected, **common
        )

    verified = solved.verified_candidates[0]
    checks = tuple(
        (_text(item.kind), _text(item.status)) for item in verified.outcome.checks
    )
    return LaneBResult(
        execution_token,
        LaneBTerminal.solved,
        verification_checks=checks,
        answer_value_si=verified.query_value_si,
        answer_query_symbol_id=verified.query_symbol_id,
        **common,
    )


def deterministic_token(index: int, run_nonce: str = LANE_B_RUNNER_VERSION) -> str:
    """Opaque per-execution token; no case identity contributes."""

    material = f"{run_nonce}\0{index}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:32]
