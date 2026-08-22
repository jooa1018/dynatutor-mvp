from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from evaluation.phase56_stage7.corpus_v2 import artifact_io
from evaluation.phase56_stage7.corpus_v2.artifact_io import write_utf8_atomic
from evaluation.phase56_stage7.corpus_v2.publication import (
    _read_back_file_sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY_ROOT / "backend" / "tools"


def test_atomic_writer_hashes_the_exact_committed_utf8_bytes(tmp_path) -> None:
    output = tmp_path / "evidence.json"
    body = '{"claim":"한글 evidence"}\n{"line":2}\n'

    reported = write_utf8_atomic(output, body)

    assert output.read_bytes() == body.encode("utf-8")
    assert reported == hashlib.sha256(output.read_bytes()).hexdigest()
    assert not list(tmp_path.glob("*.partial"))


def test_failed_replace_preserves_the_previous_artifact(tmp_path, monkeypatch) -> None:
    output = tmp_path / "evidence.json"
    output.write_bytes(b"previous-authority\n")

    def refuse_replace(source, destination):
        raise OSError("controlled replace failure")

    monkeypatch.setattr(artifact_io.os, "replace", refuse_replace)

    with pytest.raises(OSError, match="controlled replace failure"):
        write_utf8_atomic(output, "new candidate\n")

    assert output.read_bytes() == b"previous-authority\n"
    assert not list(tmp_path.glob("*.partial"))


def test_publication_readback_hashes_raw_bytes_not_normalized_text(tmp_path) -> None:
    output = tmp_path / "artifact.json"
    output.write_bytes(b"one\r\ntwo\r\n")

    assert _read_back_file_sha256(output) == hashlib.sha256(output.read_bytes()).hexdigest()
    assert _read_back_file_sha256(output) != hashlib.sha256(
        output.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize(
    "tool_name",
    [
        "run_phase56_stage7_v2_shadow_verify_prepare.py",
        "run_phase56_stage7_v2_shadow_runtime.py",
        "run_phase56_stage7_v2_shadow_score.py",
    ],
)
def test_vrg_tools_share_the_byte_exact_writer(tool_name: str) -> None:
    source = (TOOLS / tool_name).read_text(encoding="utf-8")

    assert "write_utf8_atomic" in source
    assert "write_text(body" not in source
    assert "hashlib.sha256(body.encode" not in source
