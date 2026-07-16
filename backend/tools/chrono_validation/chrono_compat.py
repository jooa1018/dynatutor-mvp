from __future__ import annotations

from dataclasses import dataclass
import importlib
import math
from types import ModuleType
from typing import Any, Iterable

try:
    from .version_evidence import PyChronoEvidenceError, installed_pychrono_version
except ImportError:  # direct script execution from tools/chrono_validation
    from version_evidence import PyChronoEvidenceError, installed_pychrono_version


COLLISION_ENVELOPE_M = 0.001
COLLISION_SAFE_MARGIN_M = 0.001


class ChronoCompatibilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChronoImport:
    module: ModuleType | None
    status: str
    message: str

    @property
    def available(self) -> bool:
        return self.module is not None and self.status == "available"


def import_chrono() -> ChronoImport:
    missing_messages: list[str] = []
    incomplete_messages: list[str] = []
    for name in ("pychrono", "pychrono.core"):
        try:
            module = importlib.import_module(name)
            if not hasattr(module, "ChSystemNSC"):
                incomplete_messages.append(
                    f"{name} imported but does not expose ChSystemNSC"
                )
                continue
            return ChronoImport(module=module, status="available", message=f"imported {name}")
        except ModuleNotFoundError as exc:
            missing_root = str(exc.name or "").split(".", 1)[0]
            if missing_root != "pychrono":
                return ChronoImport(
                    module=None,
                    status="error",
                    message=f"{name} is installed but a transitive module is missing: {exc}",
                )
            missing_messages.append(f"{name}: {exc}")
        except (ImportError, OSError) as exc:
            return ChronoImport(
                module=None,
                status="error",
                message=f"{name} installation/ABI error: {type(exc).__name__}: {exc}",
            )
        except Exception as exc:
            return ChronoImport(
                module=None,
                status="error",
                message=f"{name} import raised {type(exc).__name__}: {exc}",
            )
    if incomplete_messages:
        return ChronoImport(
            module=None,
            status="error",
            message="; ".join(incomplete_messages + missing_messages),
        )
    return ChronoImport(
        module=None,
        status="unavailable",
        message="; ".join(missing_messages) or "PyChrono is not installed",
    )


class ChronoAdapter:
    def __init__(self, module: ModuleType):
        self.chrono = module

    @property
    def version(self) -> str:
        try:
            return installed_pychrono_version(self.chrono)
        except PyChronoEvidenceError:
            return "unknown"

    def vector(self, x: float, y: float, z: float) -> Any:
        cls = self._attribute("ChVector3d", "ChVectorD")
        return cls(float(x), float(y), float(z))

    def vector_component(self, vector: Any, axis: str) -> float:
        axis = axis.lower()
        for name in (axis, axis.upper(), f"Get{axis.upper()}"):
            value = getattr(vector, name, None)
            if value is None:
                continue
            return _finite(value() if callable(value) else value, name=f"vector.{axis}")
        try:
            index = {"x": 0, "y": 1, "z": 2}[axis]
            return _finite(vector[index], name=f"vector[{index}]")
        except (KeyError, TypeError, IndexError):
            raise ChronoCompatibilityError(f"cannot read {axis}-component from {type(vector).__name__}")

    def new_nsc_system(
        self,
        *,
        gravity: tuple[float, float, float],
        max_iterations: int = 200,
    ) -> tuple[Any, str]:
        if isinstance(max_iterations, bool) or int(max_iterations) <= 0:
            raise ChronoCompatibilityError("solver max_iterations must be positive")
        system = self._attribute("ChSystemNSC")()
        self._configure_bullet_collision(system)
        gravity_vector = self.vector(*gravity)
        self._call(
            system,
            ("SetGravitationalAcceleration", "Set_G_acc", "SetGravity"),
            gravity_vector,
        )
        solver = self._configure_psor(system, max_iterations=int(max_iterations))
        if hasattr(system, "SetMinBounceSpeed"):
            system.SetMinBounceSpeed(0.0)
        return system, solver

    def _configure_bullet_collision(self, system: Any) -> None:
        holder = self._attribute("ChCollisionSystem")
        candidates: list[Any] = []
        type_holder = getattr(holder, "Type", None)
        if type_holder is not None:
            candidates.extend(
                getattr(type_holder, name, None)
                for name in ("BULLET", "Type_BULLET")
            )
        candidates.extend(
            getattr(holder, name, None)
            for name in ("Type_BULLET", "BULLET")
        )
        candidates.extend(
            getattr(self.chrono, name, None)
            for name in ("ChCollisionSystemType_BULLET", "ChCollisionSystem_BULLET")
        )
        bullet = next((item for item in candidates if item is not None), None)
        if bullet is None:
            raise ChronoCompatibilityError(
                "PyChrono does not expose the BULLET collision-system enum"
            )
        self._call(system, ("SetCollisionSystemType",), bullet)
        collision_system = self._call(system, ("GetCollisionSystem",))
        if collision_system is None:
            raise ChronoCompatibilityError(
                "PyChrono did not create the requested BULLET collision system"
            )

    def _configure_psor(self, system: Any, *, max_iterations: int) -> str:
        holder = self._attribute("ChSolver")
        candidates: list[Any] = []
        type_holder = getattr(holder, "Type", None)
        if type_holder is not None:
            candidates.extend(
                getattr(type_holder, name, None)
                for name in ("PSOR", "Type_PSOR")
            )
        candidates.extend(
            getattr(holder, name, None)
            for name in ("Type_PSOR", "PSOR")
        )
        psor = next((item for item in candidates if item is not None), None)
        if psor is None:
            raise ChronoCompatibilityError("PyChrono does not expose the PSOR solver enum")
        self._call(system, ("SetSolverType",), psor)
        solver = self._call(system, ("GetSolver",))
        iterative = solver
        as_iterative = getattr(solver, "AsIterative", None)
        if callable(as_iterative):
            candidate = as_iterative()
            if candidate is not None:
                iterative = candidate
        self._call(
            iterative,
            ("SetMaxIterations", "SetMaxIters"),
            int(max_iterations),
        )
        return (
            f"{type(solver).__name__}:PSOR:"
            f"max_iterations={int(max_iterations)}"
        )

    def contact_material_nsc(self, *, friction: float, restitution: float = 0.0) -> Any:
        cls = self._attribute("ChContactMaterialNSC", "ChMaterialSurfaceNSC")
        material = cls()
        self._call(material, ("SetFriction",), float(friction))
        self._call(material, ("SetRestitution",), float(restitution))
        set_rolling = getattr(material, "SetRollingFriction", None)
        if callable(set_rolling):
            set_rolling(0.0)
        set_spinning = getattr(material, "SetSpinningFriction", None)
        if callable(set_spinning):
            set_spinning(0.0)
        return material

    def easy_box(
        self,
        *,
        size_x: float,
        size_y: float,
        size_z: float,
        density: float,
        material: Any,
    ) -> Any:
        cls = self._attribute("ChBodyEasyBox")
        try:
            body = cls(size_x, size_y, size_z, density, False, True, material)
        except TypeError:
            body = cls(size_x, size_y, size_z, density, material)
        self._enable_collision(body)
        return body

    def easy_sphere(self, *, radius: float, density: float, material: Any) -> Any:
        cls = self._attribute("ChBodyEasySphere")
        try:
            body = cls(radius, density, False, True, material)
        except TypeError:
            body = cls(radius, density, material)
        self._enable_collision(body)
        return body

    def easy_cylinder_z(
        self,
        *,
        radius: float,
        height: float,
        density: float,
        material: Any,
    ) -> Any:
        body = self._attribute("ChBody")()
        shape = self._attribute("ChCollisionShapeCylinder")(
            material,
            float(radius),
            float(height),
        )
        attached = self._call(body, ("AddCollisionShape",), shape)
        if attached is False:
            raise ChronoCompatibilityError("ChBody.AddCollisionShape returned false")

        model = self._call(body, ("GetCollisionModel",))
        if model is None:
            raise ChronoCompatibilityError(
                "ChBody did not create a collision model for its cylinder shape"
            )
        self._call(model, ("Clear",))
        self._call(model, ("SetEnvelope",), COLLISION_ENVELOPE_M)
        self._call(model, ("SetSafeMargin",), COLLISION_SAFE_MARGIN_M)
        added = self._call(model, ("AddShape",), shape)
        if added is False:
            raise ChronoCompatibilityError("ChCollisionModel.AddShape returned false")

        mass = float(density) * math.pi * float(radius) ** 2 * float(height)
        transverse_inertia = (
            mass * (3.0 * float(radius) ** 2 + float(height) ** 2) / 12.0
        )
        axial_inertia = 0.5 * mass * float(radius) ** 2
        self._call(body, ("SetMass",), mass)
        self._call(
            body,
            ("SetInertiaXX",),
            self.vector(transverse_inertia, transverse_inertia, axial_inertia),
        )
        self._enable_collision(body)

        actual = self.collision_geometry(body)
        if not math.isclose(
            actual["envelope_m"],
            COLLISION_ENVELOPE_M,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ChronoCompatibilityError(
                f"custom cylinder collision envelope mismatch: {actual['envelope_m']}"
            )
        if not math.isclose(
            actual["safe_margin_m"],
            COLLISION_SAFE_MARGIN_M,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ChronoCompatibilityError(
                f"custom cylinder collision safe margin mismatch: {actual['safe_margin_m']}"
            )
        return body

    def new_planar_guide(self, body: Any, reference: Any) -> Any:
        guide = self._attribute("ChLinkMatePlanar")()
        origin = self.vector(0.0, 0.0, 0.0)
        normal = self.vector(0.0, 0.0, 1.0)
        initialized = self._call(
            guide,
            ("Initialize",),
            body,
            reference,
            False,
            origin,
            origin,
            normal,
            normal,
        )
        if initialized is False:
            raise ChronoCompatibilityError("ChLinkMatePlanar.Initialize returned false")
        return guide

    def _enable_collision(self, body: Any) -> None:
        self._call(body, ("EnableCollision", "SetCollide"), True)
        enabled = getattr(body, "IsCollisionEnabled", None)
        if callable(enabled) and not bool(enabled()):
            raise ChronoCompatibilityError(
                f"{type(body).__name__} did not enable its collision model"
            )

    def _axis_z(self) -> Any | None:
        value = getattr(self.chrono, "ChAxis_Z", None)
        if value is not None:
            return value
        holder = getattr(self.chrono, "ChAxis", None)
        if holder is None:
            return None
        for name in ("Z", "_Z"):
            value = getattr(holder, name, None)
            if value is not None:
                return value
        return None

    def _quat_from_angle_x(self, angle: float) -> Any:
        for name in ("QuatFromAngleX", "Q_from_AngX"):
            fn = getattr(self.chrono, name, None)
            if callable(fn):
                return fn(float(angle))
        cls = self._attribute("ChQuaterniond", "ChQuaternionD")
        half = float(angle) / 2.0
        return cls(math.cos(half), math.sin(half), 0.0, 0.0)

    def add(self, system: Any, item: Any, *, shaft: bool = False) -> None:
        if not shaft:
            self._call(system, ("Add", "AddBody"), item)
            return
        type_errors: list[str] = []
        for name in ("Add", "AddShaft"):
            method = getattr(system, name, None)
            if not callable(method):
                continue
            try:
                method(item)
                return
            except TypeError as exc:
                type_errors.append(f"{name}: {exc}")
        detail = "; ".join(type_errors) or "neither Add nor AddShaft is callable"
        raise ChronoCompatibilityError(
            f"cannot attach {type(item).__name__} shaft to the Chrono system: {detail}"
        )

    def set_fixed(self, body: Any, fixed: bool) -> None:
        self._call(body, ("SetFixed", "SetBodyFixed"), bool(fixed))

    def disable_sleeping(self, body: Any) -> None:
        for name in ("SetSleepingAllowed", "SetUseSleeping"):
            fn = getattr(body, name, None)
            if callable(fn):
                fn(False)
                return

    def set_position(self, body: Any, xyz: tuple[float, float, float]) -> None:
        self._call(body, ("SetPos",), self.vector(*xyz))

    def position(self, body: Any) -> tuple[float, float, float]:
        value = self._call(body, ("GetPos",))
        return tuple(self.vector_component(value, axis) for axis in "xyz")

    def set_linear_velocity(self, body: Any, xyz: tuple[float, float, float]) -> None:
        self._call(body, ("SetLinVel", "SetPosDt", "SetPos_dt"), self.vector(*xyz))

    def linear_velocity(self, body: Any) -> tuple[float, float, float]:
        value = self._call(body, ("GetLinVel", "GetPosDt", "GetPos_dt"))
        return tuple(self.vector_component(value, axis) for axis in "xyz")

    def angular_velocity_parent(self, body: Any) -> tuple[float, float, float]:
        value = self._call(body, ("GetAngVelParent", "GetWvel_par"))
        return tuple(self.vector_component(value, axis) for axis in "xyz")

    def contact_force(self, body: Any) -> tuple[float, float, float]:
        value = self._call(body, ("GetContactForce",))
        return tuple(self.vector_component(value, axis) for axis in "xyz")

    def collision_geometry(self, body: Any) -> dict[str, float]:
        model = self._call(body, ("GetCollisionModel",))
        return {
            "envelope_m": _finite(
                self._call(model, ("GetEnvelope",)),
                name="body collision envelope",
            ),
            "safe_margin_m": _finite(
                self._call(model, ("GetSafeMargin",)),
                name="body collision safe margin",
            ),
        }

    def mass(self, body: Any) -> float:
        return _finite(self._call(body, ("GetMass",)), name="body mass")

    def inertia_axis(self, body: Any, axis: str) -> float:
        value = self._call(body, ("GetInertiaXX",))
        return self.vector_component(value, axis)

    def step(self, system: Any, step_size: float) -> None:
        self._call(system, ("DoStepDynamics",), float(step_size))

    def time(self, system: Any) -> float:
        return _finite(self._call(system, ("GetChTime", "GetTime")), name="system time")

    def new_shaft(self, *, inertia: float, applied_load: float) -> Any:
        shaft = self._attribute("ChShaft")()
        self._call(shaft, ("SetInertia",), float(inertia))
        self._call(shaft, ("SetAppliedLoad", "SetAppliedTorque"), float(applied_load))
        return shaft

    def shaft_position(self, shaft: Any) -> float:
        return _finite(self._call(shaft, ("GetPos",)), name="shaft position")

    def shaft_speed(self, shaft: Any) -> float:
        return _finite(self._call(shaft, ("GetPosDt", "GetPos_dt")), name="shaft speed")

    def shaft_acceleration(self, shaft: Any) -> float:
        return _finite(
            self._call(shaft, ("GetPosDt2", "GetPos_dtdt")),
            name="shaft acceleration",
        )

    def new_gear(self, shaft_1: Any, shaft_2: Any, *, ratio: float) -> Any:
        gear = self._attribute("ChShaftsGear")()
        initialized = self._call(gear, ("Initialize",), shaft_1, shaft_2)
        if initialized is False:
            raise ChronoCompatibilityError("ChShaftsGear.Initialize returned false")
        self._call(gear, ("SetTransmissionRatio",), float(ratio))
        return gear

    def gear_reaction_1(self, gear: Any) -> float:
        return _finite(
            self._call(gear, ("GetReaction1", "GetTorqueReactionOn1")),
            name="gear reaction on shaft 1",
        )

    def gear_constraint_violation(self, gear: Any) -> float | None:
        fn = getattr(gear, "GetConstraintViolation", None)
        if not callable(fn):
            return None
        return _finite(fn(), name="gear constraint violation")

    def _attribute(self, *names: str) -> Any:
        for name in names:
            value = getattr(self.chrono, name, None)
            if value is not None:
                return value
        raise ChronoCompatibilityError(
            f"PyChrono {self.version} lacks required API: {' or '.join(names)}"
        )

    @staticmethod
    def _call(target: Any, names: Iterable[str], *args: Any) -> Any:
        for name in names:
            fn = getattr(target, name, None)
            if callable(fn):
                return fn(*args)
        raise ChronoCompatibilityError(
            f"{type(target).__name__} lacks required method: {' or '.join(names)}"
        )


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ChronoCompatibilityError(f"{name} is bool, expected a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ChronoCompatibilityError(f"{name} is not finite")
    return parsed


__all__ = [
    "COLLISION_ENVELOPE_M",
    "COLLISION_SAFE_MARGIN_M",
    "ChronoAdapter",
    "ChronoCompatibilityError",
    "ChronoImport",
    "import_chrono",
]
