"""The remaining gap, measured by execution instead of asserted in a table.

`docs/PHASE56_STAGE7_STRUCTURAL_BLOCKERS.md` says the unsolved public cases fall
into a fixed number of typed cohorts, that every one is blocked on a premise the
corpus does not type, and that most of them reduce to one missing record.  Those
are three empirical claims, and a table cannot hold them: a cohort count written
by hand drifts the moment a package lands, and "blocked on a missing premise"
read off a document is indistinguishable from "we did not find the closure".

So this module computes them.  It partitions every projected context by a
**structural fingerprint** taken from typed structure alone, asks of each
context which typed carriers a closure would have to read and which of those the
source actually states, and reports the partition as counts.

Three properties are load-bearing and each has its own tests.

*The fingerprint is physics, not spelling.*  It is invariant under entity,
relation and quantity identifier changes, array order, the participant order of
a symmetric relation, equivalent unit normalization, and case or family naming —
and it separates contexts that differ in query role, component, event or
interval scope, topology, contact regime, quantity roles, or any of the
direction, frame, endpoint and assumption carriers.

*A missing carrier is derived from the contract, not guessed.*  Every
`SourceCarrierCategory` is required only when the context's own typed structure
needs it, and is satisfied only by a record the source states.

*"The emitter fired" is not "the problem is solved".*  `ProgressRung` is a
strict ladder, so a counterfactual that supplies a carrier and moves a context
from `law_not_emitted` to `law_emitted_graph_underdetermined` reports exactly
that, and cannot be read as a closure.

Privacy is structural, not filtered.  No record here has a field that could hold
a case identifier, a family, a split, problem text, an evidence quote, an
expected terminal, an expected answer, a tolerance, or a numeric value from a
source — so the aggregate needs no redaction step to be publishable.

Nothing here participates in a runtime decision.  It is a measurement, never a
gate, and never an input to projection, normalization, compilation, or solving.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from enum import Enum
from typing import Annotated, Any, Iterable, Mapping, Sequence

from pydantic import Field, StringConstraints

from evaluation.phase56_stage7.contracts import FrozenStrictModel


AUTHORITY_CENSUS_VERSION = "phase56-stage7-authority-census-v1"

# The fingerprint salt is public evaluator metadata, not a secret.  It exists so
# a cohort digest is stable across runs and obviously not a hash of anything
# case-identifying.
_FINGERPRINT_SALT = "phase56-stage7-structural-cohort-v1"

_Token = Annotated[str, StringConstraints(min_length=1, max_length=160)]
_Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class SourceCarrierCategory(str, Enum):
    """The typed carriers a closure may have to read from the source.

    Each member names a *record the source states*, never an inference.  The
    engine's Draft contract can hold every one of them; whether the public
    corpus contract can state them is the question this census answers.
    """

    reference_frame = "reference_frame"
    angle_reference_datum = "angle_reference_datum"
    motion_sense = "motion_sense"
    contact_side = "contact_side"
    endpoint_condition = "endpoint_condition"
    constraint_authority = "constraint_authority"
    interaction_target = "interaction_target"
    signed_scalar_encoding = "signed_scalar_encoding"


class ProgressRung(str, Enum):
    """How far a context actually got, as a strict ladder.

    The ordering is the point.  A carrier that moves a context up one rung has
    been measured to do exactly that much, and reporting it as a solve would be
    the overclaim this ladder exists to prevent.
    """

    projection_rejected = "projection_rejected"
    blocked_neutral_terminal = "blocked_neutral_terminal"
    validation_rejected = "validation_rejected"
    normalization_rejected = "normalization_rejected"
    authorization_failed = "authorization_failed"
    law_not_emitted = "law_not_emitted"
    law_emitted_graph_underdetermined = "law_emitted_graph_underdetermined"
    graph_determined_solve_failed = "graph_determined_solve_failed"
    solved_unverified = "solved_unverified"
    solved_and_verified = "solved_and_verified"


_RUNG_ORDER: tuple[ProgressRung, ...] = (
    ProgressRung.projection_rejected,
    ProgressRung.blocked_neutral_terminal,
    ProgressRung.validation_rejected,
    ProgressRung.normalization_rejected,
    ProgressRung.authorization_failed,
    ProgressRung.law_not_emitted,
    ProgressRung.law_emitted_graph_underdetermined,
    ProgressRung.graph_determined_solve_failed,
    ProgressRung.solved_unverified,
    ProgressRung.solved_and_verified,
)


def rung_index(rung: ProgressRung) -> int:
    """Position on the ladder, so `higher > lower` is a comparison, not a guess."""

    return _RUNG_ORDER.index(rung)


class ExpectedClass(str, Enum):
    """The class a context is expected to land in, supplied by the caller.

    The census never reads gold itself.  A caller that has already crossed into
    the gold domain passes the class in; a caller that has not passes
    `unknown`, and every supported/deferred split is then reported as unknown
    rather than guessed.
    """

    supported = "supported"
    deferred = "deferred"
    unsupported_other = "unsupported_other"
    needs_figure = "needs_figure"
    needs_confirmation = "needs_confirmation"
    insufficient_information = "insufficient_information"
    unknown = "unknown"


# Relation and interaction kinds whose participants commute.  For these the
# participant primitives are sorted before they enter the fingerprint, so
# swapping two colliding bodies does not mint a new cohort; for every other kind
# the authored order is physics and is preserved.
_SYMMETRIC_PARTICIPANT_KINDS: frozenset[str] = frozenset(
    {
        "coincident",
        "collinear",
        "parallel",
        "perpendicular",
        "distance",
        "angle",
        "topology_connects",
        "contact",
        "collision",
        "gear_contact",
        "meshed",
    }
)

# Components that name an axis rather than a magnitude.  A query on one of these
# has to know which axis it means, and the only place the contract types an axis
# identity is a reference frame.
_AXIS_COMPONENTS: frozenset[str] = frozenset(
    {"x", "y", "z", "radial", "transverse", "tangential", "normal"}
)

# Event kinds that name *when* without naming *what condition holds*.  An
# interval ending on one of these has an endpoint the source has not stated.
_UNDERSPECIFIED_ENDPOINT_EVENT_KINDS: frozenset[str] = frozenset(
    {"finish", "other", "reaches_condition"}
)

# Topologies whose contact is one-sided, so which side the body is on decides
# the sign of the normal and therefore the physics.
_UNILATERAL_CONTACT_TOPOLOGIES: frozenset[str] = frozenset(
    {"slides_on", "rolls_on", "contact_with", "moves_in_slot"}
)

# Direction names that are stated in the world and mean nothing about a
# surface- or slope-relative axis until a frame binds them.
_WORLD_DIRECTION_NAMES: frozenset[str] = frozenset(
    {"upward", "downward", "left", "right", "positive", "negative"}
)

# Primitives that own no free body, so a force or moment query about one needs
# the interaction named before any law can write its equation.
_NON_FREE_BODY_QUERY_OWNERS: frozenset[str] = frozenset({"system", "joint", "pulley"})

_FORCE_LIKE_QUERY_ROLES: frozenset[str] = frozenset({"force", "moment", "torque"})


def _payload(value: Any) -> dict[str, Any]:
    # A rejected projection carries no Draft at all.  That is a real structural
    # class, not an error: it becomes the empty payload, which fingerprints as
    # `query=absent` and requires no carrier, so it is counted rather than
    # crashing the census or being silently dropped from the partition.
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return value.model_dump(mode="json", warnings="none")


def _text(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, Mapping):
        return "present"
    return str(getattr(value, "value", value))


def _multiset_tokens(prefix: str, values: Iterable[str]) -> list[str]:
    """`prefix=value*count` per distinct value, so the multiset is order-free."""

    counts = Counter(values)
    return [f"{prefix}={value}*{count}" for value, count in sorted(counts.items())]


# ---------------------------------------------------------------------------
# The structural cohort fingerprint
# ---------------------------------------------------------------------------


class StructuralCohortV1(FrozenStrictModel):
    """One context's structure, as a canonical token set and its digest."""

    version: str = AUTHORITY_CENSUS_VERSION
    digest: _Digest
    tokens: tuple[_Token, ...] = Field(default=(), max_length=512)


def structural_cohort(draft: Any) -> StructuralCohortV1:
    """Partition key for one projected Draft, from typed structure alone.

    Every token is an enum value, a structural presence flag, or a count.  No
    token carries an identifier, a label, a unit, a numeric value, or any text
    the source authored, so two contexts share a digest exactly when they share
    a physical structure.
    """

    payload = _payload(draft)
    primitive_by_entity = {
        item["entity_id"]: item.get("primitive") or "unresolved"
        for item in payload.get("entities") or []
    }
    frame_ids = {
        frame["frame_id"] for frame in payload.get("reference_frames") or []
    }
    event_kind_by_id = {
        event["event_id"]: event.get("kind") or "other"
        for event in payload.get("events") or []
    }

    tokens: list[str] = []

    # --- the question ------------------------------------------------------
    queries: Sequence[dict[str, Any]] = payload.get("queries") or []
    if not queries:
        tokens.append("query=absent")
    else:
        target = queries[0]["target"]
        tokens.append(f"query.role={_text(target.get('role'))}")
        tokens.append(f"query.component={_text(target.get('component'))}")
        tokens.append(
            "query.subject_primitive="
            + primitive_by_entity.get(target.get("subject_id"), "unresolved")
        )
        tokens.append(
            "query.point=" + ("bound" if target.get("point_id") else "unbound")
        )
        tokens.append(
            "query.frame=" + ("bound" if target.get("frame_id") else "unbound")
        )
        tokens.append(
            "query.interval=" + ("bound" if target.get("interval_id") else "unbound")
        )
        event_id = target.get("event_id")
        tokens.append(
            "query.event="
            + (event_kind_by_id.get(event_id, "unresolved") if event_id else "unbound")
        )
        tokens.append(
            "query.direction=" + ("bound" if target.get("direction") else "unbound")
        )
        tokens.append(f"query.objective={_text(queries[0].get('objective'))}")
        tokens.append(f"query.shape={_text(queries[0].get('shape'))}")

    # --- what exists -------------------------------------------------------
    tokens.extend(
        _multiset_tokens("entity", (str(value) for value in primitive_by_entity.values()))
    )
    tokens.extend(
        _multiset_tokens(
            "frame",
            (
                _text(frame.get("frame_type"))
                for frame in payload.get("reference_frames") or []
            ),
        )
    )

    # --- how it is connected ----------------------------------------------
    topology: list[str] = []
    for relation in payload.get("geometry") or []:
        kind = _text(relation.get("kind"))
        participants = [
            primitive_by_entity.get(item, "unresolved")
            for item in relation.get("participant_ids") or []
        ]
        if kind in _SYMMETRIC_PARTICIPANT_KINDS:
            participants = sorted(participants)
        scope = "interval" if relation.get("interval_id") else "timeless"
        topology.append(f"{kind}({','.join(participants)})@{scope}")
    tokens.extend(_multiset_tokens("topology", topology))

    interactions: list[str] = []
    for interaction in payload.get("interactions") or []:
        kind = _text(interaction.get("kind"))
        participants = [
            primitive_by_entity.get(item, "unresolved")
            for item in interaction.get("participant_ids") or []
        ]
        if kind in _SYMMETRIC_PARTICIPANT_KINDS:
            participants = sorted(participants)
        side = _text(interaction.get("contact_side"))
        interactions.append(f"{kind}({','.join(participants)})/side={side}")
    tokens.extend(_multiset_tokens("interaction", interactions))

    tokens.extend(
        _multiset_tokens(
            "constraint",
            (
                f"{_text(item.get('kind'))}@"
                + ("event" if item.get("event_id") else
                   "interval" if item.get("interval_id") else "timeless")
                for item in payload.get("constraints") or []
            ),
        )
    )
    tokens.extend(
        _multiset_tokens(
            "state_condition",
            (
                f"{_text(item.get('kind'))}:{_text(item.get('state'))}"
                for item in payload.get("state_conditions") or []
            ),
        )
    )

    # --- when --------------------------------------------------------------
    tokens.extend(
        _multiset_tokens(
            "event",
            (
                _text(event.get("kind"))
                for event in payload.get("events") or []
            ),
        )
    )
    intervals = payload.get("motion_intervals") or []
    bounded = sum(
        1
        for interval in intervals
        if interval.get("start_event_id") and interval.get("end_event_id")
    )
    tokens.append(f"interval.bounded={bounded}")
    tokens.append(f"interval.unbounded={len(intervals) - bounded}")
    tokens.extend(
        _multiset_tokens(
            "interval.frame",
            (
                "bound" if interval.get("frame_id") in frame_ids else "unbound"
                for interval in intervals
            ),
        )
    )

    # --- what is stated about it ------------------------------------------
    quantity_tokens: list[str] = []
    direction_tokens: list[str] = []
    for quantity in payload.get("quantities") or []:
        scope = (
            "event"
            if quantity.get("event_id")
            else "interval"
            if quantity.get("interval_id")
            else "timeless"
        )
        quantity_tokens.append(
            f"{_text(quantity.get('role'))}"
            f"/{_text(quantity.get('component'))}"
            f"@{scope}"
            f"/frame=" + ("bound" if quantity.get("frame_id") else "unbound")
            + "/valued=" + ("yes" if quantity.get("raw_value") is not None else "no")
        )
        direction = quantity.get("direction")
        if direction:
            direction_payload = (
                direction if isinstance(direction, Mapping) else _payload(direction)
            )
            direction_tokens.append(
                f"{_text(direction_payload.get('kind'))}"
                f"/axis={_text(direction_payload.get('axis'))}"
                f"/frame=" + ("bound" if direction_payload.get("frame_id") else "unbound")
            )
    tokens.extend(_multiset_tokens("quantity", quantity_tokens))
    tokens.extend(_multiset_tokens("direction", direction_tokens))

    tokens.extend(
        _multiset_tokens(
            "assumption",
            (
                f"{_text(item.get('kind'))}/{_text(item.get('disposition'))}"
                for item in payload.get("assumptions") or []
            ),
        )
    )

    canonical = tuple(sorted(tokens))
    material = ("\0".join((_FINGERPRINT_SALT, *canonical))).encode("utf-8")
    return StructuralCohortV1(
        digest=hashlib.sha256(material).hexdigest(), tokens=canonical
    )


# ---------------------------------------------------------------------------
# Which carriers this context needs, and which it has
# ---------------------------------------------------------------------------


def required_carriers(draft: Any) -> tuple[SourceCarrierCategory, ...]:
    """The carriers this context's own typed structure obliges a closure to read.

    Derived from the contract, not from a physics judgement: each rule asks only
    whether a typed field the engine consumes has been left without the record
    that gives it meaning.

    Every rule is scoped to the **query's own resolution path**.  An earlier
    draft of this function asked the weaker question — "does this structure
    mention anything an endpoint carrier could describe?" — and reported a
    missing endpoint on 26 of the 41 contexts that go on to verify a correct
    answer.  A carrier 26 solves do without is not what is blocking the other
    40, and reporting it as such would have made the census agree with the
    document by inflating both sides.  A rule that fires on a solved context is
    a rule that is measuring the wrong thing.
    """

    payload = _payload(draft)
    required: set[SourceCarrierCategory] = set()

    primitive_by_entity = {
        item["entity_id"]: item.get("primitive") or "unresolved"
        for item in payload.get("entities") or []
    }
    queries: Sequence[dict[str, Any]] = payload.get("queries") or []
    quantities: Sequence[dict[str, Any]] = payload.get("quantities") or []
    frames = payload.get("reference_frames") or []
    topology_kinds = {
        _text(relation.get("kind")) for relation in payload.get("geometry") or []
    }
    angle_relation_participants = {
        len(relation.get("participant_ids") or [])
        for relation in payload.get("geometry") or []
        if _text(relation.get("kind")) == "angle"
    }
    event_kinds_by_id = {
        event["event_id"]: _text(event.get("kind"))
        for event in payload.get("events") or []
    }
    # Events something is actually stated *at*: a condition, or any quantity
    # scoped to that instant.  An endpoint with one of these is defined.
    described_events: set[str] = {
        condition["event_id"]
        for condition in payload.get("state_conditions") or []
        if condition.get("event_id")
    }
    described_events.update(
        quantity["event_id"]
        for quantity in quantities
        if quantity.get("event_id") and quantity.get("raw_value") is not None
    )
    assumption_kinds = {
        _text(item.get("kind")) for item in payload.get("assumptions") or []
    }

    if queries:
        target = queries[0]["target"]
        component = _text(target.get("component"))
        if component in _AXIS_COMPONENTS and not frames:
            # The answer is asked for along an axis, and only a frame types an
            # axis identity.  Restricted to the query: a component on some
            # other quantity may never reach the answer at all.
            required.add(SourceCarrierCategory.reference_frame)
        role = _text(target.get("role"))
        subject_primitive = primitive_by_entity.get(
            target.get("subject_id"), "unresolved"
        )
        if (
            role in _FORCE_LIKE_QUERY_ROLES
            and subject_primitive in _NON_FREE_BODY_QUERY_OWNERS
        ):
            required.add(SourceCarrierCategory.interaction_target)
        query_event = target.get("event_id")
        if (
            query_event
            and event_kinds_by_id.get(query_event)
            in _UNDERSPECIFIED_ENDPOINT_EVENT_KINDS
            and query_event not in described_events
        ):
            # The answer is asked *at* a moment the source names but does not
            # define, and nothing states what holds there.
            required.add(SourceCarrierCategory.endpoint_condition)

    for quantity in quantities:
        role = _text(quantity.get("role"))
        if role == "angle" and not frames and angle_relation_participants <= {0, 1}:
            # An angle is a value between two directions.  With no frame and no
            # angle relation naming two participants, neither is stated.
            required.add(SourceCarrierCategory.angle_reference_datum)
        direction = quantity.get("direction")
        if not direction:
            continue
        direction_payload = (
            direction if isinstance(direction, Mapping) else _payload(direction)
        )
        name = _text(direction_payload.get("name"))
        frame_bound = bool(direction_payload.get("frame_id"))
        if (
            name in _WORLD_DIRECTION_NAMES
            and not frame_bound
            and topology_kinds & _UNILATERAL_CONTACT_TOPOLOGIES
        ):
            # A world direction beside a slope says nothing about the tangent
            # the body actually moves along.
            required.add(SourceCarrierCategory.motion_sense)
        raw_value = quantity.get("raw_value")
        if (
            isinstance(raw_value, (int, float))
            and not isinstance(raw_value, bool)
            and raw_value < 0
            and name not in {"none", "unspecified"}
        ):
            # A negative magnitude beside a stated direction is the same scalar
            # encoded twice, and the two encodings disagree.
            required.add(SourceCarrierCategory.signed_scalar_encoding)

    for interaction in payload.get("interactions") or []:
        if _text(interaction.get("kind")) != "contact":
            continue
        if interaction.get("contact_side") is None and (
            topology_kinds & _UNILATERAL_CONTACT_TOPOLOGIES
        ):
            required.add(SourceCarrierCategory.contact_side)

    if topology_kinds & {"rolls_on", "wraps", "meshed"}:
        stated = {
            _text(item.get("kind")) for item in payload.get("constraints") or []
        }
        # An approved assumption states the constraint as surely as a
        # constraint record does; the corpus authors most of them that way.
        if not stated & {"rolling", "rope", "kinematic", "geometric"} and not (
            assumption_kinds
            & {
                "pure_rolling",
                "rolling_without_slipping",
                "inextensible_rope",
                "massless_rope",
            }
        ):
            required.add(SourceCarrierCategory.constraint_authority)

    return tuple(sorted(required, key=lambda item: item.value))


def available_carriers(draft: Any) -> tuple[SourceCarrierCategory, ...]:
    """The carriers this context's source actually states.

    A carrier counts as available only when a record supplies it — never when
    a default, an absence, or a name that resembles it could be read that way.
    """

    payload = _payload(draft)
    available: set[SourceCarrierCategory] = set()

    frames = payload.get("reference_frames") or []
    frame_ids = {frame["frame_id"] for frame in frames}
    if frames:
        available.add(SourceCarrierCategory.reference_frame)
        if any(
            axis.get("direction") for frame in frames for axis in frame.get("axes") or []
        ):
            available.add(SourceCarrierCategory.angle_reference_datum)

    for quantity in payload.get("quantities") or []:
        direction = quantity.get("direction")
        if not direction:
            continue
        direction_payload = (
            direction if isinstance(direction, Mapping) else _payload(direction)
        )
        if direction_payload.get("frame_id") in frame_ids and direction_payload.get(
            "axis"
        ):
            # Bound to a named axis of a stated frame: that is a sense, not a
            # world word that happens to sound like one.
            available.add(SourceCarrierCategory.motion_sense)
            available.add(SourceCarrierCategory.signed_scalar_encoding)

    for interaction in payload.get("interactions") or []:
        if interaction.get("contact_side") is not None:
            available.add(SourceCarrierCategory.contact_side)
        if len(interaction.get("participant_ids") or []) >= 2:
            available.add(SourceCarrierCategory.interaction_target)

    condition_events = {
        condition.get("event_id")
        for condition in payload.get("state_conditions") or []
        if condition.get("event_id")
    }
    if condition_events:
        available.add(SourceCarrierCategory.endpoint_condition)

    if payload.get("constraints"):
        available.add(SourceCarrierCategory.constraint_authority)

    return tuple(sorted(available, key=lambda item: item.value))


def missing_carriers(draft: Any) -> tuple[SourceCarrierCategory, ...]:
    """Required minus available: what a closure would have to invent."""

    have = frozenset(available_carriers(draft))
    return tuple(item for item in required_carriers(draft) if item not in have)


# ---------------------------------------------------------------------------
# How far a context actually got
# ---------------------------------------------------------------------------

_NEUTRAL_TERMINALS: frozenset[str] = frozenset(
    {
        "needs_figure",
        "needs_confirmation",
        "insufficient_information",
        "verified_unsupported",
        "compiler_unsupported",
    }
)


def progress_rung(result: Any) -> ProgressRung:
    """Where one lane result stopped, on the ladder.

    A law that emitted is separated from a graph that closed, and a graph that
    closed is separated from a verified solve.  Collapsing any of those three
    would let a counterfactual that only made an emitter fire be reported as a
    closure.
    """

    terminal = _text(getattr(result, "terminal", None))
    if terminal == "projection_rejected":
        return ProgressRung.projection_rejected
    if terminal in _NEUTRAL_TERMINALS:
        return ProgressRung.blocked_neutral_terminal
    if terminal == "validation_rejected":
        return ProgressRung.validation_rejected
    if terminal == "normalization_rejected":
        return ProgressRung.normalization_rejected
    if terminal == "authorization_failed":
        return ProgressRung.authorization_failed
    if terminal == "solved":
        return (
            ProgressRung.solved_and_verified
            if getattr(result, "verified_candidate_count", 0) > 0
            else ProgressRung.solved_unverified
        )
    if terminal == "verification_rejected":
        return ProgressRung.solved_unverified
    if terminal == "solve_rejected":
        return ProgressRung.graph_determined_solve_failed
    # Everything left is a compiler stop.  An equation-free graph means no law
    # wrote anything; equations without a determination means laws wrote and
    # the system is still short.
    if getattr(result, "equation_count", 0) > 0 or getattr(
        result, "applied_law_ids", ()
    ):
        return ProgressRung.law_emitted_graph_underdetermined
    return ProgressRung.law_not_emitted


# ---------------------------------------------------------------------------
# The census
# ---------------------------------------------------------------------------


class CarrierCounterfactualV1(FrozenStrictModel):
    """What supplying one carrier actually bought, measured on the ladder.

    The only honest way to say a cohort is blocked on a carrier: supply that
    carrier and nothing else, re-run the real pipeline, and report the rung
    before and the rung after.  `unblocked` is deliberately not "the emitter
    fired" — it is a strict rise on the ladder, and `closes` is stricter still.
    """

    carrier: SourceCarrierCategory
    rung_before: ProgressRung
    rung_after: ProgressRung

    @property
    def unblocked(self) -> bool:
        """The carrier moved the context strictly further along the pipeline."""

        return rung_index(self.rung_after) > rung_index(self.rung_before)

    @property
    def closes(self) -> bool:
        """The carrier took the context all the way to a verified solve."""

        return self.rung_after is ProgressRung.solved_and_verified

    @property
    def regressed(self) -> bool:
        """The carrier moved the context backwards, which is a defect."""

        return rung_index(self.rung_after) < rung_index(self.rung_before)


def measure_carrier_counterfactual(
    *,
    carrier: SourceCarrierCategory,
    baseline_result: Any,
    augmented_result: Any,
) -> CarrierCounterfactualV1:
    """One rung-to-rung counterfactual for one carrier.

    Both results must come from the *same* pipeline over the *same* context,
    differing only by the carrier under test.  The caller owns that discipline;
    this function only reads the two rungs, so it cannot be talked into
    reporting a rise that a different pipeline produced.
    """

    return CarrierCounterfactualV1(
        carrier=carrier,
        rung_before=progress_rung(baseline_result),
        rung_after=progress_rung(augmented_result),
    )


class AuthorityContextV1(FrozenStrictModel):
    """One context's census row.  Privacy-safe by construction."""

    cohort_digest: _Digest
    expected_class: ExpectedClass
    rung: ProgressRung
    runtime_terminal: _Token
    compiler_status: _Token = "none"
    solve_terminal: _Token = "none"
    verified_candidate_count: int = 0
    equation_count: int = 0
    required_carriers: tuple[SourceCarrierCategory, ...] = ()
    available_carriers: tuple[SourceCarrierCategory, ...] = ()
    missing_carriers: tuple[SourceCarrierCategory, ...] = ()

    @property
    def solved(self) -> bool:
        return self.rung is ProgressRung.solved_and_verified

    @property
    def reference_frame_dependent(self) -> bool:
        return SourceCarrierCategory.reference_frame in self.missing_carriers

    @property
    def authority_blocked(self) -> bool:
        """Expected to be supported, does not solve, and needs a missing carrier."""

        return (
            self.expected_class is ExpectedClass.supported
            and not self.solved
            and bool(self.missing_carriers)
        )

    @property
    def closure_candidate(self) -> bool:
        """Expected to be supported, does not solve, and nothing is missing.

        A **candidate**, not a closure.  It says the structural reading found
        no missing carrier, which makes this context worth investigating under
        the v1 contract — and says nothing about whether a law exists that
        could close it.  Promoting a candidate to a package requires the
        counterfactual measurement, not this flag.
        """

        return (
            self.expected_class is ExpectedClass.supported
            and not self.solved
            and not self.missing_carriers
        )

    @property
    def carrier_hypothesis_false_positive(self) -> bool:
        """Solved, yet the structural reading called a carrier missing.

        The census's own negative control.  Every one of these is a context
        that reached a verified answer without the carrier the reading says it
        needs, so the reading is over-firing there.  It is reported rather than
        tuned away: a rule adjusted until this count reached zero would have
        been fitted to the outcome it is supposed to explain.
        """

        return self.solved and bool(self.missing_carriers)


class CohortSummaryV1(FrozenStrictModel):
    """One structural cohort, as counts."""

    cohort_digest: _Digest
    population: int
    solved: int
    supported_unsolved: int
    closure_candidates: int
    authority_blocked: int
    reference_frame_dependent: int
    rung_counts: tuple[tuple[str, int], ...] = ()
    missing_carrier_counts: tuple[tuple[str, int], ...] = ()
    expected_class_counts: tuple[tuple[str, int], ...] = ()


class AuthorityCensusV1(FrozenStrictModel):
    """The whole partition, as counts over a closed vocabulary."""

    version: str = AUTHORITY_CENSUS_VERSION
    context_count: int = 0
    supported_expected: int = 0
    supported_solved: int = 0
    supported_unsolved: int = 0
    deferred: int = 0
    blocked_neutral: int = 0
    cohort_count: int = 0
    supported_unsolved_cohort_count: int = 0
    closure_candidate_count: int = 0
    authority_blocked_count: int = 0
    # The census's negative control: solved contexts the structural reading
    # nevertheless calls carrier-short.  A non-zero value bounds how much the
    # reading over-fires and is published rather than tuned away.
    carrier_hypothesis_false_positive_count: int = 0
    reference_frame_dependent_count: int = 0
    reference_frame_dependent_cohort_count: int = 0
    rung_counts: tuple[tuple[str, int], ...] = ()
    runtime_terminal_counts: tuple[tuple[str, int], ...] = ()
    compiler_status_counts: tuple[tuple[str, int], ...] = ()
    solve_terminal_counts: tuple[tuple[str, int], ...] = ()
    expected_class_counts: tuple[tuple[str, int], ...] = ()
    required_carrier_counts: tuple[tuple[str, int], ...] = ()
    available_carrier_counts: tuple[tuple[str, int], ...] = ()
    missing_carrier_counts: tuple[tuple[str, int], ...] = ()
    cohorts: tuple[CohortSummaryV1, ...] = Field(default=(), max_length=256)

    @property
    def digest(self) -> str:
        """A deterministic digest of the whole census, for report attribution."""

        material = repr(self.model_dump(mode="json")).encode("utf-8")
        return hashlib.sha256(material).hexdigest()


def _sorted_counts(counter: Counter[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(counter.items()))


def build_authority_context(
    draft: Any,
    result: Any,
    *,
    expected_class: ExpectedClass = ExpectedClass.unknown,
) -> AuthorityContextV1:
    """One census row from one projected Draft and its lane result."""

    return AuthorityContextV1(
        cohort_digest=structural_cohort(draft).digest,
        expected_class=expected_class,
        rung=progress_rung(result),
        runtime_terminal=_text(getattr(result, "terminal", None)),
        compiler_status=_text(getattr(result, "compiler_status", None)),
        solve_terminal=_text(getattr(result, "solve_terminal", None)),
        verified_candidate_count=int(getattr(result, "verified_candidate_count", 0)),
        equation_count=int(getattr(result, "equation_count", 0)),
        required_carriers=required_carriers(draft),
        available_carriers=available_carriers(draft),
        missing_carriers=missing_carriers(draft),
    )


def build_authority_census(
    contexts: Iterable[AuthorityContextV1],
) -> AuthorityCensusV1:
    """Aggregate census rows into the published partition."""

    rows = tuple(contexts)
    by_cohort: dict[str, list[AuthorityContextV1]] = {}
    for row in rows:
        by_cohort.setdefault(row.cohort_digest, []).append(row)

    rungs: Counter[str] = Counter()
    terminals: Counter[str] = Counter()
    compiler: Counter[str] = Counter()
    solve: Counter[str] = Counter()
    expected: Counter[str] = Counter()
    required: Counter[str] = Counter()
    available: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    for row in rows:
        rungs[row.rung.value] += 1
        terminals[row.runtime_terminal] += 1
        compiler[row.compiler_status] += 1
        solve[row.solve_terminal] += 1
        expected[row.expected_class.value] += 1
        for item in row.required_carriers:
            required[item.value] += 1
        for item in row.available_carriers:
            available[item.value] += 1
        for item in row.missing_carriers:
            missing[item.value] += 1

    summaries: list[CohortSummaryV1] = []
    for digest in sorted(by_cohort):
        members = by_cohort[digest]
        cohort_rungs: Counter[str] = Counter()
        cohort_missing: Counter[str] = Counter()
        cohort_expected: Counter[str] = Counter()
        for row in members:
            cohort_rungs[row.rung.value] += 1
            cohort_expected[row.expected_class.value] += 1
            for item in row.missing_carriers:
                cohort_missing[item.value] += 1
        summaries.append(
            CohortSummaryV1(
                cohort_digest=digest,
                population=len(members),
                solved=sum(1 for row in members if row.solved),
                supported_unsolved=sum(
                    1
                    for row in members
                    if row.expected_class is ExpectedClass.supported and not row.solved
                ),
                closure_candidates=sum(1 for row in members if row.closure_candidate),
                authority_blocked=sum(1 for row in members if row.authority_blocked),
                reference_frame_dependent=sum(
                    1 for row in members if row.reference_frame_dependent
                ),
                rung_counts=_sorted_counts(cohort_rungs),
                missing_carrier_counts=_sorted_counts(cohort_missing),
                expected_class_counts=_sorted_counts(cohort_expected),
            )
        )

    supported_unsolved_rows = [
        row
        for row in rows
        if row.expected_class is ExpectedClass.supported and not row.solved
    ]
    return AuthorityCensusV1(
        context_count=len(rows),
        supported_expected=sum(
            1 for row in rows if row.expected_class is ExpectedClass.supported
        ),
        supported_solved=sum(
            1
            for row in rows
            if row.expected_class is ExpectedClass.supported and row.solved
        ),
        supported_unsolved=len(supported_unsolved_rows),
        deferred=sum(1 for row in rows if row.expected_class is ExpectedClass.deferred),
        blocked_neutral=sum(
            1 for row in rows if row.rung is ProgressRung.blocked_neutral_terminal
        ),
        cohort_count=len(by_cohort),
        supported_unsolved_cohort_count=len(
            {row.cohort_digest for row in supported_unsolved_rows}
        ),
        closure_candidate_count=sum(1 for row in rows if row.closure_candidate),
        authority_blocked_count=sum(1 for row in rows if row.authority_blocked),
        carrier_hypothesis_false_positive_count=sum(
            1 for row in rows if row.carrier_hypothesis_false_positive
        ),
        reference_frame_dependent_count=sum(
            1 for row in supported_unsolved_rows if row.reference_frame_dependent
        ),
        reference_frame_dependent_cohort_count=len(
            {
                row.cohort_digest
                for row in supported_unsolved_rows
                if row.reference_frame_dependent
            }
        ),
        rung_counts=_sorted_counts(rungs),
        runtime_terminal_counts=_sorted_counts(terminals),
        compiler_status_counts=_sorted_counts(compiler),
        solve_terminal_counts=_sorted_counts(solve),
        expected_class_counts=_sorted_counts(expected),
        required_carrier_counts=_sorted_counts(required),
        available_carrier_counts=_sorted_counts(available),
        missing_carrier_counts=_sorted_counts(missing),
        cohorts=tuple(summaries),
    )


def census_as_dict(census: AuthorityCensusV1) -> dict[str, Any]:
    """The census as plain JSON for the redacted aggregate artifact."""

    payload = census.model_dump(mode="json")
    payload["digest"] = census.digest
    return payload


__all__ = [
    "AUTHORITY_CENSUS_VERSION",
    "AuthorityCensusV1",
    "AuthorityContextV1",
    "CarrierCounterfactualV1",
    "CohortSummaryV1",
    "ExpectedClass",
    "ProgressRung",
    "SourceCarrierCategory",
    "StructuralCohortV1",
    "available_carriers",
    "build_authority_census",
    "build_authority_context",
    "census_as_dict",
    "measure_carrier_counterfactual",
    "missing_carriers",
    "progress_rung",
    "required_carriers",
    "rung_index",
    "structural_cohort",
]
