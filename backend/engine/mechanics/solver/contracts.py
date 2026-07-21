"""Immutable, data-only contracts for the Stage 4 mechanics solver boundary.

Nothing in this module executes expressions or chooses a backend.  A future
planner must derive these records exclusively from the embedded immutable
``EquationGraph``.
"""

from __future__ import annotations

from enum import Enum
import hashlib
import json
from typing import Annotated, Iterable, Literal, TypeAlias, Union

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)

from engine.mechanics.compiler.contracts import EquationGraph
from engine.mechanics.math_ast import (
    Add,
    Cross,
    Derivative,
    Divide,
    Dot,
    Equality,
    Inequality,
    Integral,
    LiteralNode,
    MathNode,
    Multiply,
    Negate,
    Norm,
    Power,
    Subtract,
    SymbolRef,
    VectorNode,
)


SOLVER_CONTRACT_VERSION = "mechanics-solver-contract-v1"
SOLVER_POLICY_VERSION = "mechanics-solver-policy-v1"

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
DisplayOnlyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]


def _finite_not_bool(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("boolean is not a finite number")
    return value


FiniteFloat = Annotated[float, BeforeValidator(_finite_not_bool), Field(allow_inf_nan=False, ge=-1.0e300, le=1.0e300)]
PositiveFiniteFloat = Annotated[float, BeforeValidator(_finite_not_bool), Field(allow_inf_nan=False, gt=0.0, le=1.0e12)]
SIValue: TypeAlias = Union[FiniteFloat, Annotated[tuple[FiniteFloat, ...], Field(min_length=1, max_length=16)]]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always", str_strip_whitespace=True)


def _is_sorted_unique(values: tuple[str, ...]) -> bool:
    return values == tuple(sorted(set(values)))


def _sorted_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _direct_math_children(node: MathNode) -> tuple[MathNode, ...]:
    """Inspect only typed AST models; strings are never interpreted."""

    children: list[MathNode] = []

    def collect(value: object) -> None:
        if isinstance(value, MathNode):
            children.append(value)
        elif isinstance(value, BaseModel):
            for field_name in type(value).model_fields:
                collect(getattr(value, field_name))
        elif isinstance(value, tuple):
            for item in value:
                collect(item)

    for name in type(node).model_fields:
        if name != "dimension":
            collect(getattr(node, name))
    return tuple(children)


def _walk_math_nodes(expression: MathNode) -> tuple[tuple[MathNode, int], ...]:
    stack: list[tuple[MathNode, int]] = [(expression, 1)]
    result: list[tuple[MathNode, int]] = []
    while stack:
        node, depth = stack.pop()
        result.append((node, depth))
        if len(result) > 4096 or depth > 64:
            raise ValueError("equation AST exceeds the solver-contract inspection bound")
        stack.extend((child, depth + 1) for child in reversed(_direct_math_children(node)))
    return tuple(result)


def _ordinary_symbol_ids(expression: MathNode) -> set[str]:
    return {
        node.symbol_id
        for node, _ in _walk_math_nodes(expression)
        if isinstance(node, SymbolRef)
    }


def _polynomial_degree(expression: MathNode, unknowns: set[str]) -> int | None:
    """Return a bounded syntactic degree, or ``None`` when not certifiable."""

    if isinstance(expression, SymbolRef):
        return 1 if expression.symbol_id in unknowns else 0
    if isinstance(expression, LiteralNode):
        return 0
    if isinstance(expression, (VectorNode, Dot, Cross, Norm, Integral)):
        return None
    if isinstance(expression, Add):
        values = tuple(_polynomial_degree(item, unknowns) for item in expression.terms)
        return None if any(item is None for item in values) else max((item for item in values if item is not None), default=0)
    if isinstance(expression, Subtract):
        left = _polynomial_degree(expression.left, unknowns)
        right = _polynomial_degree(expression.right, unknowns)
        return None if left is None or right is None else max(left, right)
    if isinstance(expression, Multiply):
        values = tuple(_polynomial_degree(item, unknowns) for item in expression.factors)
        if any(item is None for item in values):
            return None
        degree = sum(item for item in values if item is not None)
        return degree if degree <= 64 else None
    if isinstance(expression, Divide):
        numerator = _polynomial_degree(expression.numerator, unknowns)
        denominator = _polynomial_degree(expression.denominator, unknowns)
        return numerator if numerator is not None and denominator == 0 else None
    if isinstance(expression, Power):
        base = _polynomial_degree(expression.base, unknowns)
        exponent = expression.exponent
        if base is None or not isinstance(exponent, LiteralNode):
            return None
        rounded = round(exponent.value)
        if exponent.value != rounded or rounded < 0:
            return None
        degree = base * int(rounded)
        return degree if degree <= 64 else None
    if isinstance(expression, Negate):
        return _polynomial_degree(expression.operand, unknowns)
    if isinstance(expression, Derivative):
        return _polynomial_degree(expression.expression, unknowns)
    if isinstance(expression, (Equality, Inequality)):
        left = _polynomial_degree(expression.left, unknowns)
        right = _polynomial_degree(expression.right, unknowns)
        return None if left is None or right is None else max(left, right)
    return None


def _graph_event_ids(graph: EquationGraph) -> tuple[str, ...]:
    ids: list[str] = []
    for item in (*graph.equations, *graph.constraints, *graph.initial_conditions):
        scope = item.scope
        if scope.event_id is not None:
            ids.append(scope.event_id)
        ids.extend(scope.event_ids)
    for application in graph.applications:
        if application.scope.event_id is not None:
            ids.append(application.scope.event_id)
        ids.extend(application.scope.event_ids)
    ids.extend(item.event_id for item in graph.symbols if item.event_id is not None)
    return _sorted_unique(ids)


def _graph_evidence_ids(graph: EquationGraph) -> tuple[str, ...]:
    return _sorted_unique(
        evidence_id
        for item in (*graph.equations, *graph.constraints, *graph.initial_conditions, *graph.applications)
        for evidence_id in item.source_evidence_ids
    )


def _graph_unknown_ids(graph: EquationGraph) -> tuple[str, ...]:
    ordinary = {
        symbol_id
        for equation in graph.equations
        for symbol_id in _ordinary_symbol_ids(equation.expression)
    }
    return tuple(
        sorted(
            item.symbol.symbol_id
            for item in graph.symbols
            if item.known_si_value is None
            and (
                item.symbol.symbol_id == graph.query_symbol_id
                or item.quantity_role != "time"
                or item.symbol.symbol_id in ordinary
            )
        )
    )


def _selected_structural_rank(
    graph: EquationGraph,
    selected_equation_ids: tuple[str, ...],
    unknown_symbol_ids: tuple[str, ...],
) -> int:
    """Compute a bounded bipartite matching over selected graph incidence."""

    unknowns = set(unknown_symbol_ids)
    adjacency = {
        equation_id: tuple(sorted({
            edge.symbol_id
            for edge in graph.incidence
            if edge.equation_id == equation_id and edge.symbol_id in unknowns
        }))
        for equation_id in selected_equation_ids
    }
    matched_by_symbol: dict[str, str] = {}

    def augment(equation_id: str, seen: set[str]) -> bool:
        for symbol_id in adjacency[equation_id]:
            if symbol_id in seen:
                continue
            seen.add(symbol_id)
            owner = matched_by_symbol.get(symbol_id)
            if owner is None or augment(owner, seen):
                matched_by_symbol[symbol_id] = equation_id
                return True
        return False

    return sum(augment(equation_id, set()) for equation_id in selected_equation_ids)


class SolveBackendKind(str, Enum):
    linear_symbolic = "linear_symbolic"
    polynomial_symbolic = "polynomial_symbolic"
    nonlinear_symbolic = "nonlinear_symbolic"
    numeric_root = "numeric_root"
    ode_ivp = "ode_ivp"
    event_root = "event_root"
    constrained_optimization = "constrained_optimization"
    piecewise = "piecewise"


class SolvePhase(str, Enum):
    planning = "planning"
    translation = "translation"
    symbolic = "symbolic"
    numeric = "numeric"
    candidate_generation = "candidate_generation"
    verification = "verification"


class SolverBudget(FrozenModel):
    max_equations: StrictInt = Field(default=128, ge=1, le=512)
    max_unknowns: StrictInt = Field(default=64, ge=1, le=256)
    max_candidates: StrictInt = Field(default=128, ge=1, le=1024)
    max_ast_nodes: StrictInt = Field(default=4096, ge=1, le=65_536)
    max_ast_depth: StrictInt = Field(default=24, ge=1, le=64)
    max_operation_cost: StrictInt = Field(default=100_000, ge=1, le=10_000_000)
    symbolic_time_limit_s: PositiveFiniteFloat = 5.0
    numeric_time_limit_s: PositiveFiniteFloat = 10.0
    verification_time_limit_s: PositiveFiniteFloat = 5.0
    timeout_termination_grace_s: PositiveFiniteFloat = Field(default=0.5, le=5.0)
    max_numeric_starts: StrictInt = Field(default=32, ge=1, le=1024)
    max_numeric_iterations: StrictInt = Field(default=1000, ge=1, le=1_000_000)
    absolute_tolerance: PositiveFiniteFloat = 1.0e-10
    relative_tolerance: PositiveFiniteFloat = 1.0e-9
    residual_tolerance: PositiveFiniteFloat = 1.0e-8
    constraint_tolerance: PositiveFiniteFloat = 1.0e-9


class SolverTimeout(FrozenModel):
    phase: SolvePhase
    backend: SolveBackendKind
    limit_s: PositiveFiniteFloat
    elapsed_s: PositiveFiniteFloat

    @model_validator(mode="after")
    def elapsed_reached_limit(self) -> "SolverTimeout":
        if self.elapsed_s < self.limit_s:
            raise ValueError("timeout elapsed time must reach the configured limit")
        return self


class GraphStructureFeatures(FrozenModel):
    equality_count: StrictInt = Field(ge=0, le=512)
    inequality_count: StrictInt = Field(ge=0, le=512)
    constraint_count: StrictInt = Field(ge=0, le=512)
    initial_condition_count: StrictInt = Field(ge=0, le=128)
    unknown_count: StrictInt = Field(ge=0, le=256)
    max_ast_nodes_per_equation: StrictInt = Field(ge=0, le=65_536)
    total_ast_nodes: StrictInt = Field(ge=0, le=65_536)
    max_ast_depth: StrictInt = Field(ge=0, le=64)
    total_operation_cost: StrictInt = Field(ge=0, le=10_000_000)
    polynomial_degree: StrictInt | None = Field(default=None, ge=0, le=64)
    has_derivative: StrictBool = False
    has_integral: StrictBool = False
    has_vector_operation: StrictBool = False
    has_piecewise: StrictBool = False
    has_event_condition: StrictBool = False
    has_nonlinear_operation: StrictBool = False


def primary_backend_for_structure(structure: GraphStructureFeatures) -> SolveBackendKind:
    """Return the one closed, graph-structure-only primary backend."""

    if structure.has_piecewise:
        return SolveBackendKind.piecewise
    if structure.has_derivative:
        return SolveBackendKind.ode_ivp
    if structure.has_integral or structure.has_vector_operation:
        return SolveBackendKind.nonlinear_symbolic
    if structure.polynomial_degree is None:
        return SolveBackendKind.nonlinear_symbolic
    if structure.polynomial_degree <= 1:
        return SolveBackendKind.linear_symbolic
    return SolveBackendKind.polynomial_symbolic


def numeric_fallback_for_structure(structure: GraphStructureFeatures) -> SolveBackendKind | None:
    """Return the sole deterministic fallback, if this structure has one."""

    if primary_backend_for_structure(structure) is SolveBackendKind.nonlinear_symbolic:
        return SolveBackendKind.numeric_root
    return None


# Descriptive aliases retained as a small public planner-facing vocabulary.
derive_primary_backend = primary_backend_for_structure
derive_numeric_fallback = numeric_fallback_for_structure


def _graph_structure(graph: EquationGraph, unknown_ids: tuple[str, ...]) -> GraphStructureFeatures:
    metrics = tuple(_walk_math_nodes(item.expression) for item in graph.equations)
    degrees = tuple(_polynomial_degree(item.expression, set(unknown_ids)) for item in graph.equations)
    polynomial_degree = None if any(item is None for item in degrees) else max(degrees, default=0)
    nodes = tuple(node for expression in metrics for node, _ in expression)
    return GraphStructureFeatures(
        equality_count=sum(isinstance(item.expression, Equality) for item in graph.equations),
        inequality_count=sum(isinstance(item.expression, Inequality) for item in graph.equations),
        constraint_count=len(graph.constraints),
        initial_condition_count=len(graph.initial_conditions),
        unknown_count=len(unknown_ids),
        max_ast_nodes_per_equation=max((len(item) for item in metrics), default=0),
        total_ast_nodes=sum(len(item) for item in metrics),
        max_ast_depth=max((depth for item in metrics for _, depth in item), default=0),
        total_operation_cost=sum(item.complexity_cost for item in graph.equations),
        polynomial_degree=polynomial_degree,
        has_derivative=any(isinstance(item, Derivative) for item in nodes),
        has_integral=any(isinstance(item, Integral) for item in nodes),
        has_vector_operation=any(isinstance(item, (VectorNode, Dot, Cross, Norm)) for item in nodes),
        has_piecewise=any(getattr(item, "op", None) == "piecewise" for item in nodes),
        has_event_condition=bool(_graph_event_ids(graph)),
        # Unknown-dependent syntax whose degree is not certified is treated
        # conservatively as nonlinear rather than allowing a false linear flag.
        has_nonlinear_operation=any(
            degree is None and bool(_ordinary_symbol_ids(equation.expression) & set(unknown_ids))
            or degree is not None and degree > 1
            for equation, degree in zip(graph.equations, degrees)
        ),
    )


class SolvePlan(FrozenModel):
    contract_version: Literal[SOLVER_CONTRACT_VERSION] = SOLVER_CONTRACT_VERSION
    policy_version: Literal[SOLVER_POLICY_VERSION] = SOLVER_POLICY_VERSION
    graph: EquationGraph
    graph_fingerprint: Fingerprint | None = None
    plan_fingerprint: Fingerprint | None = None
    query_id: Identifier
    query_symbol_id: Identifier
    selected_equality_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=512)
    inequality_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    constraint_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    initial_condition_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=128)
    event_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=128)
    allowed_source_evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    unknown_symbol_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    known_symbol_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    structure: GraphStructureFeatures
    primary_backend: SolveBackendKind
    permitted_numeric_fallback: SolveBackendKind | None = None
    budget: SolverBudget

    @model_validator(mode="after")
    def validate_plan_sets(self) -> "SolvePlan":
        if "graph_fingerprint" in self.model_fields_set:
            if self.graph_fingerprint is None or self.graph_fingerprint != self.graph.fingerprint:
                raise ValueError("graph fingerprint must exactly match the embedded graph")
        else:
            object.__setattr__(self, "graph_fingerprint", self.graph.fingerprint)

        collections = (
            self.selected_equality_ids, self.inequality_ids, self.constraint_ids,
            self.initial_condition_ids, self.event_ids, self.allowed_source_evidence_ids,
            self.unknown_symbol_ids, self.known_symbol_ids,
        )
        if not all(_is_sorted_unique(values) for values in collections):
            raise ValueError("plan ID collections must be sorted and unique")

        equation_ids = tuple(item.equation_id for item in self.graph.equations)
        constraint_ids = tuple(item.constraint_id for item in self.graph.constraints)
        condition_ids = tuple(item.condition_id for item in self.graph.initial_conditions)
        symbol_ids = tuple(item.symbol.symbol_id for item in self.graph.symbols)
        if any(len(set(values)) != len(values) for values in (equation_ids, constraint_ids, condition_ids, symbol_ids)):
            raise ValueError("embedded graph authority must have unique node IDs")
        equations = {item.equation_id: item for item in self.graph.equations}
        if not _is_sorted_unique(self.graph.selected_equation_ids):
            raise ValueError("embedded graph selected equation IDs must be canonical")
        if any(
            identifier not in equations
            or not isinstance(equations[identifier].expression, Equality)
            for identifier in self.graph.selected_equation_ids
        ):
            raise ValueError("embedded graph selected set must contain only existing equalities")
        for closed_set in self.graph.alternative_closed_sets:
            if not _is_sorted_unique(closed_set) or any(
                identifier not in equations
                or not isinstance(equations[identifier].expression, Equality)
                for identifier in closed_set
            ):
                raise ValueError("embedded graph alternative sets must be canonical existing equalities")
        constraint_id_set = set(constraint_ids)
        if any(not set(item.constraint_ids) <= constraint_id_set for item in self.graph.equations):
            raise ValueError("embedded graph equation constraint provenance must resolve")
        if any(item.equation_id not in equations for item in self.graph.constraints):
            raise ValueError("embedded graph constraint equations must resolve")
        if any(not set(item.equation_ids) <= set(equations) for item in self.graph.applications):
            raise ValueError("embedded graph application equations must resolve")
        if any(not set(item.constraint_ids) <= constraint_id_set for item in self.graph.applications):
            raise ValueError("embedded graph application constraint provenance must resolve")

        expected_equalities = tuple(self.graph.selected_equation_ids)
        expected_inequalities = _sorted_unique(
            item.equation_id for item in self.graph.equations if isinstance(item.expression, Inequality)
        )
        expected_constraints = _sorted_unique(constraint_ids)
        expected_conditions = _sorted_unique(condition_ids)
        expected_events = _graph_event_ids(self.graph)
        expected_evidence = _graph_evidence_ids(self.graph)
        expected_unknowns = _graph_unknown_ids(self.graph)
        expected_known = _sorted_unique(
            item.symbol.symbol_id for item in self.graph.symbols if item.known_si_value is not None
        )
        if self.query_id != self.graph.query_id or self.query_symbol_id != self.graph.query_symbol_id:
            raise ValueError("plan query must exactly match the embedded graph")
        expected = (
            expected_equalities, expected_inequalities, expected_constraints,
            expected_conditions, expected_events, expected_evidence,
            expected_unknowns, expected_known,
        )
        if collections != expected:
            raise ValueError("plan-derived ID collections must exactly match the embedded graph")
        if self.query_symbol_id not in self.unknown_symbol_ids:
            raise ValueError("query symbol must be one of the graph-derived unknown symbols")
        if set(self.unknown_symbol_ids) & set(self.known_symbol_ids):
            raise ValueError("known and unknown symbols must be disjoint")

        exact_structure = _graph_structure(self.graph, expected_unknowns)
        if self.structure != exact_structure:
            raise ValueError("declared structure must exactly match bounded graph-derived features")
        if (
            self.graph.rank.equality_count != exact_structure.equality_count
            or self.graph.rank.inequality_count != exact_structure.inequality_count
            or self.graph.rank.unknown_count != exact_structure.unknown_count
            or self.graph.rank.structural_rank
            > min(exact_structure.equality_count, exact_structure.unknown_count)
        ):
            raise ValueError("embedded graph rank counts or structural rank contradict graph content")
        if (
            self.graph.rank.underdetermined
            or self.graph.rank.conflicting
            or self.graph.rank.structural_rank < exact_structure.unknown_count
            or len(self.selected_equality_ids) < exact_structure.unknown_count
        ):
            raise ValueError("a solve plan requires sufficient non-conflicting structural rank")
        if _selected_structural_rank(
            self.graph,
            self.selected_equality_ids,
            expected_unknowns,
        ) < exact_structure.unknown_count:
            raise ValueError("selected equality set must structurally cover every unknown symbol")
        exact_primary = primary_backend_for_structure(exact_structure)
        exact_fallback = numeric_fallback_for_structure(exact_structure)
        if self.primary_backend is not exact_primary:
            raise ValueError("primary backend must exactly match graph-only routing policy")
        if self.permitted_numeric_fallback is not exact_fallback:
            raise ValueError("numeric fallback must exactly match graph-only routing policy")
        if exact_structure.equality_count + exact_structure.inequality_count > self.budget.max_equations:
            raise ValueError("graph exceeds equation budget")
        if exact_structure.unknown_count > self.budget.max_unknowns:
            raise ValueError("graph exceeds unknown budget")
        if exact_structure.total_ast_nodes > self.budget.max_ast_nodes or exact_structure.max_ast_depth > self.budget.max_ast_depth:
            raise ValueError("graph exceeds AST budget")
        if exact_structure.total_operation_cost > self.budget.max_operation_cost:
            raise ValueError("graph exceeds operation budget")

        canonical = json.dumps(
            self.model_dump(mode="json", exclude={"plan_fingerprint"}),
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        expected_fingerprint = hashlib.sha256(canonical).hexdigest()
        if "plan_fingerprint" in self.model_fields_set:
            if self.plan_fingerprint is None or self.plan_fingerprint != expected_fingerprint:
                raise ValueError("plan fingerprint must exactly match canonical plan data")
        else:
            object.__setattr__(self, "plan_fingerprint", expected_fingerprint)
        return self


class CandidateValue(FrozenModel):
    symbol_id: Identifier
    value_si: SIValue


class SolverCandidate(FrozenModel):
    candidate_id: Identifier | None = None
    generation_index: StrictInt = Field(ge=0, le=1023)
    root_index: StrictInt = Field(ge=0, le=1023)
    root_multiplicity: StrictInt = Field(default=1, ge=1, le=1024)
    graph_fingerprint: Fingerprint
    plan_fingerprint: Fingerprint
    backend: SolveBackendKind
    approximate: StrictBool
    equation_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=512)
    branch_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)
    values: tuple[CandidateValue, ...] = Field(min_length=1, max_length=256)
    query_symbol_id: Identifier
    query_value_si: SIValue
    symbolic_display_only: DisplayOnlyText | None = None

    @model_validator(mode="after")
    def validate_candidate(self) -> "SolverCandidate":
        if not _is_sorted_unique(self.equation_ids) or not _is_sorted_unique(self.branch_ids):
            raise ValueError("candidate provenance IDs must be sorted and unique")
        symbols = tuple(item.symbol_id for item in self.values)
        if not _is_sorted_unique(symbols):
            raise ValueError("candidate values must have sorted unique symbol IDs")
        by_symbol = {item.symbol_id: item.value_si for item in self.values}
        if by_symbol.get(self.query_symbol_id) != self.query_value_si:
            raise ValueError("candidate query value must exactly match its typed symbol value")
        expected_candidate_id = canonical_candidate_id(self)
        if "candidate_id" in self.model_fields_set:
            if self.candidate_id is None or self.candidate_id != expected_candidate_id:
                raise ValueError("candidate ID must be the canonical authoritative-data ID")
        else:
            object.__setattr__(self, "candidate_id", expected_candidate_id)
        return self


def canonical_candidate_sha256(candidate: SolverCandidate) -> str:
    """Hash every authoritative candidate field except its self-derived ID."""

    canonical = json.dumps(
        candidate.model_dump(mode="json", exclude={"candidate_id"}),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def canonical_candidate_id(candidate: SolverCandidate) -> str:
    """Render the bounded deterministic ID for one candidate record."""

    return f"candidate_{canonical_candidate_sha256(candidate)[:32]}"


def make_solver_candidate(**authoritative_data: object) -> SolverCandidate:
    """Validated constructor that derives, rather than trusts, candidate ID."""

    return SolverCandidate(**authoritative_data)


# A factory spelling that reads naturally at backend call sites.
create_solver_candidate = make_solver_candidate


class CandidateGenerationRecord(FrozenModel):
    generation_index: StrictInt = Field(ge=0, le=1023)
    candidate_id: Identifier
    backend: SolveBackendKind
    root_index: StrictInt = Field(ge=0, le=1023)
    branch_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)
    authoritative_sha256: Fingerprint

    @model_validator(mode="after")
    def validate_record(self) -> "CandidateGenerationRecord":
        if not _is_sorted_unique(self.branch_ids):
            raise ValueError("manifest branch IDs must be sorted and unique")
        if self.candidate_id != f"candidate_{self.authoritative_sha256[:32]}":
            raise ValueError("manifest candidate ID must derive from its authoritative SHA-256")
        return self


def candidate_generation_manifest(
    candidates: Iterable[SolverCandidate],
) -> tuple[CandidateGenerationRecord, ...]:
    """Build the exact ordered manifest for already validated candidates."""

    return tuple(
        CandidateGenerationRecord(
            generation_index=item.generation_index,
            candidate_id=item.candidate_id,
            backend=item.backend,
            root_index=item.root_index,
            branch_ids=item.branch_ids,
            authoritative_sha256=canonical_candidate_sha256(item),
        )
        for item in candidates
    )


class CandidateCoverage(str, Enum):
    exhaustive_symbolic = "exhaustive_symbolic"
    bounded_numeric = "bounded_numeric"
    incomplete = "incomplete"


class CandidateSet(FrozenModel):
    graph_fingerprint: Fingerprint
    plan_fingerprint: Fingerprint
    coverage: CandidateCoverage
    generation_complete: StrictBool
    generated_count: StrictInt = Field(ge=0, le=1024)
    candidates: tuple[SolverCandidate, ...] = Field(default_factory=tuple, max_length=1024)
    manifest: tuple[CandidateGenerationRecord, ...] = Field(max_length=1024)

    @property
    def auto_selectable(self) -> bool:
        return self.generation_complete and self.coverage is CandidateCoverage.exhaustive_symbolic

    @model_validator(mode="after")
    def validate_candidates(self) -> "CandidateSet":
        if self.generated_count != len(self.candidates) or self.generated_count != len(self.manifest):
            raise ValueError("generated count, manifest, and retained candidates must exactly agree")
        if self.coverage is CandidateCoverage.incomplete and self.generation_complete:
            raise ValueError("incomplete coverage cannot claim generation completion")
        if self.coverage is not CandidateCoverage.incomplete and not self.generation_complete:
            raise ValueError("non-complete generation must use incomplete coverage")
        ids = tuple(item.candidate_id for item in self.candidates)
        indices = tuple(item.generation_index for item in self.candidates)
        slots = tuple((item.backend, item.root_index, item.branch_ids) for item in self.candidates)
        if len(set(ids)) != len(ids) or len(set(indices)) != len(indices) or len(set(slots)) != len(slots):
            raise ValueError("candidate IDs, generation indices, and root slots must be unique")
        if indices != tuple(range(len(self.candidates))):
            raise ValueError("candidate generation indices must be contiguous from zero in retained order")
        group_counts: dict[tuple[SolveBackendKind, tuple[str, ...]], int] = {}
        for candidate in self.candidates:
            group = (candidate.backend, candidate.branch_ids)
            expected_root_index = group_counts.get(group, 0)
            if candidate.root_index != expected_root_index:
                raise ValueError("root indices must be contiguous from zero within each backend/branch group")
            group_counts[group] = expected_root_index + 1
        exact_manifest = candidate_generation_manifest(self.candidates)
        if self.manifest != exact_manifest:
            raise ValueError("candidate manifest must exactly bind every retained candidate in order")
        if any(item.graph_fingerprint != self.graph_fingerprint or item.plan_fingerprint != self.plan_fingerprint for item in self.candidates):
            raise ValueError("all candidates must bind to this graph and plan")
        symbolic_backends = {
            SolveBackendKind.linear_symbolic,
            SolveBackendKind.polynomial_symbolic,
            SolveBackendKind.nonlinear_symbolic,
            SolveBackendKind.piecewise,
        }
        if self.coverage is CandidateCoverage.exhaustive_symbolic:
            if any(item.backend not in symbolic_backends or item.approximate for item in self.candidates):
                raise ValueError("exhaustive symbolic coverage accepts only exact symbolic candidates")
        if self.coverage is CandidateCoverage.bounded_numeric:
            numeric_backends = {
                SolveBackendKind.numeric_root,
                SolveBackendKind.ode_ivp,
                SolveBackendKind.event_root,
                SolveBackendKind.constrained_optimization,
            }
            if any(item.backend not in numeric_backends or not item.approximate for item in self.candidates):
                raise ValueError("bounded numeric coverage accepts only approximate numeric candidates")
        return self


class CandidateRejectionReason(str, Enum):
    equation_residual = "equation_residual"
    numerical_integration_residual = "numerical_integration_residual"
    independent_equation_mismatch = "independent_equation_mismatch"
    inequality_violation = "inequality_violation"
    constraint_violation = "constraint_violation"
    event_order_violation = "event_order_violation"
    initial_boundary_violation = "initial_boundary_violation"
    conservation_violation = "conservation_violation"
    source_evidence_mismatch = "source_evidence_mismatch"
    nonfinite_value = "nonfinite_value"
    unit_mismatch = "unit_mismatch"
    query_unbound = "query_unbound"
    physical_domain_violation = "physical_domain_violation"
    nonnegative_time_violation = "nonnegative_time_violation"
    positive_parameter_violation = "positive_parameter_violation"
    physical_regime_violation = "physical_regime_violation"
    duplicate_root = "duplicate_root"
    verification_inconclusive = "verification_inconclusive"


class CandidateRejection(FrozenModel):
    candidate_id: Identifier
    reason: CandidateRejectionReason
    check_id: Identifier
    equation_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    constraint_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    event_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=128)
    symbol_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    initial_condition_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=128)
    source_evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)

    @model_validator(mode="after")
    def ordered_provenance(self) -> "CandidateRejection":
        provenance = (
            self.equation_ids,
            self.constraint_ids,
            self.event_ids,
            self.symbol_ids,
            self.initial_condition_ids,
            self.source_evidence_ids,
        )
        if not all(_is_sorted_unique(values) for values in provenance):
            raise ValueError("rejection provenance must be sorted and unique")
        if not any(provenance) and self.reason not in {
            CandidateRejectionReason.nonfinite_value,
            CandidateRejectionReason.unit_mismatch,
            CandidateRejectionReason.query_unbound,
            CandidateRejectionReason.duplicate_root,
            CandidateRejectionReason.verification_inconclusive,
        }:
            raise ValueError("rejection reason requires precise graph provenance")
        return self


class SolverDiagnosticCode(str, Enum):
    backend_selected = "backend_selected"
    numeric_fallback_used = "numeric_fallback_used"
    candidate_limit_reached = "candidate_limit_reached"
    generation_incomplete = "generation_incomplete"
    backend_unsupported = "backend_unsupported"
    backend_failure = "backend_failure"
    resource_limit = "resource_limit"
    timeout = "timeout"


class DiagnosticSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"


_DIAGNOSTIC_SEVERITY = {
    SolverDiagnosticCode.backend_selected: DiagnosticSeverity.info,
    SolverDiagnosticCode.numeric_fallback_used: DiagnosticSeverity.warning,
    SolverDiagnosticCode.generation_incomplete: DiagnosticSeverity.warning,
    SolverDiagnosticCode.candidate_limit_reached: DiagnosticSeverity.error,
    SolverDiagnosticCode.backend_unsupported: DiagnosticSeverity.error,
    SolverDiagnosticCode.backend_failure: DiagnosticSeverity.error,
    SolverDiagnosticCode.resource_limit: DiagnosticSeverity.error,
    SolverDiagnosticCode.timeout: DiagnosticSeverity.error,
}

_SOLVE_PHASE_ORDER = {item: index for index, item in enumerate(SolvePhase)}
_DIAGNOSTIC_CODE_ORDER = {item: index for index, item in enumerate(SolverDiagnosticCode)}
_NUMERIC_BACKENDS = {
    SolveBackendKind.numeric_root,
    SolveBackendKind.ode_ivp,
    SolveBackendKind.event_root,
    SolveBackendKind.constrained_optimization,
}


def solver_phase_limit_s(
    phase: SolvePhase,
    backend: SolveBackendKind,
    budget: SolverBudget,
) -> float:
    """Map a plan phase/backend pair to its one configured elapsed-time limit."""

    if phase is SolvePhase.verification:
        return budget.verification_time_limit_s
    if phase is SolvePhase.numeric:
        return budget.numeric_time_limit_s
    if phase is SolvePhase.symbolic:
        return budget.symbolic_time_limit_s
    if backend in _NUMERIC_BACKENDS:
        return budget.numeric_time_limit_s
    return budget.symbolic_time_limit_s


class SolverDiagnosticEntry(FrozenModel):
    code: SolverDiagnosticCode
    severity: DiagnosticSeverity
    phase: SolvePhase
    backend: SolveBackendKind
    referenced_id: Identifier | None = None

    @model_validator(mode="after")
    def fixed_code_semantics(self) -> "SolverDiagnosticEntry":
        if self.severity is not _DIAGNOSTIC_SEVERITY[self.code]:
            raise ValueError("diagnostic code has one fixed severity")
        if self.code is SolverDiagnosticCode.backend_selected and self.phase is not SolvePhase.planning:
            raise ValueError("backend selection is a planning diagnostic")
        return self


class SolverAttempt(FrozenModel):
    attempt_index: StrictInt = Field(ge=0, le=2047)
    backend: SolveBackendKind
    phase: SolvePhase
    elapsed_s: FiniteFloat = Field(ge=0.0, le=1.0e12)
    completed: StrictBool


def diagnostic_entry_sort_key(
    item: SolverDiagnosticEntry,
) -> tuple[int, str, int, str]:
    """Canonical, deterministic diagnostics ordering key."""

    return (
        _SOLVE_PHASE_ORDER[item.phase],
        item.backend.value,
        _DIAGNOSTIC_CODE_ORDER[item.code],
        item.referenced_id or "",
    )


class SolverDiagnostics(FrozenModel):
    entries: tuple[SolverDiagnosticEntry, ...] = Field(default_factory=tuple, max_length=256)
    attempts: tuple[SolverAttempt, ...] = Field(default_factory=tuple, max_length=2048)
    total_elapsed_s: FiniteFloat = Field(ge=0.0, le=1.0e12)
    timeout: SolverTimeout | None = None

    @model_validator(mode="after")
    def validate_attempts(self) -> "SolverDiagnostics":
        indices = tuple(item.attempt_index for item in self.attempts)
        if indices != tuple(range(len(self.attempts))):
            raise ValueError("solver attempt indices must be contiguous from zero in recorded order")
        entry_keys = tuple(
            (item.code, item.phase, item.backend, item.referenced_id)
            for item in self.entries
        )
        if len(set(entry_keys)) != len(entry_keys):
            raise ValueError("solver diagnostic entries must be unique")
        if self.entries != tuple(sorted(self.entries, key=diagnostic_entry_sort_key)):
            raise ValueError("solver diagnostic entries must be in canonical deterministic order")
        if sum(item.elapsed_s for item in self.attempts) > self.total_elapsed_s + 1.0e-12:
            raise ValueError("attempt timing cannot exceed total timing")
        timeout_entries = tuple(item for item in self.entries if item.code is SolverDiagnosticCode.timeout)
        if (self.timeout is None) != (len(timeout_entries) == 0):
            raise ValueError("timeout diagnostic code and exact timeout details are required together")
        if len(timeout_entries) > 1:
            raise ValueError("timeout diagnostics must be unique")
        if self.timeout is not None:
            entry = timeout_entries[0]
            if entry.phase is not self.timeout.phase or entry.backend is not self.timeout.backend:
                raise ValueError("timeout diagnostic must exactly match timeout phase and backend")
            matching_attempts = tuple(
                item
                for item in self.attempts
                if item.phase is self.timeout.phase
                and item.backend is self.timeout.backend
                and not item.completed
            )
            if len(matching_attempts) != 1:
                raise ValueError("timeout requires exactly one matching incomplete solver attempt")
            timeout_attempt = matching_attempts[0]
            if timeout_attempt.attempt_index != len(self.attempts) - 1:
                raise ValueError("timeout attempt must be the final solver attempt")
            if any(not item.completed for item in self.attempts[:-1]):
                raise ValueError("every attempt before a timeout must be completed")
            if timeout_attempt.elapsed_s != self.timeout.elapsed_s:
                raise ValueError("timeout attempt elapsed time must exactly match timeout details")
            if self.timeout.elapsed_s > self.total_elapsed_s:
                raise ValueError("timeout elapsed time cannot exceed total diagnostics time")
        return self


__all__ = [
    "SOLVER_CONTRACT_VERSION", "SOLVER_POLICY_VERSION", "CandidateCoverage",
    "CandidateGenerationRecord", "CandidateRejection", "CandidateRejectionReason", "CandidateSet", "CandidateValue",
    "DiagnosticSeverity", "EquationGraph", "GraphStructureFeatures", "SolveBackendKind", "SolvePhase",
    "SolvePlan", "SolverAttempt", "SolverBudget", "SolverCandidate", "SolverDiagnosticCode",
    "SolverDiagnosticEntry", "SolverDiagnostics", "SolverTimeout", "candidate_generation_manifest",
    "canonical_candidate_id", "canonical_candidate_sha256", "create_solver_candidate",
    "derive_numeric_fallback", "derive_primary_backend", "diagnostic_entry_sort_key",
    "make_solver_candidate", "numeric_fallback_for_structure", "primary_backend_for_structure",
    "solver_phase_limit_s",
]
