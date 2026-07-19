"""Versioned, source-grounded contracts for the generic mechanics engine."""

from engine.mechanics.contracts import (
    CONTRACT_VERSION,
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    IR_SCHEMA_NAME,
    IR_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
    MechanicsProblemIRV1,
)
from engine.mechanics.math_ast import MATH_AST_VERSION
from engine.mechanics.modeler import (
    MechanicsModeler,
    MechanicsModelerOutcome,
    ModelerTerminal,
)
from engine.mechanics.modeler_config import (
    DEFAULT_MECHANICS_MODELER_MODEL,
    MechanicsIRMode,
    MechanicsModelerConfig,
)
from engine.mechanics.modeler_inputs import ModelerImageInput


__all__ = [
    "CONTRACT_VERSION",
    "DRAFT_SCHEMA_NAME",
    "DRAFT_SCHEMA_VERSION",
    "IR_SCHEMA_NAME",
    "IR_SCHEMA_VERSION",
    "MATH_AST_VERSION",
    "DEFAULT_MECHANICS_MODELER_MODEL",
    "MechanicsIRMode",
    "MechanicsModeler",
    "MechanicsModelerConfig",
    "MechanicsModelerOutcome",
    "ModelerImageInput",
    "ModelerTerminal",
    "MechanicsProblemDraftV1",
    "MechanicsProblemIRV1",
]
