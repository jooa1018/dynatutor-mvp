"""Phase 56 Stage 7 offline evaluator contracts.

The runtime/input and gold/scoring trust domains are intentionally separate.
Production modules under :mod:`engine` and :mod:`app` must never import this
package.
"""

from evaluation.phase56_stage7.contracts import (
    STAGE7_ARTIFACT_SCHEMA,
    STAGE7_ARTIFACT_VERSION,
    STAGE7_CONTRACT_VERSION,
    STAGE7_EVALUATOR_VERSION,
    Stage7EvaluationContractV1,
    stage7_evaluation_contract,
)
from evaluation.phase56_stage7.direct_impulse_profile import (
    install_direct_impulse_profile,
)
from evaluation.phase56_stage7.scoped_rest_assumption import (
    install_scoped_rest_assumption_policy,
)

# Install source-scope policy before any projection runs, then install the
# evaluator-only direct-impulse closure before a runner imports
# ``close_projected_draft`` by value.  Neither bridge is imported by production
# engine/app modules.
install_scoped_rest_assumption_policy()
install_direct_impulse_profile()

__all__ = [
    "STAGE7_ARTIFACT_SCHEMA",
    "STAGE7_ARTIFACT_VERSION",
    "STAGE7_CONTRACT_VERSION",
    "STAGE7_EVALUATOR_VERSION",
    "Stage7EvaluationContractV1",
    "stage7_evaluation_contract",
]
