# OSS usage in DynaTutor

| Project | Usage Type | License | Used As | Copied Code? | Modified? | Location |
|---|---|---|---|---|---|---|
| SymPy | dependency | BSD | symbolic equation solving | no | no | backend/requirements.txt |
| Pint | dependency | BSD/BSD-3-style | unit engine | no | no | backend/requirements.txt, backend/engine/physics_core/units.py wrapper |
| NumPy | dependency | BSD | numerical utilities/future validation | no | no | backend/requirements.txt |
| SciPy | dependency | BSD | future numerical solving/validation | no | no | backend/requirements.txt |
| PyDy | dependency/adapter | BSD-3 | multibody dynamics adapter scaffold | no copied examples in Phase 13 | no | backend/requirements.txt, backend/engine/adapters |
| Project Chrono | dev validation | BSD-3 | offline simulation validation | no | no | backend/tools/chrono_validation |
| FOSSEE Engineering Mechanics Dynamics | educational examples/tests | verify selected license before porting | derived tests, solver reference | no original code copied in Phase 13 | derived only | third_party, backend/tests/benchmarks |
| OpenStax University Physics | educational tests | CC family; verify exact book/resource | derived benchmarks | no direct API use | derived only | backend/tests/benchmarks/openstax_derived |
| MIT OCW | educational tests | Creative Commons family by course | benchmark design | no direct API use | derived only | backend/tests/benchmarks/mit_ocw_derived |
| MechAgents | architecture reference | Apache-2.0 | LLM/agent guardrail ideas | no | no | docs only |
