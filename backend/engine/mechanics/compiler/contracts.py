from __future__ import annotations

from enum import Enum
from typing import Annotated, Iterable, Literal, TypeAlias, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)

from engine.mechanics.contracts import IR_SCHEMA_NAME, IR_SCHEMA_VERSION
from engine.mechanics.math_ast import (
    DimensionVector,
    Equality,
    Inequality,
    SymbolDefinition,
)
from engine.mechanics.normalization import NORMALIZATION_POLICY_VERSION, VALIDATION_POLICY_VERSION


COMPILER_CONTRACT_VERSION = "mechanics-equation-graph-v1"
COMPILER_POLICY_VERSION = "mechanics-compiler-v1"
LAW_LIBRARY_VERSION = "mechanics-laws-v1"

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]*$",
    ),
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]


def _reject_bool_as_finite_float(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("boolean is not a finite float")
    return value


def _require_strict_bool(value: object) -> object:
    if not isinstance(value, bool):
        raise ValueError("value must be a boolean")
    return value


FiniteFloat = Annotated[
    float,
    BeforeValidator(_reject_bool_as_finite_float),
    Field(allow_inf_nan=False, ge=-1.0e300, le=1.0e300),
]
VectorSIValue: TypeAlias = Annotated[
    tuple[FiniteFloat, ...], Field(min_length=1, max_length=3)
]
TensorSIValueRow: TypeAlias = Annotated[
    tuple[FiniteFloat, ...], Field(min_length=1, max_length=3)
]


def _require_rectangular_tensor(
    value: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    if len({len(row) for row in value}) != 1:
        raise ValueError("tensor SI value rows must be rectangular")
    return value


TensorSIValue: TypeAlias = Annotated[
    tuple[TensorSIValueRow, ...],
    Field(min_length=1, max_length=3),
    AfterValidator(_require_rectangular_tensor),
]
SIValue: TypeAlias = Union[FiniteFloat, VectorSIValue, TensorSIValue]
StrictFalse: TypeAlias = Annotated[Literal[False], BeforeValidator(_require_strict_bool)]


class FrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
    )


class CompilerStatus(str, Enum):
    ready = "ready"
    blocked = "blocked"
    invalid = "invalid"
    unsupported = "unsupported"
    underdetermined = "underdetermined"
    overdetermined = "overdetermined"
    conflicting = "conflicting"
    resource_limit = "resource_limit"


class CompilerIssueCode(str, Enum):
    invalid_ir = "invalid_ir"
    policy_mismatch = "policy_mismatch"
    blocking_ambiguity = "blocking_ambiguity"
    unsupported_feature = "unsupported_feature"
    requires_specialized_model = "requires_specialized_model"
    unresolved_query = "unresolved_query"
    invalid_binding = "invalid_binding"
    invalid_expression = "invalid_expression"
    constraint_not_authoritative = "constraint_not_authoritative"
    dimension_mismatch = "dimension_mismatch"
    invalid_domain = "invalid_domain"
    domain_unproven = "domain_unproven"
    duplicate_conflict = "duplicate_conflict"
    consistency_inconclusive = "consistency_inconclusive"
    nonlinear_verification_deferred = "nonlinear_verification_deferred"
    underdetermined = "underdetermined"
    overdetermined = "overdetermined"
    resource_limit = "resource_limit"
    free_linear_vibration_readout_deferred = "free_linear_vibration_readout_deferred"
    translating_frame_relative_acceleration_deferred = (
        "translating_frame_relative_acceleration_deferred"
    )
    rotating_frame_relative_acceleration_deferred = (
        "rotating_frame_relative_acceleration_deferred"
    )
    slot_pin_relative_motion_deferred = "slot_pin_relative_motion_deferred"


COURSE_SCOPE_DEFERRED_ISSUE_CODES: frozenset[CompilerIssueCode] = frozenset(
    {
        CompilerIssueCode.free_linear_vibration_readout_deferred,
        CompilerIssueCode.translating_frame_relative_acceleration_deferred,
        CompilerIssueCode.rotating_frame_relative_acceleration_deferred,
        CompilerIssueCode.slot_pin_relative_motion_deferred,
    }
)


def has_course_scope_deferred_issue(
    codes: Iterable[CompilerIssueCode],
) -> bool:
    """Return whether exact compiler issue codes include a deferred capability."""

    return any(
        type(code) is CompilerIssueCode
        and code in COURSE_SCOPE_DEFERRED_ISSUE_CODES
        for code in codes
    )


class CompilerIssueSeverity(str, Enum):
    warning = "warning"
    error = "error"


class CompilerIssue(FrozenModel):
    code: CompilerIssueCode
    severity: CompilerIssueSeverity
    message: ShortText
    path: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
    referenced_id: Identifier | None = None


class CompilerLimits(FrozenModel):
    max_relevant_records: StrictInt = Field(default=2048, ge=8, le=20_000)
    max_symbols: StrictInt = Field(default=256, ge=1, le=512)
    max_equations: StrictInt = Field(default=128, ge=1, le=512)
    max_constraints: StrictInt = Field(default=128, ge=0, le=512)
    max_initial_conditions: StrictInt = Field(default=32, ge=0, le=128)
    max_applications: StrictInt = Field(default=128, ge=1, le=512)
    max_unknowns: StrictInt = Field(default=64, ge=1, le=256)
    max_branches: StrictInt = Field(default=512, ge=1, le=100_000)
    max_alternative_sets: StrictInt = Field(default=4, ge=0, le=16)
    max_fixed_point_rounds: StrictInt = Field(default=32, ge=1, le=128)


class ValidatedIRAuthorization(FrozenModel):
    """Exact caller-retained identity of one post-validation mechanics IR."""

    ir_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    ir_schema: Literal[IR_SCHEMA_NAME] = IR_SCHEMA_NAME
    ir_version: Literal[IR_SCHEMA_VERSION] = IR_SCHEMA_VERSION
    validation_policy_version: Literal[VALIDATION_POLICY_VERSION] = VALIDATION_POLICY_VERSION
    normalization_policy_version: Literal[NORMALIZATION_POLICY_VERSION] = NORMALIZATION_POLICY_VERSION


class EquationScope(FrozenModel):
    entity_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    point_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)
    frame_id: Identifier | None = None
    interval_id: Identifier | None = None
    event_id: Identifier | None = None
    event_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)

    @model_validator(mode="after")
    def ordered_unique_ids(self) -> "EquationScope":
        for values in (self.entity_ids, self.point_ids, self.event_ids):
            if tuple(sorted(set(values))) != values:
                raise ValueError("scope ID collections must be sorted and unique")
        return self


class SymbolNode(FrozenModel):
    symbol: SymbolDefinition
    quantity_id: Identifier | None = None
    quantity_role: Identifier | None = None
    subject_id: Identifier | None = None
    point_id: Identifier | None = None
    frame_id: Identifier | None = None
    interval_id: Identifier | None = None
    event_id: Identifier | None = None
    known_si_value: SIValue | None = None
    generated: StrictBool = False

    @model_validator(mode="after")
    def reciprocal_quantity_binding(self) -> "SymbolNode":
        if self.symbol.quantity_id != self.quantity_id:
            raise ValueError("symbol and graph quantity bindings must agree")
        return self


EquationExpression: TypeAlias = Annotated[Union[Equality, Inequality], Field(discriminator="op")]


class EquationNode(FrozenModel):
    equation_id: Identifier
    expression: EquationExpression
    expression_fingerprint: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    law_id: Identifier
    scope: EquationScope
    source_quantity_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)
    source_evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)
    assumption_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    constraint_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    generated_unknown_symbol_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    dimension: DimensionVector
    complexity_cost: StrictInt = Field(ge=0, le=10_000)

    @model_validator(mode="after")
    def ordered_unique_provenance(self) -> "EquationNode":
        for values in (
            self.source_quantity_ids,
            self.source_evidence_ids,
            self.assumption_ids,
            self.constraint_ids,
            self.generated_unknown_symbol_ids,
        ):
            if tuple(sorted(set(values))) != values:
                raise ValueError("equation provenance ID collections must be sorted and unique")
        return self


class ConstraintNode(FrozenModel):
    constraint_id: Identifier
    constraint_kind: Identifier
    equation_id: Identifier
    scope: EquationScope
    source_evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)


class InitialConditionNode(FrozenModel):
    condition_id: Identifier
    target_symbol_id: Identifier
    value_symbol_id: Identifier
    wrt_symbol_id: Identifier
    derivative_order: StrictInt = Field(ge=0, le=1)
    scope: EquationScope
    source_quantity_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=8)
    source_evidence_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    source_state_condition_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def ordered_unique_provenance(self) -> "InitialConditionNode":
        for values in (
            self.source_quantity_ids,
            self.source_evidence_ids,
            self.source_state_condition_ids,
        ):
            if tuple(sorted(set(values))) != values:
                raise ValueError("initial-condition provenance IDs must be sorted and unique")
        if self.scope.event_id is None or self.scope.event_ids != (self.scope.event_id,):
            raise ValueError("an initial condition requires one exact event scope")
        if self.target_symbol_id == self.value_symbol_id:
            raise ValueError("initial target and source-value symbols must be distinct")
        return self


class LawApplication(FrozenModel):
    application_id: Identifier
    law_id: Identifier
    equation_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    scope: EquationScope
    source_quantity_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)
    source_evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)
    assumption_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    constraint_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    generated_unknown_symbol_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    complexity_cost: StrictInt = Field(ge=0, le=10_000)


class IncidenceEdge(FrozenModel):
    equation_id: Identifier
    symbol_id: Identifier


class RankMethod(str, Enum):
    structural_maximum_matching = "structural_maximum_matching"
    numeric_linear_coefficients = "numeric_linear_coefficients"


class RankAnalysis(FrozenModel):
    method: RankMethod = RankMethod.structural_maximum_matching
    equality_count: StrictInt = Field(ge=0, le=512)
    inequality_count: StrictInt = Field(ge=0, le=512)
    unknown_count: StrictInt = Field(ge=0, le=256)
    structural_rank: StrictInt = Field(ge=0, le=256)
    underdetermined: StrictBool
    overdetermined: StrictBool
    conflicting: StrictBool
    physical_consistency_claimed: StrictFalse = False


class EquationGraph(FrozenModel):
    schema: Literal[COMPILER_CONTRACT_VERSION] = COMPILER_CONTRACT_VERSION
    compiler_policy_version: Literal[COMPILER_POLICY_VERSION] = COMPILER_POLICY_VERSION
    law_library_version: Literal[LAW_LIBRARY_VERSION] = LAW_LIBRARY_VERSION
    query_id: Identifier
    query_symbol_id: Identifier
    symbols: tuple[SymbolNode, ...] = Field(max_length=512)
    equations: tuple[EquationNode, ...] = Field(max_length=512)
    constraints: tuple[ConstraintNode, ...] = Field(max_length=512)
    initial_conditions: tuple[InitialConditionNode, ...] = Field(default_factory=tuple, max_length=128)
    applications: tuple[LawApplication, ...] = Field(max_length=512)
    incidence: tuple[IncidenceEdge, ...] = Field(max_length=32_768)
    rank: RankAnalysis
    selected_equation_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=256)
    alternative_closed_sets: tuple[tuple[Identifier, ...], ...] = Field(default_factory=tuple, max_length=16)
    fingerprint: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def validate_initial_condition_bindings(self) -> "EquationGraph":
        condition_ids = tuple(item.condition_id for item in self.initial_conditions)
        if tuple(sorted(set(condition_ids))) != condition_ids:
            raise ValueError("initial conditions must have sorted unique IDs")
        symbols = {item.symbol.symbol_id: item for item in self.symbols}
        seen_orders: set[tuple[str, str, int, str]] = set()
        for condition in self.initial_conditions:
            target = symbols.get(condition.target_symbol_id)
            value = symbols.get(condition.value_symbol_id)
            wrt = symbols.get(condition.wrt_symbol_id)
            if target is None or value is None or wrt is None:
                raise ValueError("initial-condition symbols must exist in the graph")
            if value.known_si_value is None:
                raise ValueError("initial-condition value symbols must be known")
            if (
                wrt.quantity_role != "time"
                or wrt.symbol.shape.value != "scalar"
                or wrt.symbol.dimension != DimensionVector(time=1)
            ):
                raise ValueError("initial-condition independent variable must be one scalar time symbol")
            expected_dimension = (
                target.symbol.dimension
                if condition.derivative_order == 0
                else target.symbol.dimension.minus(wrt.symbol.dimension)
            )
            if (
                expected_dimension is None
                or value.symbol.dimension != expected_dimension
                or value.symbol.shape is not target.symbol.shape
                or value.symbol.vector_length != target.symbol.vector_length
            ):
                raise ValueError("initial-condition value must match the typed target derivative")
            if (
                value.quantity_id is None
                or condition.source_quantity_ids != (value.quantity_id,)
            ):
                raise ValueError("initial-condition value provenance must name its exact source quantity")
            scope = condition.scope
            if (
                scope.entity_ids != (target.subject_id,)
                or scope.point_ids != ((target.point_id,) if target.point_id is not None else ())
                or scope.frame_id != target.frame_id
                or scope.interval_id != target.interval_id
                or target.event_id is not None
                or value.subject_id != target.subject_id
                or value.point_id != target.point_id
                or value.frame_id != target.frame_id
                or value.interval_id != target.interval_id
                or value.event_id != scope.event_id
                or wrt.subject_id != target.subject_id
                or wrt.point_id is not None
                or wrt.frame_id != target.frame_id
                or wrt.interval_id != target.interval_id
                or wrt.event_id is not None
            ):
                raise ValueError("initial-condition symbol topology must exactly match its scope")
            order_key = (
                condition.target_symbol_id,
                condition.wrt_symbol_id,
                condition.derivative_order,
                scope.event_id,
            )
            if order_key in seen_orders:
                raise ValueError("initial-condition derivative orders must be unique per target/event")
            seen_orders.add(order_key)
        return self


class CompilerResult(FrozenModel):
    status: CompilerStatus
    graph: EquationGraph | None = None
    issues: tuple[CompilerIssue, ...] = Field(default_factory=tuple, max_length=256)

    @property
    def compilable(self) -> bool:
        return self.status in {CompilerStatus.ready, CompilerStatus.overdetermined} and self.graph is not None

    @model_validator(mode="after")
    def bind_course_scope_deferred_shape(self) -> "CompilerResult":
        deferred = tuple(
            issue
            for issue in self.issues
            if issue.code in COURSE_SCOPE_DEFERRED_ISSUE_CODES
        )
        if not deferred:
            return self
        if (
            self.status is not CompilerStatus.unsupported
            or self.graph is not None
            or len(deferred) != 1
            or len(self.issues) != 1
            or deferred[0].severity is not CompilerIssueSeverity.error
        ):
            raise ValueError(
                "course-scope deferred result requires one exact unsupported error and no graph"
            )
        return self


__all__ = [
    "COMPILER_CONTRACT_VERSION",
    "COMPILER_POLICY_VERSION",
    "COURSE_SCOPE_DEFERRED_ISSUE_CODES",
    "LAW_LIBRARY_VERSION",
    "CompilerIssue",
    "CompilerIssueCode",
    "CompilerIssueSeverity",
    "CompilerLimits",
    "CompilerResult",
    "CompilerStatus",
    "ConstraintNode",
    "InitialConditionNode",
    "EquationExpression",
    "EquationGraph",
    "EquationNode",
    "EquationScope",
    "IncidenceEdge",
    "LawApplication",
    "RankAnalysis",
    "RankMethod",
    "SymbolNode",
    "ValidatedIRAuthorization",
    "has_course_scope_deferred_issue",
]
