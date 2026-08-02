"""B29 is closed; B32 remains a precisely identified catalogue wall.

Both packages were opened, both were carried as far as the v2 contract reaches,
and both stop in the same place — which is worth pinning, because "we could not
close this" and "the corpus cannot express this" are different findings and only
one of them is a corpus finding.

**B29, horizontal-contact free body.**  The shared exact-shape reader consumes
only the stated support-frame pair and value-free motion carrier.  Its
transaction builds gravity, contact and applied-force interactions atomically,
and the generic Newton plus Coulomb-friction laws now admit a driven sliding
branch.  The query axis never supplies the direction of motion.

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

Closing B32 needs a spring-energy profile and transaction — capability work,
not authority work.  It remains pinned here so the next package starts at the
actual wall rather than re-deriving it.
"""

from __future__ import annotations

import pytest

from evaluation.phase56_stage7.complete_profile import ProfileId
from evaluation.phase56_stage7.complete_profile_application import _TRANSACTIONS


# --------------------------------------------------------------------------
# B29
# --------------------------------------------------------------------------
def test_horizontal_contact_has_an_atomic_transaction() -> None:
    assert ProfileId.horizontal_contact in _TRANSACTIONS


def test_the_horizontal_contact_profile_declares_its_real_capability() -> None:
    from evaluation.phase56_stage7.complete_profile import _PROFILES_BY_ID

    signature = _PROFILES_BY_ID[ProfileId.horizontal_contact]
    capability = next(
        item
        for item in signature.prerequisites
        if item[0] == "capability_horizontal_surface_profile"
    )

    assert capability[2].__name__ == "_horizontal_driven_capability"


def test_the_catalogue_contains_the_stated_frame_normal_projection() -> None:
    from engine.mechanics.laws.core import CORE_LAW_CATALOG

    law_ids = {rule.law_id for rule in CORE_LAW_CATALOG}
    assert "horizontal_stated_frame_gravity_normal_projection" in law_ids


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
