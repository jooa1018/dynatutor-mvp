"""B29 and B32 both have exact typed closure transactions.

**B29, horizontal-contact free body.**  The shared exact-shape reader consumes
only the stated support-frame pair and value-free motion carrier.  Its
transaction builds gravity, contact and applied-force interactions atomically,
and the generic Newton plus Coulomb-friction laws now admit a driven sliding
branch.  The query axis never supplies the direction of motion.

**B32, spring natural-length endpoint.**  The shared exact reader requires the
spring/body/support inventory, initial deformation and rest state, frictionless
authority, exact event-bound natural-length endpoint and final-speed query.  Its
atomic transaction creates only value-free deformation and energy records and
reuses the engine's spring-potential, kinetic-energy and conservation laws.
`spring_vibration_deferred` remains a separate period/frequency deferral.
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
def test_the_closure_catalogue_has_an_exact_spring_energy_transaction() -> None:
    spring_profiles = {item for item in ProfileId if "spring" in item.value}

    assert spring_profiles == {
        ProfileId.spring_energy_natural_length,
        ProfileId.spring_vibration_deferred,
    }
    assert ProfileId.spring_energy_natural_length in _TRANSACTIONS
    assert ProfileId.spring_vibration_deferred not in _TRANSACTIONS


def test_the_exact_spring_profile_declares_the_existing_energy_capability() -> None:
    from evaluation.phase56_stage7.complete_profile import _PROFILES_BY_ID

    signature = _PROFILES_BY_ID[ProfileId.spring_energy_natural_length]
    capability = next(
        item
        for item in signature.prerequisites
        if item[0] == "capability_spring_energy_speed"
    )

    assert capability[1].value == "capability"


def test_the_spring_energy_laws_exist_and_are_therefore_not_the_gap() -> None:
    """The exact endpoint transaction reuses both existing energy laws."""

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
