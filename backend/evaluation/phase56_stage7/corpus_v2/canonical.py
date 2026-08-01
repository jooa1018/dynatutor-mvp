"""One canonicalization, shared by every artifact that hashes itself.

Digests only bind what they are computed over, so two artifacts that hash "the
same content" through two different serializers do not agree about anything.
The scorecard used ``repr(model_dump())`` — a Python-implementation-dependent
string in which ``{'a': 1}`` and ``{'a': True}`` are distinguishable but a
change of dict insertion order is too — while the snapshot used sorted compact
JSON.  A verifier rebuilding one of them had to reproduce the exact serializer
rather than the content, and any drift between the two spellings turned into a
mismatch nobody could attribute.

So there is one spelling here and everything imports it:

* ``ensure_ascii=False`` — the corpus is Korean, and escaping it would make the
  bytes depend on the writer rather than on the content.
* ``allow_nan=False`` — ``NaN`` is not JSON, and a digest over something no
  reader can parse back is not a digest anyone can check.
* ``sort_keys=True`` — key order is not content.
* ``separators=(",", ":")`` — whitespace is not content either.
* UTF-8, always.

A *canonical digest* is over content and a *file SHA-256* is over the bytes
somebody actually wrote.  They are different numbers about different things and
this module never conflates them: `canonical_digest` takes a value, and
callers hash file bytes themselves.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """The one byte sequence this evaluation canonicalizes a value into."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    """SHA-256 over `canonical_json_bytes`.  Never over a `repr`."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(body: str) -> str:
    """SHA-256 over the exact UTF-8 bytes of a written artifact.

    Kept beside the canonical digest deliberately, so the two names appear
    together and a caller has to choose which question it is asking: "is this
    the same content" or "is this the same file".
    """

    return hashlib.sha256(body.encode("utf-8")).hexdigest()


__all__ = ["canonical_digest", "canonical_json_bytes", "file_sha256"]
