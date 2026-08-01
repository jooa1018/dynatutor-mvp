"""B29 and B32: the source can say it; the closure catalogue cannot yet build it.

Both packages were opened, both were carried as far as the v2 contract reaches,
and both stop in the same place — which is worth pinning, because "we could not
close this" and "the corpus cannot express this" are different findings and only
one of them is a corpus finding.

**B29, horizontal-contact free body.**  The source states the support's
orientation, the direction of travel and the kinetic regime, and v2 carries all
three: the frame pair and the axis-relative motion sense project cleanly and
regress nothing.  The wall is the engine's law catalogue.
`_horizontal_surface_contact_profile` admits exactly two regimes — `sticking`, a
body at rest under an applied force, and `sliding`, a moving body with **no**
applied force and **no** tangential-acceleration unknown.  The B29 shape is a
moving body *with* an applied force *and* an unknown tangential acceleration,
which the sliding branch rejects by construction, and nothing emits
`Σ F_t = m a_t` for a horizontal contact.  There is also no
`ProfileId.horizontal_contact` transaction, and the profile's own capability
prerequisite resolves to `unsupported`.

**B32, spring natural-length endpoint.**  The source states the mass, the
stiffness, the initial compression, the release from rest, the frictionless
support and the endpoint — "the instant the spring reaches its natural length" —
and v2 carries the endpoint exactly, as a typed `zero_spring_deformation` bound
to the spring's own deformation quantity rather than as an approximate
`inactive` state.  The wall is again the closure catalogue: `ProfileId` has no
spring-energy member at all.  Its only spring entry, `spring_vibration_deferred`,
matches period/frequency queries and resolves `unsupported`; `_TRANSACTIONS` has
no spring transaction to build the spring interaction and the energy free body
the existing `spring_potential` and `kinetic_energy` laws would need.

Closing either needs a new engine law or a new closure transaction — capability
work, not authority work.  Recorded rather than attempted, and pinned here so a
later reader does not have to re-derive which kind of gap it is.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from evaluation.phase56_stage7.complete_profile import ProfileId
from evaluation.phase56_stage7.complete_profile_application import _TRANSACTIONS


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# B29
# --------------------------------------------------------------------------
def test_no_transaction_builds_a_horizontal_contact_free_body() -> None:
    assert ProfileId.horizontal_contact not in _TRANSACTIONS


def test_the_horizontal_contact_profile_declares_no_capability() -> None:
    from evaluation.phase56_stage7.complete_profile import _PROFILES_BY_ID

    signature = _PROFILES_BY_ID[ProfileId.horizontal_contact]
    capability = next(
        item
        for item in signature.prerequisites
        if item[0] == "capability_horizontal_surface_profile"
    )

    assert capability[2].__name__ == "_catalogue_has_no_capability"


def test_the_sliding_regime_excludes_a_driven_body_by_construction() -> None:
    """The exact branch, read off the engine source rather than described.

    `if applied or tangential_acceleration is not None: return None` is the
    whole of B29's wall: a moving body that is being pushed, whose acceleration
    is the unknown, is not a shape this recognizer has.
    """

    path = REPOSITORY_ROOT / "backend/engine/mechanics/laws/core.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_horizontal_surface_contact_profile"
    )
    guards = [
        ast.unparse(node.test)
        for node in ast.walk(function)
        if isinstance(node, ast.If)
    ]

    assert any(
        "applied" in guard and "tangential_acceleration is not None" in guard
        for guard in guards
    )


# --------------------------------------------------------------------------
# B32
# --------------------------------------------------------------------------
def test_the_closure_catalogue_has_no_spring_energy_profile() -> None:
    spring_profiles = {item for item in ProfileId if "spring" in item.value}

    assert spring_profiles == {ProfileId.spring_vibration_deferred}
    assert ProfileId.spring_vibration_deferred not in _TRANSACTIONS


def test_the_only_spring_profile_declares_no_capability() -> None:
    from evaluation.phase56_stage7.complete_profile import _PROFILES_BY_ID

    signature = _PROFILES_BY_ID[ProfileId.spring_vibration_deferred]
    capability = next(
        item for item in signature.prerequisites if item[0] == "capability_period_readout"
    )

    assert capability[2].__name__ == "_catalogue_has_no_capability"


def test_the_spring_energy_laws_exist_and_are_therefore_not_the_gap() -> None:
    """Both halves of ½kx² = ½mv² are in the catalogue; the free body is not."""

    from engine.mechanics.laws.core import CORE_LAW_CATALOG

    law_ids = {rule.law_id for rule in CORE_LAW_CATALOG}
    assert {"spring_potential", "kinetic_energy"} <= law_ids


# --------------------------------------------------------------------------
# What v2 *can* say, in both cases
# --------------------------------------------------------------------------
def test_the_v2_contract_can_state_an_exact_natural_length_endpoint() -> None:
    """Not `inactive`: that cannot tell natural length from separation."""

    from evaluation.phase56_stage7.corpus_v2.records import EndpointCondition

    assert EndpointCondition.zero_spring_deformation in EndpointCondition
    assert EndpointCondition.reaches_natural_length in EndpointCondition
    assert EndpointCondition.contact_loss is not EndpointCondition.zero_spring_deformation


@pytest.mark.parametrize(
    "carrier",
    ["reference_frames", "motion_senses", "endpoint_conditions"],
)
def test_the_v2_contract_carries_what_both_cohorts_need(carrier: str) -> None:
    from evaluation.phase56_stage7.corpus_v2.records import CorpusV2AugmentationV1

    assert carrier in CorpusV2AugmentationV1.model_fields
