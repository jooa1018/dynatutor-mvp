from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pytest

from tools.chrono_validation.version_evidence import (
    ExpectedPyChronoEnvironment,
    PyChronoEvidenceError,
    verify_pychrono_environment,
)


EXPECTED = ExpectedPyChronoEnvironment(
    package="projectchrono::pychrono",
    version="9.0.1",
    build="py312hf1de3a3_6463",
    channel="projectchrono",
    python="3.12",
)


def _module(*, version: str | None = None, core_api: bool = True) -> ModuleType:
    module = ModuleType("pychrono")
    if version is not None:
        module.__version__ = version
    if core_api:
        module.ChSystemNSC = type("ChSystemNSC", (), {})
    return module


def _write_record(
    prefix: Path,
    *,
    name: str = "pychrono",
    version: str = "9.0.1",
    build: str = "py312hf1de3a3_6463",
    channel: str = "projectchrono",
    source: str = "https://conda.anaconda.org/projectchrono/linux-64/pychrono.tar.bz2",
    suffix: str = "one",
) -> Path:
    metadata = prefix / "conda-meta"
    metadata.mkdir(parents=True, exist_ok=True)
    path = metadata / f"{name}-{version}-{suffix}.json"
    path.write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "build": build,
                "schannel": channel,
                "channel": f"https://conda.anaconda.org/{channel}",
                "url": source,
            }
        ),
        encoding="utf-8",
    )
    return path


def _verify(prefix: Path, module: ModuleType, expected=EXPECTED):
    return verify_pychrono_environment(
        expected,
        conda_prefix=prefix,
        importer=lambda name: module,
        python_runtime_version="3.12.13",
    )


@pytest.mark.unit
def test_module_version_and_metadata_both_prove_the_pin(tmp_path):
    _write_record(tmp_path)
    evidence = _verify(tmp_path, _module(version="9.0.1"))
    assert evidence.selected_version == "9.0.1"
    assert evidence.selected_version_source == "module.__version__"
    assert evidence.package.version == "9.0.1"


@pytest.mark.unit
def test_missing_module_version_falls_back_to_actual_conda_metadata(tmp_path):
    _write_record(tmp_path)
    module = _module()
    module.GetChronoVersion = lambda: None
    evidence = _verify(tmp_path, module)
    assert evidence.module_version is None
    assert evidence.selected_version == "9.0.1"
    assert evidence.selected_version_source == "conda-meta"


@pytest.mark.unit
def test_module_and_metadata_version_conflict_fails_closed(tmp_path):
    _write_record(tmp_path)
    with pytest.raises(PyChronoEvidenceError) as raised:
        _verify(tmp_path, _module(version="9.0.0"))
    assert raised.value.classification == "version_evidence_conflict"


@pytest.mark.unit
def test_conda_metadata_version_mismatch_fails_closed(tmp_path):
    _write_record(tmp_path, version="9.0.0")
    with pytest.raises(PyChronoEvidenceError) as raised:
        _verify(tmp_path, _module())
    assert raised.value.classification == "version_mismatch"


@pytest.mark.unit
def test_missing_package_metadata_fails_closed(tmp_path):
    (tmp_path / "conda-meta").mkdir()
    with pytest.raises(PyChronoEvidenceError) as raised:
        _verify(tmp_path, _module())
    assert raised.value.classification == "metadata_missing"


@pytest.mark.unit
def test_multiple_package_records_are_ambiguous(tmp_path):
    _write_record(tmp_path, suffix="one")
    _write_record(tmp_path, suffix="two")
    with pytest.raises(PyChronoEvidenceError) as raised:
        _verify(tmp_path, _module())
    assert raised.value.classification == "package_record_ambiguous"


@pytest.mark.unit
def test_package_import_failure_is_distinct(tmp_path):
    _write_record(tmp_path)

    def missing(name: str):
        raise ModuleNotFoundError("No module named 'pychrono'", name="pychrono")

    with pytest.raises(PyChronoEvidenceError) as raised:
        verify_pychrono_environment(
            EXPECTED,
            conda_prefix=tmp_path,
            importer=missing,
            python_runtime_version="3.12.13",
        )
    assert raised.value.classification == "dependency_missing"


@pytest.mark.unit
def test_missing_chsystemnsc_core_api_fails_closed(tmp_path):
    _write_record(tmp_path)
    with pytest.raises(PyChronoEvidenceError) as raised:
        _verify(tmp_path, _module(core_api=False))
    assert raised.value.classification == "core_api_missing"


@pytest.mark.unit
def test_malformed_conda_metadata_json_fails_closed(tmp_path):
    metadata = tmp_path / "conda-meta"
    metadata.mkdir()
    (metadata / "pychrono-malformed.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(PyChronoEvidenceError) as raised:
        _verify(tmp_path, _module())
    assert raised.value.classification == "metadata_malformed"


@pytest.mark.unit
def test_channel_qualified_pin_matches_real_pychrono_record_name(tmp_path):
    _write_record(
        tmp_path,
        name="pychrono",
        channel="projectchrono",
        source="https://conda.anaconda.org/projectchrono/linux-64/pychrono-9.0.1.tar.bz2",
    )
    evidence = _verify(tmp_path, _module())
    assert evidence.expected.package == "projectchrono::pychrono"
    assert evidence.package.name == "pychrono"
    assert evidence.package.channel == "projectchrono"
    assert evidence.package.source.startswith("https://conda.anaconda.org/projectchrono/")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("record_overrides", "runtime", "classification"),
    [
        ({"build": "wrong_build"}, "3.12.13", "build_mismatch"),
        ({"channel": "conda-forge"}, "3.12.13", "channel_mismatch"),
        ({}, "3.11.9", "python_runtime_mismatch"),
    ],
)
def test_build_channel_and_python_mismatches_fail_closed(
    tmp_path,
    record_overrides,
    runtime,
    classification,
):
    _write_record(tmp_path, **record_overrides)
    with pytest.raises(PyChronoEvidenceError) as raised:
        verify_pychrono_environment(
            EXPECTED,
            conda_prefix=tmp_path,
            importer=lambda name: _module(),
            python_runtime_version=runtime,
        )
    assert raised.value.classification == classification
