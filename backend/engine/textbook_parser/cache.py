from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from typing import Any

from engine.extraction.normalizer import normalize
from engine.textbook_parser.contracts import SCHEMA_VERSION, TextbookProblemParseV1
from engine.textbook_parser.assumption_policy import ASSUMPTION_POLICY_VERSION
from engine.textbook_parser.bindings import BINDING_POLICY_VERSION
from engine.textbook_parser.capabilities import CAPABILITY_POLICY_VERSION
from engine.textbook_parser.canonical_projection import PROJECTION_VERSION
from engine.textbook_parser.confidence import DECISION_POLICY_VERSION
from engine.textbook_parser.corrections import CORRECTION_POLICY_VERSION
from engine.textbook_parser.ontology import ONTOLOGY_VERSION
from engine.textbook_parser.prompt import PROMPT_VERSION, load_prompt
from engine.textbook_parser.telemetry import UsageSummary
from engine.textbook_parser.validation import VALIDATOR_POLICY_VERSION
from engine.textbook_parser.temporal_bindings import TEMPORAL_BINDING_POLICY_VERSION


CACHE_FORMAT_VERSION = "textbook-cache-v3"


@dataclass(frozen=True)
class CacheEntry:
    parse: TextbookProblemParseV1
    validation_summary: dict[str, Any]
    model: str
    usage: UsageSummary
    created_at: float


def build_cache_key(problem_text: str, model: str) -> str:
    prompt_content_hash = hashlib.sha256(load_prompt().encode("utf-8")).hexdigest()
    parts = (
        normalize(problem_text),
        model,
        PROMPT_VERSION,
        prompt_content_hash,
        SCHEMA_VERSION,
        ONTOLOGY_VERSION,
        VALIDATOR_POLICY_VERSION,
        ASSUMPTION_POLICY_VERSION,
        BINDING_POLICY_VERSION,
        CAPABILITY_POLICY_VERSION,
        PROJECTION_VERSION,
        DECISION_POLICY_VERSION,
        CORRECTION_POLICY_VERSION,
        TEMPORAL_BINDING_POLICY_VERSION,
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


class ParserCache:
    """Bounded L1 LRU plus bounded/TTL SQLite L2.

    The default SQLite file is in the host temporary directory. On Render this is
    intentionally ephemeral and is only a latency/cost cache, never durable state.
    """

    def __init__(
        self,
        *,
        path: str | None = None,
        ttl_seconds: int = 604800,
        l1_entries: int = 256,
        l2_entries: int = 5000,
    ) -> None:
        self.path = Path(path or (Path(tempfile.gettempdir()) / "dynatutor_textbook_parser.sqlite3"))
        self.ttl_seconds = ttl_seconds
        self.l1_entries = l1_entries
        self.l2_entries = l2_entries
        self._l1: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=2.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=2000")
        if not self._initialized:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS textbook_parse_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.commit()
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            self._initialized = True
        return connection

    def get(self, key: str) -> CacheEntry | None:
        now = time.time()
        with self._lock:
            in_memory = self._l1.get(key)
            if in_memory is not None:
                if now - in_memory.created_at <= self.ttl_seconds:
                    self._l1.move_to_end(key)
                    return in_memory
                self._l1.pop(key, None)
            try:
                with self._connect() as connection:
                    row = connection.execute(
                        "SELECT payload_json, created_at FROM textbook_parse_cache WHERE cache_key = ?",
                        (key,),
                    ).fetchone()
                    if row is None:
                        return None
                    if now - float(row[1]) > self.ttl_seconds:
                        connection.execute("DELETE FROM textbook_parse_cache WHERE cache_key = ?", (key,))
                        return None
                    payload = json.loads(row[0])
                    if payload.get("cache_format_version") != CACHE_FORMAT_VERSION:
                        connection.execute("DELETE FROM textbook_parse_cache WHERE cache_key = ?", (key,))
                        return None
                    entry = CacheEntry(
                        parse=TextbookProblemParseV1.model_validate(payload["parse"]),
                        validation_summary=dict(payload["validation_summary"]),
                        model=str(payload["model"]),
                        usage=UsageSummary(**payload["usage"]),
                        created_at=float(row[1]),
                    )
            except (OSError, sqlite3.Error, json.JSONDecodeError, KeyError, TypeError, ValueError):
                try:
                    with self._connect() as connection:
                        connection.execute("DELETE FROM textbook_parse_cache WHERE cache_key = ?", (key,))
                except (OSError, sqlite3.Error):
                    pass
                return None
            self._put_l1(key, entry)
            return entry

    def put(self, key: str, entry: CacheEntry) -> None:
        payload = {
            "cache_format_version": CACHE_FORMAT_VERSION,
            "parse": entry.parse.model_dump(mode="json"),
            "validation_summary": entry.validation_summary,
            "model": entry.model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "ontology_version": ONTOLOGY_VERSION,
            "validator_policy_version": VALIDATOR_POLICY_VERSION,
            "assumption_policy_version": ASSUMPTION_POLICY_VERSION,
            "binding_policy_version": BINDING_POLICY_VERSION,
            "capability_policy_version": CAPABILITY_POLICY_VERSION,
            "projection_version": PROJECTION_VERSION,
            "decision_policy_version": DECISION_POLICY_VERSION,
            "correction_policy_version": CORRECTION_POLICY_VERSION,
            "temporal_binding_policy_version": TEMPORAL_BINDING_POLICY_VERSION,
            "prompt_content_hash": hashlib.sha256(load_prompt().encode("utf-8")).hexdigest(),
            "usage": entry.usage.to_dict(),
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._put_l1(key, entry)
            try:
                with self._connect() as connection:
                    connection.execute(
                        "INSERT OR REPLACE INTO textbook_parse_cache(cache_key, payload_json, created_at) VALUES (?, ?, ?)",
                        (key, encoded, entry.created_at),
                    )
                    connection.execute(
                        "DELETE FROM textbook_parse_cache WHERE created_at < ?",
                        (time.time() - self.ttl_seconds,),
                    )
                    connection.execute(
                        """
                        DELETE FROM textbook_parse_cache
                        WHERE cache_key IN (
                            SELECT cache_key FROM textbook_parse_cache
                            ORDER BY created_at DESC LIMIT -1 OFFSET ?
                        )
                        """,
                        (self.l2_entries,),
                    )
            except (OSError, sqlite3.Error):
                # L2 is a fail-open optimization; L1 remains usable.
                return

    def _put_l1(self, key: str, entry: CacheEntry) -> None:
        self._l1[key] = entry
        self._l1.move_to_end(key)
        while len(self._l1) > self.l1_entries:
            self._l1.popitem(last=False)


__all__ = ["CACHE_FORMAT_VERSION", "CacheEntry", "ParserCache", "build_cache_key"]
