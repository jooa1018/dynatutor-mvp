"""SymPy Mechanics adapter for high-level dynamics derivations.

Phase 19 turns this from a summary scaffold into an actual equation-generation
adapter. These examples are original DynaTutor wrappers around
``sympy.physics.mechanics`` and are kept separate from the fast closed-form
student solvers.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import sympy as sp
from sympy.physics.mechanics import LagrangesMethod, Particle, Point, ReferenceFrame, dynamicsymbols


@dataclass
class MechanicsDerivation:
    name: str
    coordinates: list[str]
    speeds: list[str]
    parameters: list[str]
    equations: list[str]
    mass_matrix: list[list[str]]
    forcing: list[str]
    energy: dict[str, str]
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MechanicsModelSummary:
    name: str
    coordinates: list[str]
    speeds: list[str]
    notes: list[str]


def _matrix_to_strings(mat) -> list[list[str]]:
    return [[str(sp.simplify(item)) for item in row] for row in mat.tolist()]


def _vector_to_strings(vec) -> list[str]:
    return [str(sp.simplify(item)) for item in list(vec)]


def _equations_from_lagranges_method(lm: LagrangesMethod) -> list[str]:
    return [str(sp.simplify(eq)) for eq in list(lm.eom)]


def simple_pendulum_summary() -> MechanicsModelSummary:
    return MechanicsModelSummary(
        name="simple_pendulum",
        coordinates=["theta"],
        speeds=["theta_dot"],
        notes=["SymPy Mechanics Lagrange derivation available via derive_simple_pendulum()."],
    )


def mass_spring_damper_summary() -> MechanicsModelSummary:
    return MechanicsModelSummary(
        name="mass_spring_damper",
        coordinates=["x"],
        speeds=["x_dot"],
        notes=["SymPy Mechanics derivation with damping force available via derive_mass_spring_damper()."],
    )


def derive_simple_pendulum() -> MechanicsDerivation:
    """Derive L*theta_ddot + g*sin(theta) = 0.

    Coordinates:
      theta measured from the downward vertical, positive counterclockwise.
    """
    t = dynamicsymbols._t
    theta = dynamicsymbols("theta")
    m, L, g = sp.symbols("m L g", positive=True)

    N = ReferenceFrame("N")
    O = Point("O")
    O.set_vel(N, 0)
    P = O.locatenew("P", L * sp.sin(theta) * N.x - L * sp.cos(theta) * N.y)
    P.set_vel(N, P.pos_from(O).dt(N))
    bob = Particle("bob", P, m)

    kinetic = bob.kinetic_energy(N)
    potential = -m * g * L * sp.cos(theta)
    lagrangian = kinetic - potential

    lm = LagrangesMethod(lagrangian, [theta], frame=N)
    lm.form_lagranges_equations()
    simplified_eq = sp.simplify(lm.eom[0] / (m * L))
    return MechanicsDerivation(
        name="simple_pendulum",
        coordinates=[str(theta)],
        speeds=[str(theta.diff(t))],
        parameters=["m", "L", "g"],
        equations=[str(simplified_eq)],
        mass_matrix=_matrix_to_strings(lm.mass_matrix),
        forcing=_vector_to_strings(lm.forcing),
        energy={"T": str(sp.simplify(kinetic)), "V": str(sp.simplify(potential)), "L": str(sp.simplify(lagrangian))},
        notes=["Generated with SymPy Mechanics LagrangesMethod.", "Equation is divided by m*L for readable normalized form."],
    )


def derive_mass_spring_damper() -> MechanicsDerivation:
    """Derive m*x_ddot + c*x_dot + k*x = 0."""
    t = dynamicsymbols._t
    x = dynamicsymbols("x")
    m, k, c = sp.symbols("m k c", positive=True)

    N = ReferenceFrame("N")
    O = Point("O")
    O.set_vel(N, 0)
    P = O.locatenew("P", x * N.x)
    P.set_vel(N, P.pos_from(O).dt(N))
    body = Particle("mass", P, m)

    kinetic = body.kinetic_energy(N)
    potential = sp.Rational(1, 2) * k * x**2
    lagrangian = kinetic - potential
    damping_force = -c * x.diff(t) * N.x

    lm = LagrangesMethod(lagrangian, [x], forcelist=[(P, damping_force)], frame=N)
    lm.form_lagranges_equations()
    normalized = sp.simplify(lm.eom[0])
    return MechanicsDerivation(
        name="mass_spring_damper",
        coordinates=[str(x)],
        speeds=[str(x.diff(t))],
        parameters=["m", "k", "c"],
        equations=[str(normalized)],
        mass_matrix=_matrix_to_strings(lm.mass_matrix),
        forcing=_vector_to_strings(lm.forcing),
        energy={"T": str(sp.simplify(kinetic)), "V": str(sp.simplify(potential)), "L": str(sp.simplify(lagrangian))},
        notes=["Generated with SymPy Mechanics LagrangesMethod and nonconservative damping force."],
    )


def derive_particle_on_rotating_rod() -> MechanicsDerivation:
    """Derive radial equation for a bead sliding on a rod rotating at constant omega.

    Assumption:
      theta(t)=omega*t is prescribed. No radial spring/force is included.
      The radial equation is m*r_ddot - m*omega^2*r = 0.
    """
    t = dynamicsymbols._t
    r = dynamicsymbols("r")
    m, omega = sp.symbols("m omega", positive=True)

    N = ReferenceFrame("N")
    A = N.orientnew("A", "Axis", [omega * t, N.z])
    O = Point("O")
    O.set_vel(N, 0)
    P = O.locatenew("P", r * A.x)
    P.set_vel(N, P.pos_from(O).dt(N))
    bead = Particle("bead", P, m)

    kinetic = bead.kinetic_energy(N)
    lagrangian = kinetic
    lm = LagrangesMethod(lagrangian, [r], frame=N)
    lm.form_lagranges_equations()
    normalized = sp.simplify(lm.eom[0] / m)
    return MechanicsDerivation(
        name="particle_on_rotating_rod",
        coordinates=[str(r)],
        speeds=[str(r.diff(t))],
        parameters=["m", "omega"],
        equations=[str(normalized)],
        mass_matrix=_matrix_to_strings(lm.mass_matrix),
        forcing=_vector_to_strings(lm.forcing),
        energy={"T": str(sp.simplify(kinetic)), "V": "0", "L": str(sp.simplify(lagrangian))},
        notes=["Generated with prescribed rod angle theta=omega*t.", "Radial equation exposes the centrifugal term -omega^2*r."],
    )


def derive_planar_rigid_body_rotation() -> MechanicsDerivation:
    """Derive fixed-axis planar rigid-body rotation I*q_ddot = tau.

    A rotating reference frame is used so the generalized torque can be supplied
    as a frame torque in SymPy Mechanics' forcelist.
    """
    t = dynamicsymbols._t
    q = dynamicsymbols("q")
    I, tau = sp.symbols("I tau", positive=True)

    N = ReferenceFrame("N")
    A = N.orientnew("A", "Axis", [q, N.z])
    A.set_ang_vel(N, q.diff(t) * N.z)

    kinetic = sp.Rational(1, 2) * I * q.diff(t) ** 2
    potential = 0
    lagrangian = kinetic - potential

    lm = LagrangesMethod(lagrangian, [q], forcelist=[(A, tau * N.z)], frame=N)
    lm.form_lagranges_equations()
    eq = sp.simplify(lm.eom[0])
    return MechanicsDerivation(
        name="planar_rigid_body_rotation",
        coordinates=[str(q)],
        speeds=[str(q.diff(t))],
        parameters=["I", "tau"],
        equations=[str(eq)],
        mass_matrix=_matrix_to_strings(lm.mass_matrix),
        forcing=_vector_to_strings(lm.forcing),
        energy={"T": str(sp.simplify(kinetic)), "V": "0", "L": str(sp.simplify(lagrangian))},
        notes=["Generated with SymPy Mechanics LagrangesMethod and a frame torque.", "Equivalent to I*q_ddot - tau = 0."],
    )


def derive_connected_particles_spring() -> MechanicsDerivation:
    """Derive 1D two-particle spring-coupled equations."""
    t = dynamicsymbols._t
    x1, x2 = dynamicsymbols("x1 x2")
    m1, m2, k, L0 = sp.symbols("m1 m2 k L0", positive=True)

    N = ReferenceFrame("N")
    O = Point("O")
    O.set_vel(N, 0)
    P1 = O.locatenew("P1", x1 * N.x)
    P2 = O.locatenew("P2", x2 * N.x)
    P1.set_vel(N, P1.pos_from(O).dt(N))
    P2.set_vel(N, P2.pos_from(O).dt(N))
    body1 = Particle("body1", P1, m1)
    body2 = Particle("body2", P2, m2)

    kinetic = body1.kinetic_energy(N) + body2.kinetic_energy(N)
    stretch = x2 - x1 - L0
    potential = sp.Rational(1, 2) * k * stretch**2
    lagrangian = kinetic - potential
    lm = LagrangesMethod(lagrangian, [x1, x2], frame=N)
    lm.form_lagranges_equations()

    return MechanicsDerivation(
        name="connected_particles_spring",
        coordinates=[str(x1), str(x2)],
        speeds=[str(x1.diff(t)), str(x2.diff(t))],
        parameters=["m1", "m2", "k", "L0"],
        equations=_equations_from_lagranges_method(lm),
        mass_matrix=_matrix_to_strings(lm.mass_matrix),
        forcing=_vector_to_strings(lm.forcing),
        energy={"T": str(sp.simplify(kinetic)), "V": str(sp.simplify(potential)), "L": str(sp.simplify(lagrangian))},
        notes=["Generated with two 1D particles connected by a linear spring."],
    )


def derive_model(name: str) -> MechanicsDerivation:
    table = {
        "simple_pendulum": derive_simple_pendulum,
        "mass_spring_damper": derive_mass_spring_damper,
        "particle_on_rotating_rod": derive_particle_on_rotating_rod,
        "rotating_rod_particle": derive_particle_on_rotating_rod,
        "planar_rigid_body_rotation": derive_planar_rigid_body_rotation,
        "connected_particles": derive_connected_particles_spring,
        "connected_particles_spring": derive_connected_particles_spring,
    }
    if name not in table:
        raise ValueError(f"Unknown SymPy Mechanics model: {name}")
    return table[name]()


def list_mechanics_models() -> list[dict[str, Any]]:
    return [
        {"name": "simple_pendulum", "purpose": "derive pendulum equation"},
        {"name": "mass_spring_damper", "purpose": "derive damped oscillator equation"},
        {"name": "particle_on_rotating_rod", "purpose": "derive rotating rod radial equation"},
        {"name": "planar_rigid_body_rotation", "purpose": "derive fixed-axis rotation equation"},
        {"name": "connected_particles_spring", "purpose": "derive two-particle spring-coupled equations"},
    ]
