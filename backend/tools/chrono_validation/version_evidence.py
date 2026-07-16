from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import importlib
import json
import os
from pathlib import Path
import platform
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse


class PyChronoEvidenceError(RuntimeError):
    """A classified, fail-closed environment evidence failure."""

    def __init__(self, classification: str, message: str):
        super().__init__(message)
        self.classification = classification


@dataclass(frozen=True)
class ExpectedPyChronoEnvironment:
    package: str
    version: str
    build: str
    channel: str
    python: str

    def __post_init__(self) -> None:
        for name in ("package", "version", "build", "channel", "python"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"expected {name} must be non-empty")

    @property
    def package_name(self) -> str:
        # A conda pin may be channel-qualified (projectchrono::pychrono), while
        # the installed package record correctly stores only name=pychrono.
        return self.package.rsplit("::", 1)[-1].strip()

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CondaPackageRecord:
    name: str
    version: str
    build: str
    channel: str
    source: str
    record_path: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class PyChronoEnvironmentEvidence:
    expected: ExpectedPyChronoEnvironment
    package: CondaPackageRecord
    python_runtime_version: str
    import_module: str
    import_succeeded: bool
    core_api: str
    core_api_present: bool
    module_version: str | None
    module_version_source: str | None
    selected_version: str
    selected_version_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "verified",
            "expected": self.expected.to_dict(),
            "package": self.package.to_dict(),
            "python_runtime_version": self.python_runtime_version,
            "import": {
                "module": self.import_module,
                "succeeded": self.import_succeeded,
                "core_api": self.core_api,
                "core_api_present": self.core_api_present,
            },
            "module_version": self.module_version,
            "module_version_source": self.module_version_source,
            "selected_version": self.selected_version,
            "selected_version_source": self.selected_version_source,
            "checks": {
                "package_name_matches": True,
                "version_matches": True,
                "build_matches": True,
                "channel_matches": True,
                "python_runtime_matches": True,
                "module_metadata_consistent": True,
                "import_succeeded": True,
                "core_api_present": True,
            },
        }


Importer = Callable[[str], ModuleType]


def verify_pychrono_environment(
    expected: ExpectedPyChronoEnvironment,
    *,
    conda_prefix: str | os.PathLike[str] | None = None,
    importer: Importer = importlib.import_module,
    python_runtime_version: str | None = None,
) -> PyChronoEnvironmentEvidence:
    runtime = str(python_runtime_version or platform.python_version())
    if not _python_matches(runtime, expected.python):
        raise PyChronoEvidenceError(
            "python_runtime_mismatch",
            f"installed Python runtime {runtime!r} does not match {expected.python!r}",
        )

    try:
        module = importer("pychrono")
    except ModuleNotFoundError as exc:
        raise PyChronoEvidenceError(
            "dependency_missing",
            f"PyChrono import failed because the module is missing: {exc}",
        ) from exc
    except (ImportError, OSError) as exc:
        raise PyChronoEvidenceError(
            "import_error",
            f"PyChrono import failed with {type(exc).__name__}: {exc}",
        ) from exc

    if not hasattr(module, "ChSystemNSC"):
        raise PyChronoEvidenceError(
            "core_api_missing",
            "pychrono imported but does not expose ChSystemNSC",
        )

    record = read_conda_package_record(
        expected.package_name,
        conda_prefix=conda_prefix,
    )
    _verify_record(record, expected)

    module_version, module_source = module_version_evidence(module)
    if module_version is not None and module_version != record.version:
        raise PyChronoEvidenceError(
            "version_evidence_conflict",
            "PyChrono module version "
            f"{module_version!r} from {module_source} contradicts installed "
            f"conda metadata version {record.version!r}",
        )

    selected_version = module_version or record.version
    selected_source = module_source or "conda-meta"
    if selected_version != expected.version:
        raise PyChronoEvidenceError(
            "version_mismatch",
            f"selected installed version {selected_version!r} does not match {expected.version!r}",
        )

    return PyChronoEnvironmentEvidence(
        expected=expected,
        package=record,
        python_runtime_version=runtime,
        import_module="pychrono",
        import_succeeded=True,
        core_api="ChSystemNSC",
        core_api_present=True,
        module_version=module_version,
        module_version_source=module_source,
        selected_version=selected_version,
        selected_version_source=selected_source,
    )


def read_conda_package_record(
    package_name: str,
    *,
    conda_prefix: str | os.PathLike[str] | None = None,
) -> CondaPackageRecord:
    prefix_value = conda_prefix if conda_prefix is not None else os.environ.get("CONDA_PREFIX")
    if not prefix_value:
        raise PyChronoEvidenceError(
            "conda_prefix_missing",
            "CONDA_PREFIX is not set and no conda prefix was supplied",
        )
    metadata_dir = Path(prefix_value) / "conda-meta"
    if not metadata_dir.is_dir():
        raise PyChronoEvidenceError(
            "metadata_missing",
            f"conda metadata directory does not exist: {metadata_dir}",
        )

    canonical_name = _normalize_package_name(package_name)
    matches: list[CondaPackageRecord] = []
    metadata_files = sorted(metadata_dir.glob("*.json"), key=lambda item: item.name)
    if not metadata_files:
        raise PyChronoEvidenceError(
            "metadata_missing",
            f"conda metadata directory is empty: {metadata_dir}",
        )

    # Parse every conda record. A corrupted environment record is not silently
    # ignored based on a filename guess, and duplicate package records remain visible.
    for path in metadata_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PyChronoEvidenceError(
                "metadata_malformed",
                f"cannot parse conda package record {path.name}: {type(exc).__name__}: {exc}",
            ) from exc
        if not isinstance(payload, Mapping):
            raise PyChronoEvidenceError(
                "metadata_malformed",
                f"conda package record {path.name} is not a JSON object",
            )
        raw_name = payload.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise PyChronoEvidenceError(
                "metadata_malformed",
                f"conda package record {path.name} has no package name",
            )
        if _normalize_package_name(raw_name) != canonical_name:
            continue
        matches.append(_package_record_from_payload(payload, path))

    if not matches:
        raise PyChronoEvidenceError(
            "package_record_missing",
            f"no installed conda package record found for {package_name!r}",
        )
    if len(matches) != 1:
        paths = ", ".join(record.record_path for record in matches)
        raise PyChronoEvidenceError(
            "package_record_ambiguous",
            f"multiple installed conda package records found for {package_name!r}: {paths}",
        )
    return matches[0]


def module_version_evidence(module: ModuleType) -> tuple[str | None, str | None]:
    raw = getattr(module, "__version__", None)
    if raw is not None and str(raw).strip():
        return str(raw).strip(), "module.__version__"
    for name in ("GetChronoVersion", "GetVersion"):
        function = getattr(module, name, None)
        if not callable(function):
            continue
        try:
            raw = function()
        except (RuntimeError, TypeError, ValueError) as exc:
            raise PyChronoEvidenceError(
                "module_version_error",
                f"pychrono.{name} failed with {type(exc).__name__}: {exc}",
            ) from exc
        if raw is not None and str(raw).strip():
            return str(raw).strip(), f"module.{name}()"
    raw = getattr(module, "CHRONO_VERSION", None)
    if raw is not None and str(raw).strip():
        return str(raw).strip(), "module.CHRONO_VERSION"
    return None, None


def installed_pychrono_version(
    module: ModuleType,
    *,
    conda_prefix: str | os.PathLike[str] | None = None,
) -> str:
    module_version, _ = module_version_evidence(module)
    if module_version is not None:
        return module_version
    return read_conda_package_record("pychrono", conda_prefix=conda_prefix).version


def _package_record_from_payload(
    payload: Mapping[str, Any],
    path: Path,
) -> CondaPackageRecord:
    values: dict[str, str] = {}
    for name in ("name", "version", "build"):
        raw = payload.get(name)
        if not isinstance(raw, str) or not raw.strip():
            raise PyChronoEvidenceError(
                "metadata_malformed",
                f"conda package record {path.name} has no valid {name}",
            )
        values[name] = raw.strip()

    raw_channel = payload.get("schannel") or payload.get("channel") or payload.get("url")
    if not isinstance(raw_channel, str) or not raw_channel.strip():
        raise PyChronoEvidenceError(
            "metadata_malformed",
            f"conda package record {path.name} has no channel/source",
        )
    raw_source = payload.get("url") or payload.get("channel") or payload.get("schannel")
    if not isinstance(raw_source, str) or not raw_source.strip():
        raw_source = raw_channel
    channel = _normalize_channel(raw_channel)
    if not channel:
        raise PyChronoEvidenceError(
            "metadata_malformed",
            f"cannot normalize channel from conda package record {path.name}",
        )
    return CondaPackageRecord(
        name=values["name"],
        version=values["version"],
        build=values["build"],
        channel=channel,
        source=raw_source.strip(),
        record_path=str(path),
    )


def _verify_record(
    record: CondaPackageRecord,
    expected: ExpectedPyChronoEnvironment,
) -> None:
    if _normalize_package_name(record.name) != _normalize_package_name(expected.package_name):
        raise PyChronoEvidenceError(
            "package_name_mismatch",
            f"installed package name {record.name!r} does not match {expected.package_name!r}",
        )
    if record.version != expected.version:
        raise PyChronoEvidenceError(
            "version_mismatch",
            f"installed metadata version {record.version!r} does not match {expected.version!r}",
        )
    if record.build != expected.build:
        raise PyChronoEvidenceError(
            "build_mismatch",
            f"installed build {record.build!r} does not match {expected.build!r}",
        )
    if _normalize_channel(expected.channel) != record.channel:
        raise PyChronoEvidenceError(
            "channel_mismatch",
            f"installed channel {record.channel!r} does not match {expected.channel!r}",
        )


def _python_matches(actual: str, expected: str) -> bool:
    actual_parts = actual.strip().split(".")
    expected_parts = expected.strip().split(".")
    if len(actual_parts) < len(expected_parts):
        return False
    return actual_parts[: len(expected_parts)] == expected_parts


def _normalize_package_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _normalize_channel(value: str) -> str:
    raw = value.strip().lower().rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc in {"conda.anaconda.org", "anaconda.org"} and parts:
            return parts[0]
        if "projectchrono" in parts:
            return "projectchrono"
        if "conda-forge" in parts:
            return "conda-forge"
        return raw
    parts = [part for part in raw.split("/") if part]
    if len(parts) > 1 and parts[-1] in {
        "linux-64",
        "linux-aarch64",
        "osx-64",
        "osx-arm64",
        "win-64",
        "noarch",
    }:
        parts.pop()
    return "/".join(parts)


def _failure_payload(
    expected: ExpectedPyChronoEnvironment,
    error: PyChronoEvidenceError,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "expected": expected.to_dict(),
        "failure": {
            "classification": error.classification,
            "message": str(error),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify pinned real PyChrono evidence")
    parser.add_argument("--expected-package", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-build", required=True)
    parser.add_argument("--expected-channel", required=True)
    parser.add_argument("--expected-python", required=True)
    parser.add_argument("--conda-prefix")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    expected = ExpectedPyChronoEnvironment(
        package=args.expected_package,
        version=args.expected_version,
        build=args.expected_build,
        channel=args.expected_channel,
        python=args.expected_python,
    )
    try:
        payload = verify_pychrono_environment(
            expected,
            conda_prefix=args.conda_prefix,
        ).to_dict()
        exit_code = 0
    except PyChronoEvidenceError as exc:
        payload = _failure_payload(expected, exc)
        exit_code = 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CondaPackageRecord",
    "ExpectedPyChronoEnvironment",
    "PyChronoEnvironmentEvidence",
    "PyChronoEvidenceError",
    "installed_pychrono_version",
    "main",
    "module_version_evidence",
    "read_conda_package_record",
    "verify_pychrono_environment",
]
