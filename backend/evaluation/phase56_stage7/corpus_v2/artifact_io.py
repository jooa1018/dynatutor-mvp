"""Byte-exact atomic writes for Stage 7 evidence artifacts.

``Path.write_text`` uses the platform text newline policy.  Hashing a Python
string before that write therefore does not prove the bytes a Windows reader
will open: each ``\n`` may have become ``\r\n``.  Evidence file hashes are
claims about files, so this module encodes once, writes those exact bytes, and
hashes the bytes read back from the committed destination.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


class ArtifactWriteRefused(OSError):
    """An evidence artifact could not be committed byte-exactly."""


def write_utf8_atomic(path: Path, body: str) -> str:
    """Atomically replace ``path`` with exact UTF-8 bytes and return its SHA."""

    path.parent.mkdir(parents=True, exist_ok=True)
    expected = body.encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".partial",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())

        if temporary.read_bytes() != expected:
            raise ArtifactWriteRefused("artifact_staged_bytes_mismatch")
        os.replace(temporary, path)
        temporary = None
        committed = path.read_bytes()
        if committed != expected:
            raise ArtifactWriteRefused("artifact_committed_bytes_mismatch")
        return hashlib.sha256(committed).hexdigest()
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


__all__ = ["ArtifactWriteRefused", "write_utf8_atomic"]
