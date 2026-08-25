"""The controlled v1 source vocabulary that states a query objective.

B22's first published classification said `EngineCarrier.query_objective` has
no source field anywhere in the v1 public corpus contract.  That was wrong,
and an independent audit caught it: the B12 repair already maps the v1 source
field `query.output_key = minimum_speed` onto the Draft's typed
`Query.objective = minimum`, and the official v1 projection has applied that
mapping ever since.  A query objective is therefore not a carrier v1 cannot
express — it is a carrier v1 expresses *partially*, through a controlled
output-key vocabulary, and this module is the one place that vocabulary is
written down.

Both readers bind to this table so they cannot drift apart:

* the official v1 projection (`lane_b_draft_projection`) consumes it to stamp
  the typed objective onto the Draft query, and
* the semantic-preservation audit (`semantic_preservation`) consumes it to
  classify `query.output_key` as the source carrier of `query_objective`.

The rules are the B12 rules, restated:

* Lookup is exact membership in this closed table.  No substring search, no
  "contains `minimum`" heuristic, no problem-text reading, no family or case
  routing, and no expected-answer participation — an output key outside the
  table carries no objective, however suggestive its spelling.
* `minimum_speed -> minimum` is the whole table today.  The v1 public
  contract's closed output-key vocabulary contains no key whose meaning is an
  admissible-set *maximum*: `max_height` names the exact apex height of a
  trajectory (an exact-value readout the kinematics determine), not a
  boundary of an admissible set, so mapping it would put words in the
  source's mouth.  If a genuinely extremal maximum key ever enters the corpus
  contract, it is added here explicitly or it does not exist.
* An ordinary value question (`final_velocity`, `acceleration`, ...) carries
  no objective, and an absent objective is the exact-value reading — never a
  defaulted `minimum`.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


QUERY_OBJECTIVE_SOURCES_VERSION = "phase56-stage7-query-objective-sources-v1"

# The v1 source field whose controlled vocabulary can state an objective.
QUERY_OBJECTIVE_SOURCE_FIELD = "query.output_key"

# corpus query output key -> engine `QueryObjective` value.  Closed and exact:
# consumers look keys up by equality and never by substring or pattern.
QUERY_OBJECTIVE_OUTPUT_KEYS: Mapping[str, str] = MappingProxyType(
    {
        "minimum_speed": "minimum",
    }
)


__all__ = [
    "QUERY_OBJECTIVE_OUTPUT_KEYS",
    "QUERY_OBJECTIVE_SOURCE_FIELD",
    "QUERY_OBJECTIVE_SOURCES_VERSION",
]
