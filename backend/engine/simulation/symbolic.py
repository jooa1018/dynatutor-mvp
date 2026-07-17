from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

import sympy as sp
from sympy.physics.mechanics import (
    LagrangesMethod,
    Particle,
    Point,
    ReferenceFrame,
    dynamicsymbols,
)

from engine.model_builder.typed_model import (
    Body,
    Constraint,
    CoordinateFrame,
    Dimension,
    Force,
    QuantityValue,
    TypedDynamicsModel,
    Vector2,
)
from engine.simulation.contracts import NumericSimulationSpec


SIMPLE_PENDULUM_VERSION = "phase50-simple-pendulum-v1"
MASS_SPRING_DAMPER_VERSION = "phase50-mass-spring-damper-v1"


@dataclass(frozen=True)
class NumericModelContract:
    model_id: str
    model_version: str
    state_variables: tuple[str, ...]
    state_units: Mapping[str, str]
    parameter_names: tuple[str, ...]
    parameter_units: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "state_units",
            MappingProxyType(dict(self.state_units)),
        )
        object.__setattr__(
            self,
            "parameter_units",
            MappingProxyType(dict(self.parameter_units)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "state_variables": list(self.state_variables),
            "state_units": dict(self.state_units),
            "parameter_names": list(self.parameter_names),
            "parameter_units": dict(self.parameter_units),
        }


MODEL_CONTRACTS: Mapping[str, NumericModelContract] = MappingProxyType(
    {
        "simple_pendulum": NumericModelContract(
            model_id="simple_pendulum",
            model_version=SIMPLE_PENDULUM_VERSION,
            state_variables=("theta", "theta_dot"),
            state_units={"theta": "rad", "theta_dot": "rad/s"},
            parameter_names=("m", "L", "g"),
            parameter_units={"m": "kg", "L": "m", "g": "m/s^2"},
        ),
        "mass_spring_damper": NumericModelContract(
            model_id="mass_spring_damper",
            model_version=MASS_SPRING_DAMPER_VERSION,
            state_variables=("x", "x_dot"),
            state_units={"x": "m", "x_dot": "m/s"},
            parameter_names=("m", "k", "c"),
            parameter_units={"m": "kg", "k": "N/m", "c": "N*s/m"},
        ),
    }
)


@dataclass(frozen=True)
class SymPyMechanicsSystem:
    model_id: str
    model_version: str
    typed_model: TypedDynamicsModel
    state_variables: tuple[str, ...]
    state_units: Mapping[str, str]
    coordinate_symbols: tuple[sp.Symbol, ...]
    speed_symbols: tuple[sp.Symbol, ...]
    parameter_names: tuple[str, ...]
    parameter_symbols: tuple[sp.Symbol, ...]
    parameter_units: Mapping[str, str]
    mass_matrix: sp.Matrix
    forcing: sp.Matrix
    total_energy: sp.Expr
    observables: Mapping[str, sp.Expr]
    constraint_residuals: Mapping[str, sp.Expr]
    equations_of_motion: tuple[sp.Expr, ...]
    derivation_metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "state_units",
            MappingProxyType(dict(self.state_units)),
        )
        object.__setattr__(
            self,
            "parameter_units",
            MappingProxyType(dict(self.parameter_units)),
        )
        object.__setattr__(
            self,
            "observables",
            MappingProxyType(dict(self.observables)),
        )
        object.__setattr__(
            self,
            "constraint_residuals",
            MappingProxyType(dict(self.constraint_residuals)),
        )
        object.__setattr__(
            self,
            "derivation_metadata",
            MappingProxyType(dict(self.derivation_metadata)),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "typed_model": typed_model_summary(self.typed_model),
            "state_variables": list(self.state_variables),
            "state_units": dict(self.state_units),
            "parameter_names": list(self.parameter_names),
            "parameter_units": dict(self.parameter_units),
            "mass_matrix": [
                [str(item) for item in row]
                for row in self.mass_matrix.tolist()
            ],
            "forcing": [str(item) for item in list(self.forcing)],
            "equations_of_motion": [
                str(item) for item in self.equations_of_motion
            ],
            "derivation_metadata": dict(self.derivation_metadata),
        }


def get_numeric_model_contract(model_id: str) -> NumericModelContract | None:
    return MODEL_CONTRACTS.get(model_id)


def list_numeric_model_contracts() -> list[dict[str, Any]]:
    return [
        MODEL_CONTRACTS[model_id].to_dict()
        for model_id in sorted(MODEL_CONTRACTS)
    ]


def _quantity(
    symbol: str,
    magnitude: float,
    unit: str,
    dimension: str,
) -> QuantityValue:
    return QuantityValue(
        symbol=symbol,
        magnitude=float(magnitude),
        unit=unit,
        dimension=dimension,
        display_unit=unit,
    )


def build_numeric_typed_model(spec: NumericSimulationSpec) -> TypedDynamicsModel:
    contract = get_numeric_model_contract(spec.model_id)
    if contract is None:
        raise ValueError(f"unsupported numeric model: {spec.model_id}")
    if spec.model_version != contract.model_version:
        raise ValueError(
            f"model_version must be {contract.model_version!r}"
        )

    if spec.model_id == "simple_pendulum":
        theta = sp.Symbol("theta", real=True)
        mass = _quantity("m", spec.parameters["m"], "kg", Dimension.MASS)
        length = _quantity("L", spec.parameters["L"], "m", Dimension.LENGTH)
        gravity = _quantity(
            "g",
            spec.parameters["g"],
            "m/s^2",
            Dimension.ACCELERATION,
        )
        x = sp.Symbol("L", positive=True) * sp.sin(theta)
        y = -sp.Symbol("L", positive=True) * sp.cos(theta)
        model = TypedDynamicsModel(
            system_type=spec.model_id,
            frames={"world": CoordinateFrame(id="world")},
            quantities={"m": mass, "L": length, "g": gravity},
            display_metadata={
                "offline_numeric_validation": True,
                "coordinate": "theta from downward vertical, CCW positive",
                "model_version": spec.model_version,
            },
        )
        model.bodies["bob"] = Body(
            id="bob",
            kind="particle",
            frame_id="world",
            mass=mass,
            center_of_mass=Vector2(x, y, "world", Dimension.LENGTH),
            geometry={"pendulum_length_m": length.magnitude},
        )
        model.forces.append(
            Force(
                id="bob_weight",
                kind="weight",
                body_id="bob",
                application_point=Vector2(
                    x,
                    y,
                    "world",
                    Dimension.LENGTH,
                ),
                vector=Vector2(
                    0,
                    -sp.Symbol("m", positive=True)
                    * sp.Symbol("g", positive=True),
                    "world",
                    Dimension.FORCE,
                ),
            )
        )
        model.constraints.append(
            Constraint(
                id="pendulum_length",
                kind="fixed_length",
                frame_id="world",
                dimension=Dimension.LENGTH,
                expression=x**2 + y**2 - sp.Symbol("L", positive=True) ** 2,
                display="x^2 + y^2 - L^2 = 0",
                related_bodies=["bob"],
            )
        )
        model.validate()
        return model

    x = sp.Symbol("x", real=True)
    x_dot = sp.Symbol("x_dot", real=True)
    mass = _quantity("m", spec.parameters["m"], "kg", Dimension.MASS)
    stiffness = _quantity("k", spec.parameters["k"], "N/m", "stiffness")
    damping = _quantity("c", spec.parameters["c"], "N*s/m", "damping")
    force_value = (
        -sp.Symbol("k", positive=True) * x
        - sp.Symbol("c", nonnegative=True) * x_dot
    )
    model = TypedDynamicsModel(
        system_type=spec.model_id,
        frames={"world": CoordinateFrame(id="world")},
        quantities={"m": mass, "k": stiffness, "c": damping},
        display_metadata={
            "offline_numeric_validation": True,
            "coordinate": "x from spring equilibrium, right positive",
            "model_version": spec.model_version,
        },
    )
    model.bodies["mass"] = Body(
        id="mass",
        kind="particle",
        frame_id="world",
        mass=mass,
        center_of_mass=Vector2(x, 0, "world", Dimension.LENGTH),
    )
    model.forces.append(
        Force(
            id="spring_damper_force",
            kind="spring_damper",
            body_id="mass",
            application_point=Vector2(x, 0, "world", Dimension.LENGTH),
            vector=Vector2(force_value, 0, "world", Dimension.FORCE),
            constitutive_relation=sp.Eq(
                sp.Symbol("F_sd"),
                force_value,
            ),
        )
    )
    model.validate()
    return model


def build_sympy_mechanics_system(
    spec: NumericSimulationSpec,
    typed_model: TypedDynamicsModel,
) -> SymPyMechanicsSystem:
    if typed_model.system_type != spec.model_id:
        raise ValueError("typed model and simulation spec model IDs differ")
    if spec.model_id == "simple_pendulum":
        return _derive_simple_pendulum(spec, typed_model)
    if spec.model_id == "mass_spring_damper":
        return _derive_mass_spring_damper(spec, typed_model)
    raise ValueError(f"unsupported numeric model: {spec.model_id}")


def _derive_simple_pendulum(
    spec: NumericSimulationSpec,
    typed_model: TypedDynamicsModel,
) -> SymPyMechanicsSystem:
    time_symbol = dynamicsymbols._t
    theta_dynamic = dynamicsymbols("theta")
    m, length, gravity = sp.symbols("m L g", positive=True)

    frame = ReferenceFrame("N")
    origin = Point("O")
    origin.set_vel(frame, 0)
    bob_point = origin.locatenew(
        "P",
        length * sp.sin(theta_dynamic) * frame.x
        - length * sp.cos(theta_dynamic) * frame.y,
    )
    bob_point.set_vel(frame, bob_point.pos_from(origin).dt(frame))
    bob = Particle("bob", bob_point, m)
    kinetic = bob.kinetic_energy(frame)
    potential = -m * gravity * length * sp.cos(theta_dynamic)
    lagrangian = kinetic - potential
    method = LagrangesMethod(lagrangian, [theta_dynamic], frame=frame)
    method.form_lagranges_equations()

    theta, theta_dot, theta_ddot = sp.symbols(
        "theta theta_dot theta_ddot",
        real=True,
    )
    substitutions = {
        theta_dynamic: theta,
        theta_dynamic.diff(time_symbol): theta_dot,
    }
    mass_matrix = sp.Matrix(method.mass_matrix).subs(substitutions)
    forcing = sp.Matrix(method.forcing).subs(substitutions)
    physical_energy = (kinetic + potential).subs(substitutions)
    energy = sp.simplify(physical_energy + m * gravity * length)
    length_residual = (
        (length * sp.sin(theta)) ** 2
        + (-length * sp.cos(theta)) ** 2
        - length**2
    )
    return SymPyMechanicsSystem(
        model_id=spec.model_id,
        model_version=spec.model_version,
        typed_model=typed_model,
        state_variables=("theta", "theta_dot"),
        state_units={"theta": "rad", "theta_dot": "rad/s"},
        coordinate_symbols=(theta,),
        speed_symbols=(theta_dot,),
        parameter_names=("m", "L", "g"),
        parameter_symbols=(m, length, gravity),
        parameter_units={"m": "kg", "L": "m", "g": "m/s^2"},
        mass_matrix=mass_matrix,
        forcing=forcing,
        total_energy=energy,
        observables={
            "theta": theta,
            "theta_dot": theta_dot,
            "bob_x": length * sp.sin(theta),
            "bob_y": -length * sp.cos(theta),
            "energy": energy,
        },
        constraint_residuals={"pendulum_length": length_residual},
        equations_of_motion=tuple(
            mass_matrix * sp.Matrix([theta_ddot]) - forcing
        ),
        derivation_metadata={
            "engine": "sympy.physics.mechanics.LagrangesMethod",
            "coordinate_convention": "theta from downward vertical, CCW positive",
            "derivation": "typed model -> Lagrangian -> mass matrix and forcing",
            "energy_reference": "zero at theta=0 equilibrium",
        },
    )


def _derive_mass_spring_damper(
    spec: NumericSimulationSpec,
    typed_model: TypedDynamicsModel,
) -> SymPyMechanicsSystem:
    time_symbol = dynamicsymbols._t
    x_dynamic = dynamicsymbols("x")
    m, stiffness, damping = sp.symbols("m k c", positive=True)

    frame = ReferenceFrame("N")
    origin = Point("O")
    origin.set_vel(frame, 0)
    mass_point = origin.locatenew("P", x_dynamic * frame.x)
    mass_point.set_vel(frame, mass_point.pos_from(origin).dt(frame))
    body = Particle("mass", mass_point, m)
    kinetic = body.kinetic_energy(frame)
    potential = sp.Rational(1, 2) * stiffness * x_dynamic**2
    lagrangian = kinetic - potential
    damping_force = -damping * x_dynamic.diff(time_symbol) * frame.x
    method = LagrangesMethod(
        lagrangian,
        [x_dynamic],
        forcelist=[(mass_point, damping_force)],
        frame=frame,
    )
    method.form_lagranges_equations()

    x, x_dot, x_ddot = sp.symbols("x x_dot x_ddot", real=True)
    substitutions = {
        x_dynamic: x,
        x_dynamic.diff(time_symbol): x_dot,
    }
    mass_matrix = sp.Matrix(method.mass_matrix).subs(substitutions)
    forcing = sp.Matrix(method.forcing).subs(substitutions)
    energy = (kinetic + potential).subs(substitutions)
    return SymPyMechanicsSystem(
        model_id=spec.model_id,
        model_version=spec.model_version,
        typed_model=typed_model,
        state_variables=("x", "x_dot"),
        state_units={"x": "m", "x_dot": "m/s"},
        coordinate_symbols=(x,),
        speed_symbols=(x_dot,),
        parameter_names=("m", "k", "c"),
        parameter_symbols=(m, stiffness, damping),
        parameter_units={"m": "kg", "k": "N/m", "c": "N*s/m"},
        mass_matrix=mass_matrix,
        forcing=forcing,
        total_energy=energy,
        observables={"x": x, "x_dot": x_dot, "energy": energy},
        constraint_residuals={},
        equations_of_motion=tuple(
            mass_matrix * sp.Matrix([x_ddot]) - forcing
        ),
        derivation_metadata={
            "engine": "sympy.physics.mechanics.LagrangesMethod",
            "coordinate_convention": "x from equilibrium, right positive",
            "derivation": "typed model -> Lagrangian and damping force -> mass matrix and forcing",
        },
    )


def typed_model_summary(model: TypedDynamicsModel) -> dict[str, Any]:
    return {
        "system_type": model.system_type,
        "frames": sorted(model.frames),
        "bodies": {
            body_id: {
                "kind": body.kind,
                "frame_id": body.frame_id,
            }
            for body_id, body in sorted(model.bodies.items())
        },
        "quantities": {
            name: {
                "magnitude": value.magnitude,
                "unit": value.unit,
                "dimension": value.dimension,
            }
            for name, value in sorted(model.quantities.items())
        },
        "force_kinds": sorted(force.kind for force in model.forces),
        "constraint_kinds": sorted(
            constraint.kind for constraint in model.constraints
        ),
        "display_metadata": dict(model.display_metadata),
    }


__all__ = [
    "MASS_SPRING_DAMPER_VERSION",
    "MODEL_CONTRACTS",
    "NumericModelContract",
    "SIMPLE_PENDULUM_VERSION",
    "SymPyMechanicsSystem",
    "build_numeric_typed_model",
    "build_sympy_mechanics_system",
    "get_numeric_model_contract",
    "list_numeric_model_contracts",
    "typed_model_summary",
]
