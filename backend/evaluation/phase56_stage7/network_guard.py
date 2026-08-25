from __future__ import annotations

import contextlib
import os
import socket
from dataclasses import dataclass
from typing import Callable, Iterator


class ExternalNetworkBlocked(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OfflineEnvironmentEvidence:
    openai_key_empty: bool
    anthropic_key_empty: bool
    provider_base_urls_absent: bool

    @property
    def passed(self) -> bool:
        return (
            self.openai_key_empty
            and self.anthropic_key_empty
            and self.provider_base_urls_absent
        )


def assert_offline_environment() -> OfflineEnvironmentEvidence:
    openai_key_empty = os.environ.get("OPENAI_API_KEY", "") == ""
    anthropic_key_empty = os.environ.get("ANTHROPIC_API_KEY", "") == ""
    provider_base_urls_absent = all(
        os.environ.get(name, "") == ""
        for name in (
            "OPENAI_BASE_URL",
            "ANTHROPIC_BASE_URL",
            "MECHANICS_MODELER_BASE_URL",
            "MECHANICS_FIGURE_BASE_URL",
        )
    )
    evidence = OfflineEnvironmentEvidence(
        openai_key_empty=openai_key_empty,
        anthropic_key_empty=anthropic_key_empty,
        provider_base_urls_absent=provider_base_urls_absent,
    )
    if not evidence.passed:
        raise ExternalNetworkBlocked(
            "Stage 7 evaluation requires empty model credentials and base URLs"
        )
    return evidence


@contextlib.contextmanager
def block_external_network() -> Iterator[None]:
    """Fail closed on every socket creation during the evaluation phase.

    Dependency installation occurs before this guard.  Local test clients that do
    not create sockets remain usable; any attempted model or external endpoint
    connection raises immediately.
    """

    original_socket = socket.socket
    original_create_connection = socket.create_connection

    def denied_socket(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise ExternalNetworkBlocked("external network disabled for Stage 7")

    def denied_connection(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise ExternalNetworkBlocked("external network disabled for Stage 7")

    socket.socket = denied_socket  # type: ignore[assignment]
    socket.create_connection = denied_connection  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = original_socket  # type: ignore[assignment]
        socket.create_connection = original_create_connection  # type: ignore[assignment]
