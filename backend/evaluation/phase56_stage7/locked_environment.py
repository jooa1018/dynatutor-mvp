"""Reproduce a strict Stage 7 run under the declared dependency lock.

A strict report is evidence about the *engine*.  A report produced against
whatever happened to be installed in the container is evidence about the
container as well, and the two are not separable after the fact: the last
recorded Lane D failure was one test in one unpinned FastAPI, and reading it as
an engine defect or dismissing it as an environment artifact were equally
unfounded until the environment was pinned and the test re-run.

So this module states the environment as a contract.  It parses
``backend/requirements-lock.txt`` into an exact name/version set, compares that
set against what a candidate interpreter actually resolved, and names the exact
environment variables a strict run must have empty.  Everything here is a pure
function over data that a test can supply, so the contract is testable without
building a virtual environment or reaching a network.

Nothing here participates in a runtime decision, and nothing here relaxes a
gate.  A locked run is the *same* strict gate with its inputs stated.
"""

from __future__ import annotations

import re
from typing import Annotated, Iterable, Mapping, Sequence

from pydantic import Field, StringConstraints

from evaluation.phase56_stage7.contracts import FrozenStrictModel


LOCKED_ENVIRONMENT_CONTRACT_VERSION = (
    "phase56-stage7-locked-environment-contract-v1"
)

# The variables `assert_offline_environment` requires empty.  A locked run
# clears exactly these and no others: emptying more would let a strict run
# silently depend on an unstated blank, and emptying fewer would let a host
# credential decide whether the gate is allowed to start.
OFFLINE_REQUIRED_EMPTY_VARIABLES: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "MECHANICS_FIGURE_BASE_URL",
    "MECHANICS_MODELER_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
)

# The distributions whose versions decide whether Lane D's product-API suite is
# measuring the engine or the framework underneath it.  `starlette` is not a
# direct lock entry — it is FastAPI's own dependency — and is recorded anyway,
# because the route-registration behaviour Lane D asserts lives there.
ENVIRONMENT_WITNESS_DISTRIBUTIONS: tuple[str, ...] = (
    "fastapi",
    "httpx",
    "numpy",
    "pint",
    "pydantic",
    "pydantic-core",
    "pytest",
    "scipy",
    "starlette",
    "sympy",
)

_DistributionName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
_VersionText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._+!-]*$",
    ),
]

# ``name[extra,extra]==version``.  The lock file is authored by this repository
# and is deliberately not a full PEP 508 grammar: a requirement this parser
# cannot read is a lock file that must be fixed, not a line to skip.
_REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[(?P<extras>[A-Za-z0-9,._-]*)\])?"
    r"==(?P<version>[A-Za-z0-9][A-Za-z0-9._+!-]*)$"
)


class LockedRequirementParseError(ValueError):
    """A lock line that is neither blank, a comment, nor ``name==version``."""


def canonical_distribution_name(value: str) -> str:
    """PEP 503 canonical form, so ``Pillow`` and ``pillow`` are one name."""

    return re.sub(r"[-_.]+", "-", value.strip()).lower()


class LockedRequirementV1(FrozenStrictModel):
    """One pinned distribution, as the lock file states it."""

    name: _DistributionName
    canonical_name: _DistributionName
    version: _VersionText
    extras: tuple[_DistributionName, ...] = ()


class ResolvedDistributionV1(FrozenStrictModel):
    """One distribution as a candidate interpreter actually resolved it."""

    canonical_name: _DistributionName
    version: _VersionText


class LockedVersionMismatchV1(FrozenStrictModel):
    """A pinned distribution the candidate interpreter does not match."""

    canonical_name: _DistributionName
    required_version: _VersionText
    # ``None`` means the distribution is not installed at all, which is a
    # different defect from installing the wrong version and is kept distinct.
    resolved_version: _VersionText | None = None

    @property
    def missing(self) -> bool:
        return self.resolved_version is None


class LockedEnvironmentRecordV1(FrozenStrictModel):
    """The environment a strict report was produced in, stated exactly.

    This is the artifact a later reader needs in order to decide whether a
    strict result is reproducible.  It carries no case identifier, no problem
    text, and no score — only interpreter and distribution versions.
    """

    version: str = LOCKED_ENVIRONMENT_CONTRACT_VERSION
    python_version: _VersionText
    lock_file: str
    locked_requirements: tuple[LockedRequirementV1, ...] = Field(default=())
    witness_versions: tuple[ResolvedDistributionV1, ...] = Field(default=())
    mismatches: tuple[LockedVersionMismatchV1, ...] = Field(default=())
    offline_variables_cleared: tuple[str, ...] = OFFLINE_REQUIRED_EMPTY_VARIABLES

    @property
    def locked(self) -> bool:
        """True when every pinned distribution resolved to its pinned version."""

        return not self.mismatches


def parse_locked_requirements(text: str) -> tuple[LockedRequirementV1, ...]:
    """Parse a lock file into exact pins.

    Blank lines and ``#`` comments are skipped.  Anything else must be an
    exact ``==`` pin: a range, a marker, or a bare name is a lock file that
    does not lock, and it fails closed rather than being dropped.
    """

    requirements: list[LockedRequirementV1] = []
    seen: set[str] = set()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = _REQUIREMENT.match(line)
        if match is None:
            raise LockedRequirementParseError(
                f"line {number} is not an exact name==version pin"
            )
        name = match.group("name")
        canonical = canonical_distribution_name(name)
        if canonical in seen:
            raise LockedRequirementParseError(
                f"line {number} pins {canonical} a second time"
            )
        seen.add(canonical)
        extras_group = match.group("extras") or ""
        extras = tuple(
            sorted(
                canonical_distribution_name(part)
                for part in extras_group.split(",")
                if part.strip()
            )
        )
        requirements.append(
            LockedRequirementV1(
                name=name,
                canonical_name=canonical,
                version=match.group("version"),
                extras=extras,
            )
        )
    if not requirements:
        raise LockedRequirementParseError("lock file pins nothing")
    return tuple(requirements)


def compare_locked_versions(
    *,
    required: Iterable[LockedRequirementV1],
    resolved: Mapping[str, str | None],
) -> tuple[LockedVersionMismatchV1, ...]:
    """Every pin the resolved environment does not satisfy, in lock order.

    `resolved` maps a distribution name to the version an interpreter reports,
    or to ``None`` when it reports nothing.  Names are canonicalised on both
    sides, so a lock entry spelled ``Pillow`` matches a resolution reported as
    ``pillow``.
    """

    canonical_resolved = {
        canonical_distribution_name(name): version
        for name, version in resolved.items()
    }
    mismatches: list[LockedVersionMismatchV1] = []
    for requirement in required:
        actual = canonical_resolved.get(requirement.canonical_name)
        if actual == requirement.version:
            continue
        mismatches.append(
            LockedVersionMismatchV1(
                canonical_name=requirement.canonical_name,
                required_version=requirement.version,
                resolved_version=actual,
            )
        )
    return tuple(mismatches)


def offline_environment(base: Mapping[str, str]) -> dict[str, str]:
    """`base` with every credential and provider base URL removed.

    Removal, not blanking: `assert_offline_environment` treats an unset name and
    an empty one identically, and removing leaves nothing for a child process to
    read back.  Every other variable is carried through untouched, because a
    strict run still needs `PATH`, `HOME`, and the corpus path.
    """

    required_empty = frozenset(OFFLINE_REQUIRED_EMPTY_VARIABLES)
    return {
        name: value
        for name, value in base.items()
        if name not in required_empty
    }


def offline_environment_is_clean(env: Mapping[str, str]) -> bool:
    """True when no credential or provider base URL carries a value."""

    return all(
        env.get(name, "") == "" for name in OFFLINE_REQUIRED_EMPTY_VARIABLES
    )


def build_locked_environment_record(
    *,
    python_version: str,
    lock_file: str,
    lock_text: str,
    resolved: Mapping[str, str | None],
    witness_names: Sequence[str] = ENVIRONMENT_WITNESS_DISTRIBUTIONS,
) -> LockedEnvironmentRecordV1:
    """The full environment record for a strict run, mismatches included."""

    required = parse_locked_requirements(lock_text)
    canonical_resolved = {
        canonical_distribution_name(name): version
        for name, version in resolved.items()
    }
    witnesses = tuple(
        ResolvedDistributionV1(canonical_name=canonical, version=version)
        for canonical in sorted(
            {canonical_distribution_name(name) for name in witness_names}
        )
        # A witness the environment does not carry is omitted rather than
        # recorded as a mismatch: the witness list names what is worth
        # reporting, not what is required.  Requirements come from the lock.
        for version in (canonical_resolved.get(canonical),)
        if version is not None
    )
    return LockedEnvironmentRecordV1(
        python_version=python_version,
        lock_file=lock_file,
        locked_requirements=required,
        witness_versions=witnesses,
        mismatches=compare_locked_versions(required=required, resolved=resolved),
    )


__all__ = [
    "ENVIRONMENT_WITNESS_DISTRIBUTIONS",
    "LOCKED_ENVIRONMENT_CONTRACT_VERSION",
    "OFFLINE_REQUIRED_EMPTY_VARIABLES",
    "LockedEnvironmentRecordV1",
    "LockedRequirementParseError",
    "LockedRequirementV1",
    "LockedVersionMismatchV1",
    "ResolvedDistributionV1",
    "build_locked_environment_record",
    "canonical_distribution_name",
    "compare_locked_versions",
    "offline_environment",
    "offline_environment_is_clean",
    "parse_locked_requirements",
]
