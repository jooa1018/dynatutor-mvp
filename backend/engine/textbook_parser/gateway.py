from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any

from engine.extraction.extractor import extract_problem
from engine.models import CanonicalProblem
from engine.textbook_parser.canonical_projection import project_canonical
from engine.textbook_parser.config import ParserMode, TextbookParserConfig
from engine.textbook_parser.corrections import apply_parse_corrections
from engine.textbook_parser.orchestrator import ParseOutcome, parse_textbook_problem


@dataclass(frozen=True)
class ParserGatewayResult:
    canonical: CanonicalProblem
    outcome: ParseOutcome | None
    blocked: bool
    approval_fingerprint: str | None = None
    mode: ParserMode = ParserMode.off
    correction_applied: bool = False

    @property
    def summary(self) -> dict[str, Any] | None:
        if self.outcome is None:
            return None
        summary = self.outcome.public_summary()
        summary["approval_fingerprint"] = self.approval_fingerprint
        summary["requires_approval"] = self.blocked and self.outcome.validated is not None and self.outcome.validated.accepted
        summary["parser_mode"] = self.mode.value
        summary["correction_applied"] = self.correction_applied
        return summary


def approval_fingerprint(outcome: ParseOutcome) -> str | None:
    if outcome.validated is None or outcome.validated.selected_candidate_id is None:
        return None
    payload = {
        "problem_hash": outcome.problem_hash,
        "candidate": outcome.validated.selected_candidate_id,
        "parse": outcome.validated.parse.model_dump(mode="json"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _blocked_canonical(problem_text: str, outcome: ParseOutcome) -> CanonicalProblem:
    """Return an interpretation-neutral value that cannot be routed or solved."""

    return CanonicalProblem(
        system_type="unknown",
        raw_text=problem_text,
        knowns={},
        unknowns=[],
        requested_outputs=[],
        missing_info=["authoritative textbook interpretation is not approved"],
        textbook_parse={
            "source": "gpt_structured_outputs",
            "authoritative": False,
            "blocked": True,
            "public_summary": outcome.public_summary(),
        },
    )


def parse_problem_gateway(
    problem_text: str,
    *,
    config: TextbookParserConfig | None = None,
    approved_fingerprint: str | None = None,
    client=None,
    cache=None,
    legacy_extractor=extract_problem,
    parse_correction: dict[str, Any] | None = None,
) -> ParserGatewayResult:
    config = config or TextbookParserConfig.from_env()
    if config.mode == ParserMode.off:
        return ParserGatewayResult(
            legacy_extractor(problem_text), None, False, mode=config.mode
        )

    outcome = parse_textbook_problem(
        problem_text, config=config, client=client, cache=cache
    )
    if parse_correction is not None and outcome.validated is not None:
        corrected = apply_parse_corrections(
            outcome.validated.parse, parse_correction
        )
        from engine.textbook_parser.validation import validate_parse

        corrected_validation = validate_parse(problem_text, corrected)
        outcome = replace(
            outcome,
            status=corrected_validation.status,
            validated=corrected_validation,
            cache_hit=False,
        )
    fingerprint = approval_fingerprint(outcome)
    if config.mode == ParserMode.shadow:
        legacy = legacy_extractor(problem_text)
        legacy.textbook_parse = {
            "source": "gpt_structured_outputs",
            "authoritative": False,
            "public_summary": outcome.public_summary(),
        }
        return ParserGatewayResult(
            legacy, outcome, False, fingerprint, config.mode, parse_correction is not None
        )
    if outcome.validated is None or not outcome.validated.accepted:
        return ParserGatewayResult(
            _blocked_canonical(problem_text, outcome),
            outcome,
            True,
            fingerprint,
            config.mode,
            parse_correction is not None,
        )
    if config.mode == ParserMode.confirm and approved_fingerprint != fingerprint:
        return ParserGatewayResult(
            _blocked_canonical(problem_text, outcome),
            outcome,
            True,
            fingerprint,
            config.mode,
            parse_correction is not None,
        )
    canonical = project_canonical(problem_text, outcome.validated)
    result = ParserGatewayResult(
        canonical,
        outcome,
        False,
        fingerprint,
        config.mode,
        parse_correction is not None,
    )
    canonical.textbook_parse["public_summary"] = result.summary
    return result


__all__ = [
    "ParserGatewayResult",
    "approval_fingerprint",
    "parse_problem_gateway",
]
