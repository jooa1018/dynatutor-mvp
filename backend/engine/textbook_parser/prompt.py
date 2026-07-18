from __future__ import annotations

from pathlib import Path


PROMPT_VERSION = "textbook-parser-prompt-v1"
PROMPT_PATH = Path(__file__).with_name("prompts") / "textbook_parser_v1.txt"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


__all__ = ["PROMPT_PATH", "PROMPT_VERSION", "load_prompt"]
