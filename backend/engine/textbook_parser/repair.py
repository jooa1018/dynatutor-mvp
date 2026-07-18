from __future__ import annotations

from engine.textbook_parser.errors import RepairIssueV1


REPAIR_POLICY_VERSION = "field-repair-policy-v1"


def format_repair_request(
    problem_text: str,
    issues: tuple[RepairIssueV1, ...],
) -> list[dict[str, str]]:
    lines = [
        "Re-parse the original problem and return one complete fresh TextbookProblemParseWireV2.",
        "",
        "Correct these structural failures:",
    ]
    for index, issue in enumerate(issues, start=1):
        lines.append(f"{index}. path: {issue.path or '<root>'}")
        lines.append(f"   code: {issue.code}")
        if issue.error_type:
            lines.append(f"   error_type: {issue.error_type}")
        if issue.referenced_id:
            lines.append(f"   referenced_id: {issue.referenced_id}")
        if issue.reason_code:
            lines.append(f"   reason: {issue.reason_code}")
        for key, value in sorted((issue.allowed_metadata or {}).items()):
            lines.append(f"   {key}: {value}")
    lines.extend(
        [
            "",
            "Do not calculate an answer.",
            "Do not copy these diagnostics into output.",
            "Return the entire structure, not a partial patch.",
            "",
            "ORIGINAL PROBLEM:",
            problem_text,
        ]
    )
    return [{"role": "user", "content": "\n".join(lines)}]


__all__ = ["REPAIR_POLICY_VERSION", "format_repair_request"]
