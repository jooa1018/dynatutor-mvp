from engine.mechanics.multimodal_authority_audit import audit_modeling_payload


def test_authority_audit_rejects_execution_and_answer_fields_recursively() -> None:
    result = audit_modeling_payload(
        {
            "draft": {
                "objects": [],
                "nested": {"selected_solver": "solve_it", "final_answer": "42"},
            }
        }
    )
    assert not result.passed
    assert {finding.field for finding in result.findings} == {"selected_solver", "final_answer"}


def test_authority_audit_allows_source_grounded_draft_fields() -> None:
    result = audit_modeling_payload(
        {
            "draft": {
                "objects": [{"object_id": "block"}],
                "quantities": [{"quantity_id": "mass", "raw_value": "2", "raw_unit": "kg"}],
            },
            "figure_observations": [{"observation_id": "label_mass"}],
        }
    )
    assert result.passed
    assert result.findings == ()
