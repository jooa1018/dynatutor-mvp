from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        nodeid = item.nodeid.lower()
        name = item.name.lower()

        if "negative" in nodeid or "unsupported" in nodeid:
            item.add_marker(pytest.mark.negative)

        if (
            "benchmark" in nodeid
            or "blind_textbook" in nodeid
            or "korean_quality" in nodeid
            or "test_phase13_benchmark" in nodeid
            or "test_phase20_benchmark_audit" in nodeid
        ):
            item.add_marker(pytest.mark.benchmark)
            item.add_marker(pytest.mark.slow)

        is_benchmark_item = any(item.iter_markers(name="benchmark"))

        if (
            ("audit" in nodeid and not is_benchmark_item)
            or "release_candidate" in nodeid
            or "test_phase21_chrono" in nodeid
            or "test_phase22_llm_guardrail" in nodeid
            or "test_phase23_release" in nodeid
            or "test_phase24_final" in nodeid
        ):
            item.add_marker(pytest.mark.audit)

        if (
            "frontend" in nodeid
            or "dependency_locks" in nodeid
            or "test_phase24_final" in nodeid
        ):
            item.add_marker(pytest.mark.frontend)

        if not any(item.iter_markers(name="benchmark")) and not any(item.iter_markers(name="audit")) and not any(item.iter_markers(name="frontend")):
            if "regression" in nodeid or "phase" in nodeid or "mvp" in nodeid:
                item.add_marker(pytest.mark.regression)
            else:
                item.add_marker(pytest.mark.unit)
