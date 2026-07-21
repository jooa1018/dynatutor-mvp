"""Single-pass internal orchestration for generic mechanics rollout modes."""

from __future__ import annotations

from engine.mechanics.compiler import (
    MechanicsCompiler,
    authorize_validated_mechanics_ir,
)
from engine.mechanics.compiler.contracts import ValidatedIRAuthorization
from engine.mechanics.modeler import MechanicsModeler, MechanicsModelerOutcome, ModelerTerminal
from engine.mechanics.modeler_config import MechanicsIRMode, MechanicsModelerConfig
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.verification.contracts import MechanicsSolveTerminal

from engine.mechanics.runtime.contracts import (
    MechanicsRuntimeExecution,
    RuntimeDelivery,
    RuntimeFailure,
    RuntimeTerminal,
    compiler_result_is_coherent,
    is_exact_confirmation_fingerprint,
    modeler_outcome_is_coherent,
    solve_result_is_coherent,
)


def _active_delivery(mode: MechanicsIRMode, *, solved: bool = False) -> RuntimeDelivery:
    if mode is MechanicsIRMode.shadow:
        return RuntimeDelivery.legacy
    if solved:
        return RuntimeDelivery.generic
    return RuntimeDelivery.none


def _authorization_is_coherent(value: object) -> bool:
    if type(value) is not ValidatedIRAuthorization:
        return False
    try:
        rebuilt = ValidatedIRAuthorization.model_validate(
            value.model_dump(mode="python", warnings="none")
        )
    except Exception:
        return False
    return rebuilt == value


class MechanicsRuntimeOrchestrator:
    """Evaluate one problem through the exact modeler-to-graph authority path."""

    __slots__ = ("_config", "_modeler")

    def __init__(
        self,
        config: MechanicsModelerConfig,
        *,
        modeler: MechanicsModeler | object | None = None,
    ) -> None:
        if type(config) is not MechanicsModelerConfig:
            raise TypeError("runtime requires an exact trusted modeler config")
        self._config = config
        self._modeler = modeler

    @property
    def config(self) -> MechanicsModelerConfig:
        return self._config

    def evaluate(
        self,
        problem_text: str,
        *,
        confirmation_fingerprint: str | None = None,
    ) -> MechanicsRuntimeExecution:
        """Run at most one model operation and retain one immutable execution."""

        mode = self._config.mode
        if mode is MechanicsIRMode.off:
            return MechanicsRuntimeExecution(
                mode=mode,
                terminal=RuntimeTerminal.off,
                delivery=RuntimeDelivery.legacy,
            )

        delivery = _active_delivery(mode)
        if not self._config.enabled:
            return MechanicsRuntimeExecution(
                mode=mode,
                terminal=RuntimeTerminal.disabled,
                delivery=delivery,
            )

        if (
            mode is MechanicsIRMode.confirm
            and confirmation_fingerprint is not None
            and not is_exact_confirmation_fingerprint(confirmation_fingerprint)
        ):
            return MechanicsRuntimeExecution(
                mode=mode,
                terminal=RuntimeTerminal.confirmation_invalid,
                delivery=delivery,
            )

        modeler = self._modeler
        if modeler is None:
            try:
                modeler = MechanicsModeler(self._config)
            except Exception:
                return self._failure(RuntimeFailure.modeler_construction)

        try:
            outcome = modeler.model(problem_text)
        except Exception:
            return self._failure(RuntimeFailure.modeler_execution)

        try:
            valid_outcome = modeler_outcome_is_coherent(outcome)
        except Exception:
            valid_outcome = False
        if not valid_outcome:
            return self._failure(RuntimeFailure.modeler_contract)
        exact_outcome = outcome

        if exact_outcome.terminal is not ModelerTerminal.accepted:
            return MechanicsRuntimeExecution(
                mode=mode,
                terminal=RuntimeTerminal.modeler_rejected,
                delivery=delivery,
                modeler_outcome=exact_outcome,
            )

        if mode is MechanicsIRMode.confirm and (
            confirmation_fingerprint is None
            or confirmation_fingerprint != exact_outcome.calculation_fingerprint
        ):
            return MechanicsRuntimeExecution(
                mode=mode,
                terminal=RuntimeTerminal.confirmation_needed,
                delivery=delivery,
                modeler_outcome=exact_outcome,
                current_calculation_fingerprint=exact_outcome.calculation_fingerprint,
            )

        exact_ir = exact_outcome.ir
        try:
            authorization = authorize_validated_mechanics_ir(exact_ir)
        except Exception:
            return self._failure(
                RuntimeFailure.authorization,
                modeler_outcome=exact_outcome,
            )
        if not _authorization_is_coherent(authorization):
            return self._failure(
                RuntimeFailure.authorization,
                modeler_outcome=exact_outcome,
            )

        try:
            compiler = MechanicsCompiler()
        except Exception:
            return self._failure(
                RuntimeFailure.compiler_construction,
                modeler_outcome=exact_outcome,
            )
        try:
            compiler_result = compiler.compile(
                exact_ir,
                validated_ir_authorization=authorization,
            )
        except Exception:
            return self._failure(
                RuntimeFailure.compiler_execution,
                modeler_outcome=exact_outcome,
            )

        try:
            valid_compiler_result = compiler_result_is_coherent(compiler_result)
        except Exception:
            valid_compiler_result = False
        if not valid_compiler_result:
            return self._failure(
                RuntimeFailure.compiler_contract,
                modeler_outcome=exact_outcome,
            )
        if not compiler_result.compilable or compiler_result.graph is None:
            return MechanicsRuntimeExecution(
                mode=mode,
                terminal=RuntimeTerminal.compiler_rejected,
                delivery=delivery,
                modeler_outcome=exact_outcome,
                compiler_result=compiler_result,
            )

        exact_graph = compiler_result.graph
        try:
            solve_result = solve_verified_equation_graph(exact_graph)
        except Exception:
            return self._failure(
                RuntimeFailure.solver_execution,
                modeler_outcome=exact_outcome,
                compiler_result=compiler_result,
            )

        try:
            valid_solve_result = solve_result_is_coherent(solve_result, exact_graph)
        except Exception:
            valid_solve_result = False
        if not valid_solve_result:
            return self._failure(
                RuntimeFailure.solver_contract,
                modeler_outcome=exact_outcome,
                compiler_result=compiler_result,
            )
        if solve_result.terminal is not MechanicsSolveTerminal.solved:
            return MechanicsRuntimeExecution(
                mode=mode,
                terminal=RuntimeTerminal.solve_rejected,
                delivery=delivery,
                modeler_outcome=exact_outcome,
                compiler_result=compiler_result,
                solve_result=solve_result,
            )
        return MechanicsRuntimeExecution(
            mode=mode,
            terminal=RuntimeTerminal.solved,
            delivery=_active_delivery(mode, solved=True),
            modeler_outcome=exact_outcome,
            compiler_result=compiler_result,
            solve_result=solve_result,
        )

    def _failure(
        self,
        failure: RuntimeFailure,
        *,
        modeler_outcome: MechanicsModelerOutcome | None = None,
        compiler_result=None,
    ) -> MechanicsRuntimeExecution:
        return MechanicsRuntimeExecution(
            mode=self._config.mode,
            terminal=RuntimeTerminal.failed,
            delivery=_active_delivery(self._config.mode),
            failure=failure,
            modeler_outcome=modeler_outcome,
            compiler_result=compiler_result,
        )


__all__ = ["MechanicsRuntimeOrchestrator"]
