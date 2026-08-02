"""Evaluator-only assumption authority for Lane B: exact, immutable, bound.

The engine's own contract for a ``server_default`` quantity is two-keyed: the
assumption must be approved **and** an exact immutable
:class:`~engine.mechanics.validation.AssumptionAuthorization` must accompany it
into ``validate_draft`` and ``normalize_draft``.  Lane B has so far passed only
the approved IDs, which is why ``server_default`` provenance is unreachable
from the evaluator — the ``ENGINE_CONTRACT_BLOCKER`` the structural-blockers
report records.

This module is the missing authority stage.  It sits **between projection and
validation**, outside any complete-profile transaction, and produces one
:class:`LaneBAuthorityBundleV1` per projected Draft:

* the approved assumption IDs, exactly the projection's own;
* an authorization per approved assumption of a **closed value policy** —
  gravity, exact frictionless coefficient, or exact starts-from-rest speed —
  whose proposal matches that policy to the character;
* a fingerprint of the source Draft it was built from; and
* a fingerprint of the bundle itself.

Authorization is not a new source of values.  Every authorized value is the
closed server policy's own constant, already carried by the Draft's approved
assumption record; the bundle merely restates it in the immutable form the
engine demands, so the engine can hold the eventual quantity to it exactly.

Everything else fails closed and is recorded as a bounded refusal code:
an unapproved or out-of-set assumption, an incomplete proposal, an unresolved
subject or interval, a proposal that deviates from the closed policy, a value
or unit outside the bounded grammar, duplicate or competing assumptions for
one physical identity, and a competing stated fact **at the same physical
identity** — the policy's role for the same subject over an overlapping
interval or event scope.  A stated fact for another subject, or for another
interval of this subject, or at an event provably attached only elsewhere,
occupies a different physical identity and refuses nothing; a stated fact
whose scope cannot be proven separate fails closed and still blocks.
An event-scoped default is structurally impossible here — the authorization
record has no event field, and the engine itself refuses any event-scoped
``server_default`` quantity.

The bundle is bound to its Draft: ``verify_lane_b_authority_bundle`` recomputes
both fingerprints, so a bundle replayed against another case, another
revision, another Draft, or a mutated copy of its own Draft verifies false.
Nothing here is wired to the product modeler or API path, and nothing here
reads a case ID, family, split, expected terminal, or expected answer.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from engine.mechanics.contracts import MechanicsProblemDraftV1, QuantityRole
from engine.mechanics.validation import AssumptionAuthorization

from evaluation.phase56_stage7.lane_b_draft_projection import DraftProjection

LANE_B_AUTHORITY_BUNDLE_VERSION = "phase56-stage7-lane-b-authority-bundle-v2"

# The closed value policy: the only assumption kinds whose approval may ground
# a server-valued quantity, and the exact role/value/unit each one is permitted
# to carry.  This mirrors the projection's own server-default set on purpose —
# widening it is a contract change, not a convenience.
_AUTHORITY_VALUE_POLICY: dict[str, tuple[str, str, str]] = {
    "constant_gravity": ("gravity", "9.81", "m/s^2"),
    "frictionless": ("coefficient_friction", "0", ""),
    "starts_from_rest": ("velocity", "0", "m/s"),
}

# The closed role → dimension mapping for authorized values.  A role absent
# here cannot be authorized however the policy table changes, so a policy edit
# that forgets the dimension fails closed instead of authorizing an undimensioned
# number.
_AUTHORITY_ROLE_DIMENSIONS: dict[str, tuple[tuple[str, int], ...]] = {
    "gravity": (("length", 1), ("time", -2)),
    "coefficient_friction": (),
    "velocity": (("length", 1), ("time", -1)),
}

# Bounded canonical grammars.  The policy match is already exact, so these are
# a second, independent wall: a policy table typo cannot smuggle an unbounded
# or non-numeric string into an authorization.
_VALUE_GRAMMAR = re.compile(r"^\d{1,4}(\.\d{1,6})?$")
_UNIT_GRAMMAR = re.compile(r"^[A-Za-z0-9^/*.\-]{1,16}$")


class AuthorityRefusal(str, Enum):
    """Why one approved value-policy assumption was not authorized."""

    proposal_incomplete = "proposal_incomplete"
    subject_unresolved = "subject_unresolved"
    interval_unresolved = "interval_unresolved"
    policy_mismatch = "policy_mismatch"
    grammar_rejected = "grammar_rejected"
    role_not_in_closed_mapping = "role_not_in_closed_mapping"
    duplicate_identity = "duplicate_identity"
    competing_value_identity = "competing_value_identity"
    competing_stated_fact = "competing_stated_fact"


class LaneBAuthorityError(Exception):
    """The projection and its Draft disagree; no authority can be issued."""


# Provenances that already state a number for a role.  A server default must
# never stand beside one of these at the same physical identity: the stated
# fact wins and the authorization is simply not issued.
_STATED_PROVENANCES: frozenset[str] = frozenset(
    {"explicit_source", "user_correction", "server_default"}
)


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _event_interval_reach(
    draft: MechanicsProblemDraftV1,
) -> Mapping[str, frozenset[str]]:
    """Which intervals each event provably touches: membership, occupancy,
    and boundary.

    ``Event.interval_ids`` is the event's own declared membership,
    ``Event.occurs_in_interval_ids`` its proven interior occupancy, and an
    interval whose ``start_event_id``/``end_event_id`` names the event
    touches it from the interval side.  All three are typed source
    structure — nothing here reads raw text.
    """

    reach: dict[str, set[str]] = {
        event.event_id: set(event.interval_ids)
        | set(event.occurs_in_interval_ids)
        for event in draft.events
    }
    for interval in draft.motion_intervals:
        for boundary in (interval.start_event_id, interval.end_event_id):
            if boundary is not None and boundary in reach:
                reach[boundary].add(interval.interval_id)
    return {event_id: frozenset(items) for event_id, items in reach.items()}


def _stated_fact_competes(
    quantity: object,
    *,
    role: str,
    subject_id: str,
    interval_id: str | None,
    event_interval_reach: Mapping[str, frozenset[str]],
) -> bool:
    """Whether one stated quantity occupies the authorization's physical identity.

    The identity of the closed gravity policy is (role, subject, interval/event
    scope).  Component and frame deliberately do not separate competitors: the
    role is a magnitude invariant, so a stated gravity in any dress still
    states this subject's gravity here.  A role whose physical identity did
    include a component would need its own scope rule before it could enter
    the policy table.

    Scope that cannot be proven separate fails closed: an authorization bound
    to no interval claims every interval, an unscoped stated fact states its
    value for every interval, and a dangling or attachment-free event
    reference proves no separation.
    """

    if str(_enum_value(quantity.role)) != role:
        return False
    if quantity.subject_id != subject_id:
        return False
    if interval_id is None:
        return True
    if quantity.interval_id == interval_id:
        return True
    event_id = quantity.event_id
    if event_id is not None:
        reach = event_interval_reach.get(event_id)
        if reach is None:
            return True
        if interval_id in reach:
            return True
        if reach:
            # The event provably belongs to other intervals only.
            return False
        return quantity.interval_id is None
    return quantity.interval_id is None


def draft_fingerprint(draft: MechanicsProblemDraftV1) -> str:
    """The exact revision this authority speaks for, as one hash."""

    payload = draft.model_dump_json().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bundle_fingerprint(
    *,
    version: str,
    source_draft_fingerprint: str,
    approved_assumption_ids: tuple[str, ...],
    authorized_assumptions: tuple[tuple[str, AssumptionAuthorization], ...],
    refusals: tuple[tuple[str, str], ...],
) -> str:
    parts: list[str] = [version, source_draft_fingerprint]
    parts.extend(approved_assumption_ids)
    for key, authorization in authorized_assumptions:
        parts.append(
            "\x1f".join(
                (
                    key,
                    authorization.assumption_id,
                    authorization.subject_id,
                    str(authorization.role),
                    authorization.raw_value,
                    authorization.raw_unit,
                    authorization.interval_id or "",
                )
            )
        )
    for assumption_id, refusal in refusals:
        parts.append(f"{assumption_id}\x1f{refusal}")
    material = "\x00".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class LaneBAuthorityBundleV1:
    """One Draft's exact assumption authority, immutable and fingerprinted."""

    version: str
    source_draft_fingerprint: str
    approved_assumption_ids: tuple[str, ...]
    authorized_assumptions: tuple[tuple[str, AssumptionAuthorization], ...]
    refusals: tuple[tuple[str, str], ...]
    authority_fingerprint: str

    def authorization_map(self) -> Mapping[str, AssumptionAuthorization]:
        """The immutable mapping both ``validate_draft`` and ``normalize_draft`` get.

        A read-only proxy over a fresh dict: a caller can neither mutate the
        bundle through it nor mutate it at all.
        """

        return MappingProxyType(dict(self.authorized_assumptions))


def build_lane_b_authority_bundle(
    projection: DraftProjection,
) -> LaneBAuthorityBundleV1:
    """The authority stage: projection in, one exact immutable bundle out.

    Runs after projection and before validation, never inside a
    complete-profile transaction.  Raises :class:`LaneBAuthorityError` when the
    projection carries no Draft or its approvable set disagrees with the
    Draft's own approved dispositions — an internal inconsistency no authority
    may paper over.
    """

    draft = projection.draft
    if draft is None:
        raise LaneBAuthorityError("a bundle needs a projected draft")

    approvable = frozenset(projection.approvable_assumption_ids)
    approved_records = tuple(
        assumption
        for assumption in draft.assumptions
        if _enum_value(assumption.disposition) == "approved"
    )
    approved_ids = frozenset(item.assumption_id for item in approved_records)
    if approved_ids != approvable:
        raise LaneBAuthorityError(
            "the projection's approvable set and the draft's approved dispositions disagree"
        )

    entity_ids = frozenset(item.entity_id for item in draft.entities)
    interval_ids = frozenset(item.interval_id for item in draft.motion_intervals)

    # Quantities for which the Draft already states a number, from any
    # provenance that carries one.  A server default never stands beside a
    # stated fact *at the same physical identity* — judged per candidate below
    # against the candidate's own subject and interval/event scope, never
    # against the role alone.
    stated_quantities = tuple(
        quantity
        for quantity in draft.quantities
        if _enum_value(quantity.provenance) in _STATED_PROVENANCES
        and quantity.raw_value is not None
    )
    event_reach = _event_interval_reach(draft)

    candidates = tuple(
        item for item in approved_records if item.kind in _AUTHORITY_VALUE_POLICY
    )
    identity_counts: dict[tuple[str, str, str | None], int] = {}
    value_identity_counts: dict[tuple[str, str, str | None], int] = {}
    for item in candidates:
        identity = (item.kind, item.subject_id, item.interval_id)
        identity_counts[identity] = identity_counts.get(identity, 0) + 1
        role = _AUTHORITY_VALUE_POLICY[item.kind][0]
        value_identity = (role, item.subject_id, item.interval_id)
        value_identity_counts[value_identity] = (
            value_identity_counts.get(value_identity, 0) + 1
        )

    authorized: list[tuple[str, AssumptionAuthorization]] = []
    refusals: list[tuple[str, str]] = []
    for item in candidates:
        policy_role, policy_value, policy_unit = _AUTHORITY_VALUE_POLICY[item.kind]
        refusal: AuthorityRefusal | None = None
        if identity_counts[(item.kind, item.subject_id, item.interval_id)] > 1:
            refusal = AuthorityRefusal.duplicate_identity
        elif (
            value_identity_counts[(policy_role, item.subject_id, item.interval_id)]
            > 1
        ):
            refusal = AuthorityRefusal.competing_value_identity
        elif (
            item.proposed_role is None
            or item.proposed_value is None
            or item.proposed_unit is None
        ):
            refusal = AuthorityRefusal.proposal_incomplete
        elif item.subject_id not in entity_ids:
            refusal = AuthorityRefusal.subject_unresolved
        elif item.interval_id is not None and item.interval_id not in interval_ids:
            refusal = AuthorityRefusal.interval_unresolved
        elif (
            str(_enum_value(item.proposed_role)) != policy_role
            or item.proposed_value != policy_value
            or item.proposed_unit != policy_unit
        ):
            refusal = AuthorityRefusal.policy_mismatch
        elif not _VALUE_GRAMMAR.fullmatch(policy_value) or not (
            _UNIT_GRAMMAR.fullmatch(policy_unit)
            or (
                policy_unit == ""
                and _AUTHORITY_ROLE_DIMENSIONS.get(policy_role) == ()
            )
        ):
            refusal = AuthorityRefusal.grammar_rejected
        elif (
            policy_role not in _AUTHORITY_ROLE_DIMENSIONS
            or policy_role not in {role.value for role in QuantityRole}
        ):
            refusal = AuthorityRefusal.role_not_in_closed_mapping
        elif any(
            _stated_fact_competes(
                quantity,
                role=policy_role,
                subject_id=item.subject_id,
                interval_id=item.interval_id,
                event_interval_reach=event_reach,
            )
            for quantity in stated_quantities
        ):
            refusal = AuthorityRefusal.competing_stated_fact

        if refusal is not None:
            refusals.append((item.assumption_id, refusal.value))
            continue
        authorized.append(
            (
                item.assumption_id,
                AssumptionAuthorization(
                    assumption_id=item.assumption_id,
                    subject_id=item.subject_id,
                    role=policy_role,
                    raw_value=policy_value,
                    raw_unit=policy_unit,
                    interval_id=item.interval_id,
                ),
            )
        )

    approved_sorted = tuple(sorted(approved_ids))
    authorized_sorted = tuple(sorted(authorized, key=lambda pair: pair[0]))
    refusals_sorted = tuple(sorted(refusals))
    source_fingerprint = draft_fingerprint(draft)
    return LaneBAuthorityBundleV1(
        version=LANE_B_AUTHORITY_BUNDLE_VERSION,
        source_draft_fingerprint=source_fingerprint,
        approved_assumption_ids=approved_sorted,
        authorized_assumptions=authorized_sorted,
        refusals=refusals_sorted,
        authority_fingerprint=_bundle_fingerprint(
            version=LANE_B_AUTHORITY_BUNDLE_VERSION,
            source_draft_fingerprint=source_fingerprint,
            approved_assumption_ids=approved_sorted,
            authorized_assumptions=authorized_sorted,
            refusals=refusals_sorted,
        ),
    )


def verify_lane_b_authority_bundle(
    bundle: object, draft: MechanicsProblemDraftV1
) -> bool:
    """Exactly this bundle, for exactly this Draft — or nothing.

    Recomputes both fingerprints and re-checks every structural invariant, so
    a forged bundle, a mutated bundle, a mismatched key, a wrong record type,
    or a bundle built from any other Draft or revision all verify false.
    """

    if type(bundle) is not LaneBAuthorityBundleV1:
        return False
    if bundle.version != LANE_B_AUTHORITY_BUNDLE_VERSION:
        return False
    if bundle.source_draft_fingerprint != draft_fingerprint(draft):
        return False
    for key, authorization in bundle.authorized_assumptions:
        if type(authorization) is not AssumptionAuthorization:
            return False
        if key != authorization.assumption_id:
            return False
        if key not in bundle.approved_assumption_ids:
            return False
    recomputed = _bundle_fingerprint(
        version=bundle.version,
        source_draft_fingerprint=bundle.source_draft_fingerprint,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorized_assumptions,
        refusals=bundle.refusals,
    )
    return recomputed == bundle.authority_fingerprint


__all__ = [
    "LANE_B_AUTHORITY_BUNDLE_VERSION",
    "AuthorityRefusal",
    "LaneBAuthorityBundleV1",
    "LaneBAuthorityError",
    "build_lane_b_authority_bundle",
    "draft_fingerprint",
    "verify_lane_b_authority_bundle",
]
