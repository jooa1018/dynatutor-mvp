# Phase 7 Notes — FBD Diagram Upgrade

Phase 7 improves the visual tutoring layer without changing the core rule:

```text
Solver decides the math.
Verification checks the result.
FBD diagrams teach modeling and direction choices.
```

## Added

- Higher-quality SVG FBD diagrams
- Color-coded force/axis legends embedded inside the SVG
- Force direction labels for gravity, normal force, friction, tension, spring force, and velocity components
- Coordinate axes for incline and polar problems
- Component decomposition labels such as `mg sinθ`, `mg cosθ`, `N sinθ`, `N cosθ`
- Diagram-specific annotation notes returned in the API
- Frontend `FBD 고도화 도식` card with a `도식 읽는 법` section
- Phase 7 regression tests

## New response field

`DiagnosisResponse` now includes:

```json
{
  "fbd_diagram_svg": "<svg ...>",
  "fbd_annotations": [
    "중력 mg는 항상 수직 아래 방향입니다...",
    "수직항력 N은 경사면에 수직입니다..."
  ]
}
```

## Diagram coverage

- Incline block
- Table-hanging pulley
- Vertical circle
- Pure rolling energy
- Spring-mass vibration / spring energy
- Flat curve friction
- Banked curve without friction
- Polar kinematics
- Instant center velocity
- Slot-pin relative motion
- Plane rigid body velocity

## Limitations

The diagrams are still schematic. Arrow lengths are not scaled by actual magnitudes. They are designed to help beginners choose axes, draw the right forces, and avoid common sign/direction mistakes before solving.
