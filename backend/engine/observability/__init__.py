"""Privacy-safe, opt-in observability for the solve pipeline.

The product solve path does not import this package unless a caller explicitly
constructs and supplies a collector.
"""

from .contracts import (
    BENCHMARK_VERSION,
    CANONICAL_SCHEMA_VERSION,
    CROSS_ENGINE_REPORT_SCHEMA_VERSION,
    CROSS_ENGINE_REPORT_VERSION,
    LEGACY_MODEL_SCHEMA_VERSION,
    PERFORMANCE_SCHEMA_VERSION,
    PERFORMANCE_VERSION,
    SOLVER_PIPELINE_VERSION,
    STATUS_VALUES,
    TRACE_SCHEMA_VERSION,
    TRACE_VERSION,
    TYPED_MODEL_SCHEMA_VERSION,
    StableSnapshot,
)
from .trace import SolveTraceCollector, new_live_collector

__all__ = [
    "BENCHMARK_VERSION",
    "CANONICAL_SCHEMA_VERSION",
    "CROSS_ENGINE_REPORT_SCHEMA_VERSION",
    "CROSS_ENGINE_REPORT_VERSION",
    "LEGACY_MODEL_SCHEMA_VERSION",
    "PERFORMANCE_SCHEMA_VERSION",
    "PERFORMANCE_VERSION",
    "SOLVER_PIPELINE_VERSION",
    "STATUS_VALUES",
    "TRACE_SCHEMA_VERSION",
    "TRACE_VERSION",
    "TYPED_MODEL_SCHEMA_VERSION",
    "SolveTraceCollector",
    "StableSnapshot",
    "new_live_collector",
]
