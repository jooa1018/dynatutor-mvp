"""Phase 54: versioned VisualizationScene DTO.

Contract summary
----------------
- ``dynatutor.visualization_scene`` v1.0 is an additive, optional projection of
  already-finalized backend results into a render-ready 2D scene.
- The scene is playback material only.  Every motion segment is a closed-form
  program derived from post-gate backend answers; the frontend (Rapier2D or
  any other runtime) replays it and may never feed values back.
- Answer authority stays with the backend: the ``authority`` block is made of
  ``Literal`` fields, so a scene claiming any other authority fails validation
  at construction time.  Numbers must be finite; NaN/Infinity are rejected.
- ``status="ready"`` requires bodies, motion, camera, and timestep;
  ``status="unavailable"`` requires ``fallback_reason`` and forbids playback
  material, so an unsupported problem can never masquerade as a ready scene.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VISUALIZATION_SCENE_SCHEMA = "dynatutor.visualization_scene"
VISUALIZATION_SCENE_VERSION = "1.0"

# Every float in the scene tree rejects NaN/Infinity at validation time.
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]

SceneType = Literal["incline_block", "mass_spring", "pure_rolling", "collision_1d", "pendulum"]


class _SceneModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VizVec2(_SceneModel):
    x: FiniteFloat
    y: FiniteFloat


class VizShapeModel(_SceneModel):
    """Render shape. Sizes are world-meters unless the body is schematic."""

    kind: Literal["rect", "circle", "wedge", "wall", "spring_coil", "ground_line"]
    half_width: FiniteFloat | None = None
    half_height: FiniteFloat | None = None
    radius: FiniteFloat | None = None
    # wedge: right triangle with horizontal base; angle in degrees.
    angle_deg: FiniteFloat | None = None
    base_length: FiniteFloat | None = None

    @model_validator(mode="after")
    def _check_kind_params(self) -> "VizShapeModel":
        if self.kind == "rect" and (self.half_width is None or self.half_height is None):
            raise ValueError("rect shape requires half_width and half_height")
        if self.kind == "circle" and self.radius is None:
            raise ValueError("circle shape requires radius")
        if self.kind == "wedge" and (self.angle_deg is None or self.base_length is None):
            raise ValueError("wedge shape requires angle_deg and base_length")
        for name in ("half_width", "half_height", "radius", "base_length"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")
        return self


class VizBodyModel(_SceneModel):
    id: str = Field(min_length=1)
    label: str
    role: Literal["block", "wheel", "cart", "incline_surface", "wall", "ground", "spring", "equilibrium_marker"]
    shape: VizShapeModel
    body_type: Literal["kinematic", "fixed"]
    initial_position: VizVec2
    initial_angle: FiniteFloat = 0.0
    # True when the drawn size is a render-scale choice, not a stated quantity.
    schematic_size: bool = False


class VizMotionSegmentModel(_SceneModel):
    """Closed-form playback segment.

    ``uniform_acceleration``: x(t) = p0 + v0*Δt + 0.5*a*Δt² (Δt = t - t_start).
    ``oscillation``: x(t) = origin + axis * amplitude * cos(omega*Δt + phase).
    ``rest``: body stays at position0.
    Angular playback is optional and used for rolling display.
    """

    id: str = Field(min_length=1)
    body_id: str = Field(min_length=1)
    kind: Literal["rest", "uniform_acceleration", "oscillation"]
    t_start: FiniteFloat = Field(ge=0)
    t_end: FiniteFloat = Field(gt=0)
    position0: VizVec2 | None = None
    velocity0: VizVec2 | None = None
    acceleration: VizVec2 | None = None
    origin: VizVec2 | None = None
    axis: VizVec2 | None = None
    amplitude: FiniteFloat | None = None
    omega: FiniteFloat | None = None
    phase: FiniteFloat | None = None
    angle0: FiniteFloat | None = None
    angular_velocity0: FiniteFloat | None = None
    angular_acceleration: FiniteFloat | None = None
    # True when displayed rotation uses a render-scale radius, so the angular
    # rate on screen is schematic and must not be read as a physical value.
    angular_schematic: bool = False

    @model_validator(mode="after")
    def _check_kind_params(self) -> "VizMotionSegmentModel":
        if self.t_end <= self.t_start:
            raise ValueError("t_end must be greater than t_start")
        if self.kind in ("rest", "uniform_acceleration"):
            if self.position0 is None:
                raise ValueError(f"{self.kind} segment requires position0")
            if self.kind == "uniform_acceleration" and (
                self.velocity0 is None or self.acceleration is None
            ):
                raise ValueError("uniform_acceleration segment requires velocity0 and acceleration")
        if self.kind == "oscillation":
            missing = [
                name
                for name in ("origin", "axis", "amplitude", "omega")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"oscillation segment requires {', '.join(missing)}")
            if self.amplitude is not None and self.amplitude <= 0:
                raise ValueError("oscillation amplitude must be positive")
            if self.omega is not None and self.omega <= 0:
                raise ValueError("oscillation omega must be positive")
        return self


class VizForceModel(_SceneModel):
    """Force arrow overlay. Lengths are schematic; labels carry the physics."""

    id: str = Field(min_length=1)
    body_id: str = Field(min_length=1)
    kind: Literal["weight", "normal", "friction", "spring_restoring", "impulse"]
    label: str
    symbol: str | None = None
    # Unit direction for fixed arrows; None with behavior="restoring" lets the
    # renderer point the arrow toward equilibrium from the current position.
    direction: VizVec2 | None = None
    behavior: Literal["fixed", "restoring"] = "fixed"
    magnitude_display: str | None = None
    schematic_length: bool = True
    visible_t_start: FiniteFloat | None = None
    visible_t_end: FiniteFloat | None = None

    @model_validator(mode="after")
    def _check_direction(self) -> "VizForceModel":
        if self.behavior == "fixed" and self.direction is None:
            raise ValueError("fixed force overlay requires a direction")
        return self


class VizConstraintModel(_SceneModel):
    kind: str = Field(min_length=1)
    description: str


class VizAxisModel(_SceneModel):
    kind: Literal["positive_x", "positive_y"]
    origin: VizVec2
    direction: VizVec2
    label: str


class VizEventMarkerModel(_SceneModel):
    t: FiniteFloat = Field(ge=0)
    kind: Literal["collision", "segment_boundary"]
    label: str


class VizCameraModel(_SceneModel):
    min_x: FiniteFloat
    min_y: FiniteFloat
    max_x: FiniteFloat
    max_y: FiniteFloat

    @model_validator(mode="after")
    def _check_bounds(self) -> "VizCameraModel":
        if self.max_x <= self.min_x or self.max_y <= self.min_y:
            raise ValueError("camera bounds must have positive extent")
        return self


class VizTimestepModel(_SceneModel):
    # Fixed playback timestep in seconds; frontend must step in multiples.
    fixed_dt: FiniteFloat = Field(gt=0, le=0.1)
    duration: FiniteFloat = Field(gt=0)
    loop: bool = False


class VizAnswerOverlayItemModel(_SceneModel):
    """Post-gate backend answer projected verbatim for on-screen display."""

    label: str
    display: str
    numeric: FiniteFloat | None = None
    unit: str | None = None
    output_key: str | None = None
    source: Literal["backend"] = "backend"


class VizCoordinateFrameModel(_SceneModel):
    axes: list[str] = Field(default_factory=list)
    positive_directions: list[str] = Field(default_factory=list)
    description: str | None = None
    source: str | None = None


class VizAuthorityModel(_SceneModel):
    """Code-enforced authority boundary.

    Literal-typed fields make any other value a validation error, so a scene
    that claims grading rights or answer authority cannot be constructed.
    """

    answer_authority: Literal["backend"] = "backend"
    visualization_authority: Literal["approximate"] = "approximate"
    grading: Literal[False] = False
    answer_selection: Literal[False] = False
    student_answer_overwrite: Literal[False] = False


class VisualizationSceneModel(_SceneModel):
    # Field name matches ExplanationTraceModel's established public "schema"
    # key; the pydantic shadow warning is accepted there and here alike.
    schema: Literal["dynatutor.visualization_scene"] = VISUALIZATION_SCENE_SCHEMA
    version: Literal["1.0"] = VISUALIZATION_SCENE_VERSION
    status: Literal["ready", "unavailable"]
    scene_type: SceneType | None = None
    scene_label: str | None = None
    source_solver: str | None = None
    simulation_mode: Literal["kinematic_playback"] = "kinematic_playback"
    coordinate_frame: VizCoordinateFrameModel | None = None
    bodies: list[VizBodyModel] = Field(default_factory=list)
    motion: list[VizMotionSegmentModel] = Field(default_factory=list)
    forces: list[VizForceModel] = Field(default_factory=list)
    constraints: list[VizConstraintModel] = Field(default_factory=list)
    axes: list[VizAxisModel] = Field(default_factory=list)
    events: list[VizEventMarkerModel] = Field(default_factory=list)
    camera: VizCameraModel | None = None
    timestep: VizTimestepModel | None = None
    answer_overlay: list[VizAnswerOverlayItemModel] = Field(default_factory=list)
    scene_description: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Names + reasons for values that exist only for rendering (amplitude,
    # render radius, spacing).  UI must present them as visualization-only.
    schematic_notes: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None
    authority: VizAuthorityModel = Field(default_factory=VizAuthorityModel)

    @model_validator(mode="after")
    def _check_scene(self) -> "VisualizationSceneModel":
        if self.status == "ready":
            if self.scene_type is None:
                raise ValueError("ready scene requires scene_type")
            if not self.bodies:
                raise ValueError("ready scene requires at least one body")
            if not self.motion:
                raise ValueError("ready scene requires at least one motion segment")
            if self.camera is None or self.timestep is None:
                raise ValueError("ready scene requires camera bounds and a fixed timestep")
            if not self.answer_overlay:
                raise ValueError("ready scene requires a backend answer overlay")
        else:
            if not self.fallback_reason:
                raise ValueError("unavailable scene requires fallback_reason")
            if self.bodies or self.motion:
                raise ValueError("unavailable scene must not carry playback material")

        body_ids = {body.id for body in self.bodies}
        if len(body_ids) != len(self.bodies):
            raise ValueError("body ids must be unique")
        for segment in self.motion:
            if segment.body_id not in body_ids:
                raise ValueError(f"motion segment {segment.id} references unknown body {segment.body_id}")
            if self.timestep is not None and segment.t_start >= self.timestep.duration:
                raise ValueError(f"motion segment {segment.id} starts after scene duration")
        for force in self.forces:
            if force.body_id not in body_ids:
                raise ValueError(f"force {force.id} references unknown body {force.body_id}")

        seen_segments: dict[str, list[tuple[float, float]]] = {}
        for segment in self.motion:
            spans = seen_segments.setdefault(segment.body_id, [])
            for t0, t1 in spans:
                if segment.t_start < t1 and t0 < segment.t_end:
                    raise ValueError(f"overlapping motion segments for body {segment.body_id}")
            spans.append((segment.t_start, segment.t_end))
        return self

    def public_dump(self) -> dict[str, Any]:
        return self.model_dump()
