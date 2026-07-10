from engine.adapters.sympy_mechanics_adapter import (
    derive_connected_particles_spring,
    derive_mass_spring_damper,
    derive_model,
    derive_particle_on_rotating_rod,
    derive_planar_rigid_body_rotation,
    derive_simple_pendulum,
    list_mechanics_models,
)
from engine.adapters.pydy_adapter import (
    build_optional_pydy_system,
    build_pydy_blueprint,
    get_pydy_status,
    list_adapter_models,
)


def test_phase19_simple_pendulum_lagrange_equation():
    d = derive_simple_pendulum()
    assert d.name == "simple_pendulum"
    assert any("Derivative(theta(t), (t, 2))" in eq for eq in d.equations)
    assert any("g*sin(theta(t))" in eq for eq in d.equations)
    assert d.mass_matrix == [["L**2*m"]]


def test_phase19_mass_spring_damper_equation():
    d = derive_mass_spring_damper()
    eq = d.equations[0]
    assert "m*Derivative(x(t), (t, 2))" in eq
    assert "c*Derivative(x(t), t)" in eq
    assert "k*x(t)" in eq
    assert d.mass_matrix == [["m"]]


def test_phase19_particle_on_rotating_rod_equation():
    d = derive_particle_on_rotating_rod()
    eq = d.equations[0]
    assert "Derivative(r(t), (t, 2))" in eq
    assert "omega**2*r(t)" in eq
    assert d.mass_matrix == [["m"]]


def test_phase19_planar_rigid_body_rotation_equation():
    d = derive_planar_rigid_body_rotation()
    assert d.equations == ["I*Derivative(q(t), (t, 2)) - tau"]
    assert d.mass_matrix == [["I"]]
    assert d.forcing == ["tau"]


def test_phase19_connected_particles_spring_equations():
    d = derive_connected_particles_spring()
    assert len(d.equations) == 2
    assert d.mass_matrix == [["m1", "0"], ["0", "m2"]]
    assert any("m1*Derivative(x1(t), (t, 2))" in eq for eq in d.equations)
    assert any("m2*Derivative(x2(t), (t, 2))" in eq for eq in d.equations)


def test_phase19_derive_model_dispatch_and_list():
    names = {m["name"] for m in list_mechanics_models()}
    assert "simple_pendulum" in names
    assert "mass_spring_damper" in names
    assert derive_model("simple_pendulum").name == "simple_pendulum"
    assert derive_model("connected_particles").name == "connected_particles_spring"


def test_phase19_pydy_status_and_blueprint_are_safe_without_runtime_dependency():
    status = get_pydy_status()
    assert isinstance(status.available, bool)

    blueprint = build_pydy_blueprint("simple_pendulum")
    assert blueprint.name == "simple_pendulum"
    assert blueprint.realtime_safe is False
    assert any("theta" in c for c in blueprint.coordinates)
    assert any("g*sin(theta(t))" in eq for eq in blueprint.equations)

    payload = build_optional_pydy_system("simple_pendulum")
    assert "ok" in payload
    assert "blueprint" in payload
    assert payload["blueprint"]["name"] == "simple_pendulum"


def test_phase19_pydy_adapter_model_list():
    models = list_adapter_models()
    names = {m["name"] for m in models}
    assert "simple_pendulum" in names
    assert all(m["realtime_safe"] is False for m in models)
