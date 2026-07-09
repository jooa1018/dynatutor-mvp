from tools.run_release_candidate_audit import audit


def test_phase23_release_candidate_audit_without_nested_pytest():
    report = audit(include_pytest=False)
    assert report["release_candidate"] == "phase23"
    assert report["overall_passed"] is True
    assert report["checks"]["benchmark_passed"] is True
    assert report["checks"]["benchmark_total_at_least_450"] is True
    assert report["checks"]["phase21_validation_passed"] is True
    assert report["checks"]["llm_guardrail_passed"] is True
    assert report["benchmark_audit"]["total_count"] >= 450
    assert report["phase21_validation_summary"]["failed"] == 0
    assert report["llm_guardrail_audit"]["changed_answer_rejected"] is True
    assert report["artifact_inventory"]["phase_doc_count"] >= 20


def test_phase23_release_candidate_known_limitations_are_explicit():
    report = audit(include_pytest=False)
    limitations = "\n".join(report["known_limitations"])
    assert "Frontend build" in limitations
    assert "PyChrono" in limitations
    assert "Benchmarks" in limitations
    assert "LLM guardrail" in limitations
