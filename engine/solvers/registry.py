from engine.models import CanonicalProblem
from engine.solvers.base import BaseSolver
from engine.solvers.incline import InclineNoFrictionSolver, InclineWithFrictionSolver
from engine.solvers.newton import SingleParticleNewtonSolver
from engine.solvers.pulley import AtwoodPulleySolver, TableHangingPulleySolver, InclineHangingPulleySolver, MassivePulleyAtwoodSolver
from engine.solvers.rolling import PureRollingEnergySolver, RollingEnergyGeneralSolver
from engine.solvers.vertical_circle import VerticalCircleSolver
from engine.solvers.collision import Collision1DSolver
from engine.solvers.kinematics import ConstantAcceleration1DSolver
from engine.solvers.projectile import ProjectileMotionSolver
from engine.solvers.work_rotation_impulse import ConstantForceWorkSolver, FixedAxisRotationSolver, ImpulseMomentumSolver
from engine.solvers.energy_vibration import SpringMassVibrationSolver, SpringEnergySpeedSolver, WorkEnergySpeedSolver, HorizontalFrictionForceSolver
from engine.solvers.curves import FlatCurveFrictionSolver, BankedCurveNoFrictionSolver
from engine.solvers.advanced_motion import PolarKinematicsSolver, InstantCenterVelocitySolver, SlotPinRelativeMotionSolver
from engine.solvers.advanced_dynamics import CoriolisRelativeMotionSolver
from engine.solvers.rigid_body_2d import PlaneRigidBodyVelocitySolver, PlaneRigidBodyAccelerationSolver, RelativeAccelerationTranslationSolver


class SolverRegistry:
    def __init__(self) -> None:
        self.solvers: list[BaseSolver] = [
            SingleParticleNewtonSolver(),
            InclineNoFrictionSolver(),
            InclineWithFrictionSolver(),
            AtwoodPulleySolver(),
            TableHangingPulleySolver(),
            InclineHangingPulleySolver(),
            MassivePulleyAtwoodSolver(),
            PureRollingEnergySolver(),
            RollingEnergyGeneralSolver(),
            VerticalCircleSolver(),
            Collision1DSolver(),
            ConstantAcceleration1DSolver(),
            ProjectileMotionSolver(),
            ConstantForceWorkSolver(),
            FixedAxisRotationSolver(),
            HorizontalFrictionForceSolver(),
            ImpulseMomentumSolver(),
            WorkEnergySpeedSolver(),
            SpringMassVibrationSolver(),
            SpringEnergySpeedSolver(),
            FlatCurveFrictionSolver(),
            BankedCurveNoFrictionSolver(),
            RelativeAccelerationTranslationSolver(),
            CoriolisRelativeMotionSolver(),
            PlaneRigidBodyAccelerationSolver(),
            PolarKinematicsSolver(),
            InstantCenterVelocitySolver(),
            SlotPinRelativeMotionSolver(),
            PlaneRigidBodyVelocitySolver(),
        ]

    def select(self, c: CanonicalProblem) -> BaseSolver | None:
        matches = [m for s in self.solvers if (m := s.match(c))]
        if not matches:
            return None
        matches.sort(key=lambda m: m.score, reverse=True)
        chosen = matches[0]
        chosen.solver.reason = chosen.reason
        return chosen.solver
