from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from evaluation.phase56_stage7.contracts import (
    STAGE7_ARTIFACT_SCHEMA,
    STAGE7_ARTIFACT_VERSION,
    FrozenStrictModel,
    Sha256,
    Stage7FailureKind,
    Stage7HardSafetySignal,
    Stage7Metric,
)
from pydantic import Field
from typing import Annotated, Literal
from pydantic import StringConstraints


_FORBIDDEN_NORMALIZED = frozenset(
    {
        "problemtext",
        "goldgraph",
        "expectedanswer",
        "answertolerance",
        "referenceexpression",
        "rawprovideroutput",
        "rawimage",
        "imagebase64",
        "privatemanifest",
        "promptcontent",
        "secret",
        "apikey",
    }
)
_FORBIDDEN_VALUE_MARKERS = (
    "sk-",
    "private_heldout",
    "do_not_share_with_codex",
    "data:image/",
)


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def assert_privacy_safe_artifact(value: Any) -> None:
    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                if not isinstance(key, str):
                    raise ValueError("artifact keys must be strings")
                if _normalized_key(key) in _FORBIDDEN_NORMALIZED:
                    raise ValueError(f"artifact contains forbidden field: {key}")
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
        elif isinstance(node, str):
            lowered = node.casefold()
            if any(marker in lowered for marker in _FORBIDDEN_VALUE_MARKERS):
                raise ValueError("artifact contains forbidden sensitive marker")

    walk(value)


class Stage7AggregateArtifactV1(FrozenStrictModel):
    schema: Literal["dynatutor.phase56_stage7.report"] = STAGE7_ARTIFACT_SCHEMA
    version: Literal["1.0"] = STAGE7_ARTIFACT_VERSION
    evaluator_version: Literal["phase56-stage7-evaluator-v1"] = (
        "phase56-stage7-evaluator-v1"
    )
    exact_head_sha: Sha256
    corpus_zip_sha256: Sha256
    public_split_sha256: dict[str, Sha256]
    public_split_counts: dict[str, int]
    terminal_confusion: dict[str, int]
    metric_aggregates: dict[Stage7Metric, float]
    hard_safety_counts: dict[Stage7HardSafetySignal, int]
    failure_counts: dict[Stage7FailureKind, int]
    privacy_safe_case_hashes: tuple[Sha256, ...] = Field(default=(), max_length=1000)
    bounded_mismatch_signatures: tuple[
        Annotated[str, StringConstraints(max_length=240)], ...
    ] = Field(default=(), max_length=1000)
    actual_model_quality: Literal["NOT_RUN / N/A"] = "NOT_RUN / N/A"
    external_model_calls: Literal[0] = 0
    private_heldout_accesses: Literal[0] = 0

    def privacy_safe_json_bytes(self) -> bytes:
        payload = self.model_dump(mode="json")
        assert_privacy_safe_artifact(payload)
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


def privacy_safe_case_hash(*, case_id: str, problem_sha256: str) -> str:
    # The salt is evaluator-version public metadata, not a secret.  The resulting
    # hash is correlation-only and cannot enter the runtime input/cache/prompt.
    material = f"phase56-stage7-evaluator-v1\0{case_id}\0{problem_sha256}".encode(
        "utf-8"
    )
    return hashlib.sha256(material).hexdigest()
