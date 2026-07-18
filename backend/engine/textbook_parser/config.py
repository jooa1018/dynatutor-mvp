from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os


DEFAULT_MODEL = "gpt-5.4-mini-2026-03-17"


class ParserMode(str, Enum):
    off = "off"
    shadow = "shadow"
    confirm = "confirm"
    auto = "auto"
    required = "required"


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TextbookParserConfig:
    enabled: bool
    mode: ParserMode
    model: str
    reasoning_effort: str
    max_retries: int
    timeout_seconds: float
    store: bool
    max_output_tokens: int
    max_problem_chars: int
    max_inflight: int
    cache_path: str | None
    cache_ttl_seconds: int
    cache_l1_entries: int
    cache_l2_entries: int

    @classmethod
    def from_env(cls) -> "TextbookParserConfig":
        enabled = _bool("TEXTBOOK_PARSER_ENABLED", False)
        try:
            mode = ParserMode(os.getenv("TEXTBOOK_PARSER_MODE", "off").strip().lower())
        except ValueError as exc:
            raise ValueError("TEXTBOOK_PARSER_MODE must be off, shadow, confirm, auto, or required") from exc
        if not enabled:
            mode = ParserMode.off
        store = _bool("TEXTBOOK_PARSER_STORE", False)
        if store:
            raise ValueError("TEXTBOOK_PARSER_STORE must remain false")
        max_retries = min(max(int(os.getenv("TEXTBOOK_PARSER_MAX_RETRIES", "1")), 0), 1)
        max_output_tokens = min(
            max(int(os.getenv("TEXTBOOK_PARSER_MAX_OUTPUT_TOKENS", "1800")), 256),
            1800,
        )
        return cls(
            enabled=enabled,
            mode=mode,
            model=os.getenv("TEXTBOOK_PARSER_MODEL", DEFAULT_MODEL),
            reasoning_effort=os.getenv("TEXTBOOK_PARSER_REASONING_EFFORT", "low"),
            max_retries=max_retries,
            timeout_seconds=min(max(float(os.getenv("TEXTBOOK_PARSER_TIMEOUT_SECONDS", "20")), 1.0), 20.0),
            store=False,
            max_output_tokens=max_output_tokens,
            max_problem_chars=min(max(int(os.getenv("TEXTBOOK_PARSER_MAX_PROBLEM_CHARS", "12000")), 500), 12000),
            max_inflight=min(max(int(os.getenv("TEXTBOOK_PARSER_MAX_INFLIGHT", "8")), 1), 16),
            cache_path=os.getenv("TEXTBOOK_PARSER_CACHE_PATH") or None,
            cache_ttl_seconds=min(max(int(os.getenv("TEXTBOOK_PARSER_CACHE_TTL_SECONDS", "604800")), 60), 2_592_000),
            cache_l1_entries=min(max(int(os.getenv("TEXTBOOK_PARSER_CACHE_L1_ENTRIES", "256")), 1), 2048),
            cache_l2_entries=min(max(int(os.getenv("TEXTBOOK_PARSER_CACHE_L2_ENTRIES", "5000")), 10), 50_000),
        )


__all__ = ["DEFAULT_MODEL", "ParserMode", "TextbookParserConfig"]
