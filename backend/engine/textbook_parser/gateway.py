from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from engine.extraction.extractor import extract_problem
from engine.models import CanonicalProblem
from engine.textbook_parser.canonical_projection import project_canonical
from engine.textbook_parser.config import ParserMode, TextbookParserConfig
from engine.textbook_parser.orchestrator import ParseOutcome, parse_textbook_problem


@dataclass(frozen=True)
class ParserGatewayResult:
    canonical: CanonicalProblem
    outcome: ParseOutcome | None
    blocked: bool
    approval_fingerprint: str | None = None

    @property
    def summary(self) -> dict[str, Any] | None:
        if self.outcome is None:
            return None
        summary = self.outcome.public_summary()
        summary["approval_fingerprint"] = self.approval_fingerprint
        summary["requires_approval"] = self.blocked and self.outcome.validated is not None and self.outcome.validated.accepted
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


def parse_problem_gateway(
    problem_text: str,
    *,
    config: TextbookParserConfig | None = None,
    approved_fingerprint: str | None = None,
    client=None,
    cache=None,
) -> ParserGatewayResult:
    config = config or TextbookParserConfig.from_env()
    legacy = extract_problem(problem_text)
    if config.mode == ParserMode.off:
        return ParserGatewayResult(legacy, None, False)

    outcome = parse_textbook_problem(
        problem_text, config=config, client=client, cache=cache
    )
    fingerprint = approval_fingerprint(outcome)
    if config.mode == ParserMode.shadow:
        legacy.textbook_parse = {
            "source": "gpt_structured_outputs",
            "authoritative": False,
            "public_summary": outcome.public_summary(),
        }
        return ParserGatewayResult(legacy, outcome, False, fingerprint)
    if outcome.validated is None or not outcome.validated.accepted:
        legacy.textbook_parse = {
            "source": "gpt_structured_outputs",
            "authoritative": False,
            "public_summary": outcome.public_summary(),
        }
        return ParserGatewayResult(legacy, outcome, True, fingerprint)
    if config.mode == ParserMode.confirm and approved_fingerprint != fingerprint:
        legacy.textbook_parse = {
            "source": "gpt_structured_outputs",
            "authoritative": False,
            "public_summary": outcome.public_summary(),
        }
        return ParserGatewayResult(legacy, outcome, True, fingerprint)
    canonical = project_canonical(problem_text, outcome.validated)
    canonical.textbook_parse["public_summary"] = outcome.public_summary()
    return ParserGatewayResult(
        canonical,
        outcome,
        False,
        fingerprint,
    )


__all__ = [
    "ParserGatewayResult",
    "approval_fingerprint",
    "parse_problem_gateway",
]
