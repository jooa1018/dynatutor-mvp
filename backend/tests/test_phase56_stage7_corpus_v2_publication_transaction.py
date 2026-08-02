"""Three renames are three chances to crash: the publication attack matrix.

The earlier Phase M fix moved publication *after* the campaign seal, staging
each artifact beside its destination and renaming all three at the end.  That
kept a refused preparation off the final paths.  What it did not do — and
claimed to, in the phrase "an unanticipated failure must not publish half a
preparation" — was make the *successful* publication atomic.  Each of the three
renames was atomic; the set was not.  An exception or a process kill after the
first rename left the authoritative paths holding a new candidate archive
beside an old runtime input and an old attestation, and unlinking the remaining
``.partial`` files could not restore what a completed rename had already
overwritten.  Phase V would refuse the mixture later, but that is a property of
the verifier, not of the publication: between the partial publish and that
refusal, the authoritative paths themselves disagreed about which preparation
they were.

The fixed staging names were their own defects: every run staged into the same
three ``<name>.partial`` files, so two concurrent writers could overwrite or
rename each other's staging; and a read-back mismatch could return before the
staged path had been registered for cleanup, leaving a ``.partial`` behind.

This suite is the attack matrix for the replacement protocol — one immutable
generation directory per preparation, one atomic ``CURRENT.json`` pointer
replace as the only authority change, per-run random staging directories, and
downstream phases pinned to the publication id Phase M printed.  The first
control reproduces the old defect against the legacy protocol itself, so the
matrix starts by proving the defect it exists to close was real.  Everything
here is synthetic; no public archive is read.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from evaluation.phase56_stage7.corpus_v2 import publication
from evaluation.phase56_stage7.corpus_v2.canonical import (
    canonical_digest,
    file_sha256,
)
from evaluation.phase56_stage7.corpus_v2.prepare_attestation import (
    build_prepare_attestation,
    load_prepare_attestation,
    runtime_input_binding_failures,
)
from evaluation.phase56_stage7.corpus_v2.publication import (
    CANDIDATE_ARCHIVE_NAME,
    CURRENT_POINTER_NAME,
    GENERATION_ARTIFACT_NAMES,
    GENERATIONS_DIRECTORY_NAME,
    PREPARE_ATTESTATION_NAME,
    RUNTIME_INPUT_NAME,
    STAGING_DIRECTORY_PREFIX,
    GenerationTransaction,
    PublicationFailure,
    PublicationRefused,
    resolve_published_generation,
)
from evaluation.phase56_stage7.corpus_v2.runtime_input import (
    ShadowRuntimeInputV2,
    load_runtime_input,
)
from tests.support.phase56_stage7_prepare_fixtures import (
    SYNTHETIC_ARCHIVE,
    SYNTHETIC_CANDIDATE,
    SYNTHETIC_CODE_HEAD,
    SYNTHETIC_MANIFEST,
    prepared_context,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY_ROOT / "backend" / "tools"
PREPARE_TOOL = TOOLS / "run_phase56_stage7_v2_shadow_prepare.py"
VERIFY_TOOL = TOOLS / "run_phase56_stage7_v2_shadow_verify_prepare.py"
RUNTIME_TOOL = TOOLS / "run_phase56_stage7_v2_shadow_runtime.py"
SCORE_TOOL = TOOLS / "run_phase56_stage7_v2_shadow_score.py"


# ==========================================================================
# Harness
# ==========================================================================
def _root(tmp_path: Path) -> Path:
    return tmp_path / "publication"


def _body(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _generation_bodies(seed: int):
    """A complete synthetic generation whose id honestly names its content.

    The candidate body varies with ``seed``, so two seeds are two different
    preparations with two different content-addressed generation ids — which
    is exactly what two concurrent writers, or one writer run twice against a
    changed manifest, would produce.
    """

    contexts = tuple(prepared_context(index, refused=index >= 2) for index in range(3))
    bundle = ShadowRuntimeInputV2(
        original_v1_archive_sha256=SYNTHETIC_ARCHIVE,
        augmentation_manifest_sha256=SYNTHETIC_MANIFEST,
        candidate_archive_sha256=SYNTHETIC_CANDIDATE,
        contexts=contexts,
    )
    candidate_body = _body({"synthetic_candidate": seed})
    bundle_body = _body(bundle.model_dump(mode="json"))
    attestation = build_prepare_attestation(
        campaign_seal_name=None,
        exact_code_head=SYNTHETIC_CODE_HEAD,
        original_v1_archive_sha256=SYNTHETIC_ARCHIVE,
        augmentation_manifest_digest=SYNTHETIC_MANIFEST,
        augmentation_manifest_file_sha256="f" * 64,
        candidate_archive_digest=SYNTHETIC_CANDIDATE,
        candidate_archive_file_sha256=file_sha256(candidate_body),
        runtime_input_digest=bundle.digest,
        runtime_input_file_sha256=file_sha256(bundle_body),
        contexts=contexts,
    )
    bodies = {
        CANDIDATE_ARCHIVE_NAME: candidate_body,
        RUNTIME_INPUT_NAME: bundle_body,
        PREPARE_ATTESTATION_NAME: _body(attestation.model_dump(mode="json")),
    }
    return bodies, attestation


def _publish(root: Path, bodies, attestation):
    with GenerationTransaction(root) as transaction:
        for name in GENERATION_ARTIFACT_NAMES:
            transaction.stage(name, bodies[name])
        return transaction.commit(attestation.attestation_digest)


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under the root, byte for byte — the whole authority state."""

    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _staging_directories(root: Path) -> list[Path]:
    generations = root / GENERATIONS_DIRECTORY_NAME
    if not generations.exists():
        return []
    return sorted(
        path
        for path in generations.iterdir()
        if path.name.startswith(STAGING_DIRECTORY_PREFIX)
    )


def _assert_no_residue(root: Path) -> None:
    assert _staging_directories(root) == []
    assert list(root.rglob("*.partial")) == []


def _synthetic_campaign(tmp_path, monkeypatch):
    """A real corpus archive this repository owns, plus two manifests.

    The corpus pin is redirected at the synthetic archive's own hash, exactly
    as the seal suite does.  The second manifest differs from the first by one
    unresolved probe entry — a content change that alters the manifest digest
    and therefore the generation id, while leaving the population untouched.
    That is the cheapest honest way to get two *different* publications out of
    one corpus, which is what the pinning and immutability controls need.
    """

    import hashlib

    from evaluation.phase56_stage7.corpus_integrity import (
        read_public_corpus_archive,
    )
    from evaluation.phase56_stage7.corpus_v2 import prepare_builder
    from tests.support.phase56_stage7_corpus_fixtures import (
        default_members,
        write_plain_archive,
    )

    archive = tmp_path / "corpus.zip"
    write_plain_archive(archive, default_members())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(
        prepare_builder,
        "read_public_corpus_archive",
        lambda path: read_public_corpus_archive(path, expected_sha256=digest),
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "phase56-stage7-corpus-v2-record-v1",
                "migration_version": "phase56-stage7-corpus-v2-migration-v1",
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    baseline = prepare_builder.build_prepared_campaign(
        corpus_archive=archive, manifest=manifest
    )
    fingerprint = json.loads(baseline.candidate_body)["records"][0][
        "original_fingerprint"
    ]
    other_manifest = tmp_path / "other_manifest.json"
    other_manifest.write_text(
        json.dumps(
            {
                "schema_version": "phase56-stage7-corpus-v2-record-v1",
                "migration_version": "phase56-stage7-corpus-v2-migration-v1",
                "entries": [
                    {
                        "original_fingerprint": fingerprint,
                        "review_status": "unresolved",
                        "authoring_provenance": "second-writer probe",
                        "unresolved_reason": "probe",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return archive, manifest, other_manifest


def _run_prepare_tool(tmp_path, monkeypatch, archive, manifest) -> int:
    import runpy

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(PREPARE_TOOL),
            "--corpus-archive",
            str(archive),
            "--manifest",
            str(manifest),
            "--publication-root",
            str(_root(tmp_path)),
            "--exact-code-head",
            SYNTHETIC_CODE_HEAD,
        ],
    )
    module = runpy.run_path(str(PREPARE_TOOL), run_name="not_main")
    return module["main"]()


def _run_verifier_pinned(
    tmp_path, monkeypatch, archive, manifest, publication_id
) -> int:
    import runpy

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(VERIFY_TOOL),
            "--corpus-archive",
            str(archive),
            "--manifest",
            str(manifest),
            "--publication-root",
            str(_root(tmp_path)),
            "--publication-id",
            publication_id,
            "--verification-report",
            str(tmp_path / "verify.json"),
            "--exact-code-head",
            SYNTHETIC_CODE_HEAD,
        ],
    )
    module = runpy.run_path(str(VERIFY_TOOL), run_name="not_main")
    return module["main"]()


def _publication_id_from(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("STAGE7_V2_PREPARE_PUBLICATION_ID="):
            return line.split("=", 1)[1]
    raise AssertionError(f"no publication id in output:\n{output}")


# ==========================================================================
# 5.1 The old defect, reproduced — and the new protocol under the same fault
# ==========================================================================
def _legacy_stage(path: Path, body: str) -> tuple[Path, Path]:
    """The pre-fix staging: a fixed ``.partial`` beside the destination."""

    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(path.name + ".partial")
    staged.write_text(body, encoding="utf-8")
    return staged, path


def _legacy_publish(staged, *, interrupt_after: int) -> None:
    """The pre-fix ``_publish``, with the crash window made explicit.

    This is the exact shape ``run_phase56_stage7_v2_shadow_prepare.py`` used at
    `8471126b`: one ``Path.replace`` per artifact, in sequence.  The
    interruption stands in for any exception or process kill between the
    renames — the window the old comment called "one `replace` call wide",
    which it was per artifact and was not for the set.
    """

    for index, (source, destination) in enumerate(staged):
        if index >= interrupt_after:
            raise KeyboardInterrupt("interrupted between sequential renames")
        source.replace(destination)


def test_5_1_the_legacy_sequential_replace_mixed_two_generations(tmp_path) -> None:
    """The regression control: the defect this package exists to close is real.

    An earlier honest generation sits at the three final paths; a second
    publication is interrupted after its first rename; the old cleanup —
    unlinking the staged files — runs exactly as the old ``except`` path did.
    The result is a *mixed* generation at the authoritative paths: the new
    candidate archive beside the old runtime input and the old attestation.
    Nothing on disk can restore the overwritten candidate, which is the
    difference between "each rename is atomic" and "the publication is".
    """

    names = ("candidate.json", "runtime_input.json", "attestation.json")
    finals = {name: tmp_path / "out" / name for name in names}
    for name, path in finals.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"generation-one {name}\n", encoding="utf-8")

    staged = [
        _legacy_stage(path, f"generation-two {name}\n")
        for name, path in finals.items()
    ]

    with pytest.raises(KeyboardInterrupt):
        _legacy_publish(staged, interrupt_after=1)
    for source, _ in staged:
        source.unlink(missing_ok=True)

    published = {
        name: path.read_text(encoding="utf-8") for name, path in finals.items()
    }
    assert published["candidate.json"] == "generation-two candidate.json\n"
    assert published["runtime_input.json"] == "generation-one runtime_input.json\n"
    assert published["attestation.json"] == "generation-one attestation.json\n"
    generations = {body.split()[0] for body in published.values()}
    assert generations == {"generation-one", "generation-two"}, (
        "the legacy protocol was expected to mix generations under this fault"
    )


def test_5_1_the_same_interruption_cannot_mix_the_new_authority(
    tmp_path, monkeypatch
) -> None:
    """The matched positive: every crash window leaves one whole generation.

    The same interruption is injected at each boundary the new protocol has —
    the generation promote and the pointer replace.  After either, the
    previous pointer bytes are identical, the previous generation's three
    artifacts are identical, and a reader resolves all three artifacts from
    that one generation.  There is no window in which the authority holds
    artifacts from two preparations, because the artifacts never move
    separately.
    """

    root = _root(tmp_path)
    bodies_one, attestation_one = _generation_bodies(1)
    ref_one = _publish(root, bodies_one, attestation_one)
    before = _tree_bytes(root)

    bodies_two, attestation_two = _generation_bodies(2)

    def interrupt(*_args):
        raise KeyboardInterrupt("interrupted at the promote")

    monkeypatch.setattr(publication, "_rename_directory", interrupt)
    with pytest.raises(KeyboardInterrupt):
        _publish(root, bodies_two, attestation_two)
    monkeypatch.undo()
    # Interrupted before the promote completed: the tree is byte-identical —
    # not merely equivalent — to the pre-attack state.
    assert _tree_bytes(root) == before

    def interrupt_replace(*_args):
        raise KeyboardInterrupt("interrupted at the pointer replace")

    monkeypatch.setattr(publication, "_replace_file", interrupt_replace)
    with pytest.raises(KeyboardInterrupt):
        _publish(root, bodies_two, attestation_two)
    monkeypatch.undo()

    # Interrupted between the promote and the pointer replace: the previous
    # authority is untouched and the new generation is a complete,
    # unreferenced orphan — never a mixture.
    after = _tree_bytes(root)
    assert after[CURRENT_POINTER_NAME] == before[CURRENT_POINTER_NAME]
    for name, body in before.items():
        assert after[name] == body
    current = resolve_published_generation(root)
    assert current.generation_id == ref_one.generation_id
    for name in GENERATION_ARTIFACT_NAMES:
        assert (current.generation_path / name).read_text(
            encoding="utf-8"
        ) == bodies_one[name]
    orphan = resolve_published_generation(
        root, publication_id=attestation_two.attestation_digest
    )
    assert orphan.generation_id == attestation_two.attestation_digest
    _assert_no_residue(root)


# ==========================================================================
# 5.2 Read-back mismatch: fail closed, clean only what this run owns
# ==========================================================================
@pytest.mark.parametrize(
    "artifact, gate",
    [
        (CANDIDATE_ARCHIVE_NAME, "prepare_candidate_archive_write_mismatch"),
        (RUNTIME_INPUT_NAME, "prepare_runtime_input_write_mismatch"),
        (PREPARE_ATTESTATION_NAME, "prepare_attestation_write_mismatch"),
    ],
)
def test_5_2_a_read_back_mismatch_refuses_and_cleans_its_own_staging(
    tmp_path, monkeypatch, capsys, artifact, gate
) -> None:
    """A write that lost its tail refuses by name and leaves no trace.

    The old ``_stage`` could return ``None`` before its staged path had been
    added to the cleanup list, leaving a ``.partial`` behind — the candidate
    archive case here is exactly that path, attacked directly: the *first*
    staged artifact fails before anything else exists to clean up.  In the new
    protocol the staging directory is created before any artifact and removed
    whole, so there is no registration step to miss.  A foreign writer's
    staging directory and the earlier authority are untouched.
    """

    archive, manifest, _ = _synthetic_campaign(tmp_path, monkeypatch)
    assert _run_prepare_tool(tmp_path, monkeypatch, archive, manifest) == 0
    capsys.readouterr()
    root = _root(tmp_path)
    before = _tree_bytes(root)

    foreign = root / GENERATIONS_DIRECTORY_NAME / f"{STAGING_DIRECTORY_PREFIX}foreign"
    foreign.mkdir(parents=True)
    (foreign / "another-writers-file").write_text("theirs\n", encoding="utf-8")

    real_read_back = publication._read_back_file_sha256

    def corrupted_read_back(path: Path) -> str:
        if path.name == artifact and path.parent.name.startswith(
            STAGING_DIRECTORY_PREFIX
        ):
            return "0" * 64
        return real_read_back(path)

    monkeypatch.setattr(publication, "_read_back_file_sha256", corrupted_read_back)
    status = _run_prepare_tool(tmp_path, monkeypatch, archive, manifest)
    captured = capsys.readouterr()
    monkeypatch.undo()

    assert status == 2
    assert f"STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:{gate}" in captured.err
    assert "STAGE7_V2_PREPARE_PUBLICATION_ID=" not in captured.out

    after = _tree_bytes(root)
    assert after.pop(f"{GENERATIONS_DIRECTORY_NAME}/.tmp-foreign/another-writers-file")
    assert after == before, "the refused run changed something it did not own"
    assert _staging_directories(root) == [foreign]
    assert list(root.rglob("*.partial")) == []
    assert resolve_published_generation(root).generation_id == (
        load_prepare_attestation(
            resolve_published_generation(root).prepare_attestation.read_text(
                encoding="utf-8"
            )
        ).attestation_digest
    )


# ==========================================================================
# 5.3 Exception after the writes: own staging cleaned, nothing else touched
# ==========================================================================
def test_5_3_an_exception_after_the_writes_cleans_only_its_own_staging(
    tmp_path, monkeypatch, capsys
) -> None:
    """An unanticipated failure between the writes and the return.

    Injected after the candidate archive and the runtime input are staged —
    the same point the old protocol's ``except BaseException`` path guarded.
    The transaction's exit aborts: this run's staging directory is gone, the
    earlier authority is byte-unchanged, and a foreign staging directory and
    the committed generations of other writers still exist untouched.
    """

    from evaluation.phase56_stage7.corpus_v2 import prepare_attestation

    archive, manifest, _ = _synthetic_campaign(tmp_path, monkeypatch)
    assert _run_prepare_tool(tmp_path, monkeypatch, archive, manifest) == 0
    capsys.readouterr()
    root = _root(tmp_path)
    before = _tree_bytes(root)

    foreign = root / GENERATIONS_DIRECTORY_NAME / f"{STAGING_DIRECTORY_PREFIX}foreign"
    foreign.mkdir(parents=True)
    (foreign / "another-writers-file").write_text("theirs\n", encoding="utf-8")

    def explode(**_kwargs):
        raise RuntimeError("injected after the artifact writes")

    monkeypatch.setattr(prepare_attestation, "build_prepare_attestation", explode)
    with pytest.raises(RuntimeError, match="injected after the artifact writes"):
        _run_prepare_tool(tmp_path, monkeypatch, archive, manifest)
    capsys.readouterr()
    monkeypatch.undo()

    after = _tree_bytes(root)
    assert after.pop(f"{GENERATIONS_DIRECTORY_NAME}/.tmp-foreign/another-writers-file")
    assert after == before
    assert _staging_directories(root) == [foreign]
    assert list(root.rglob("*.partial")) == []


# ==========================================================================
# 5.4 Generation committed, pointer not committed
# ==========================================================================
def test_5_4_a_generation_without_a_pointer_is_a_complete_unreferenced_orphan(
    tmp_path, monkeypatch
) -> None:
    """The promote succeeded and the pointer staging failed.

    The previous CURRENT is byte-unchanged and still resolves; the new
    generation is on disk, complete — all three artifacts, hashes intact, so a
    pinned resolve accepts it — and *unreferenced*: no reader that resolves
    the pointer can observe it.  That orphan is the documented cost of never
    deleting a directory another writer might have committed to.
    """

    root = _root(tmp_path)
    bodies_one, attestation_one = _generation_bodies(1)
    ref_one = _publish(root, bodies_one, attestation_one)
    pointer_before = (root / CURRENT_POINTER_NAME).read_bytes()

    bodies_two, attestation_two = _generation_bodies(2)
    real_write = publication._write_file

    def fail_pointer_staging(path: Path, body: str) -> None:
        if path.name.startswith("CURRENT."):
            raise OSError("injected: the pointer could not be staged")
        real_write(path, body)

    monkeypatch.setattr(publication, "_write_file", fail_pointer_staging)
    with pytest.raises(PublicationRefused) as refusal:
        _publish(root, bodies_two, attestation_two)
    monkeypatch.undo()

    assert PublicationFailure.pointer_commit_failed.value in str(refusal.value)
    assert (root / CURRENT_POINTER_NAME).read_bytes() == pointer_before
    assert resolve_published_generation(root).generation_id == ref_one.generation_id

    orphan = resolve_published_generation(
        root, publication_id=attestation_two.attestation_digest
    )
    for name in GENERATION_ARTIFACT_NAMES:
        assert (orphan.generation_path / name).read_text(
            encoding="utf-8"
        ) == bodies_two[name]
    _assert_no_residue(root)


# ==========================================================================
# 5.5 The pointer replace itself fails
# ==========================================================================
def test_5_5_a_failed_pointer_replace_keeps_the_previous_authority(
    tmp_path, monkeypatch, capsys
) -> None:
    """The staged pointer was perfect and the atomic replace still failed.

    Driven through the whole Phase M command: exit 2 under
    ``publication_pointer_commit_failed``, the previous pointer bytes
    unchanged and still naming the previous generation, no pointer partial
    left behind, and the new generation left as a complete orphan.  CURRENT
    never points at partial JSON or at a generation that does not exist,
    because the only thing that ever overwrites it is a validated, fsynced
    staged pointer.
    """

    archive, manifest, other_manifest = _synthetic_campaign(tmp_path, monkeypatch)
    assert _run_prepare_tool(tmp_path, monkeypatch, archive, manifest) == 0
    first_id = _publication_id_from(capsys.readouterr().out)
    root = _root(tmp_path)
    pointer_before = (root / CURRENT_POINTER_NAME).read_bytes()

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("injected: the pointer replace failed")

    monkeypatch.setattr(publication, "_replace_file", fail_replace)
    status = _run_prepare_tool(tmp_path, monkeypatch, archive, other_manifest)
    captured = capsys.readouterr()
    monkeypatch.undo()

    assert status == 2
    assert (
        "STAGE7_V2_PREPARE_ACCEPTANCE=FAIL:"
        f"{PublicationFailure.pointer_commit_failed.value}" in captured.err
    )
    assert (root / CURRENT_POINTER_NAME).read_bytes() == pointer_before
    current = resolve_published_generation(root)
    assert current.generation_id == first_id
    assert list(root.rglob("*.partial")) == []
    assert _staging_directories(root) == []
    orphans = [
        path.name
        for path in sorted((root / GENERATIONS_DIRECTORY_NAME).iterdir())
        if path.name != first_id
    ]
    assert len(orphans) == 1
    resolve_published_generation(root, publication_id=orphans[0])


# ==========================================================================
# 5.6 Success: complete, idempotent, and immutable across publications
# ==========================================================================
def test_5_6_a_successful_publication_is_complete_idempotent_and_immutable(
    tmp_path, monkeypatch, capsys
) -> None:
    """The positive control, from the published bytes and nothing else.

    Every hash is recomputed from what is actually on disk: the three file
    SHA-256 values against the pointer and the attestation, the runtime
    input's canonical digest against the attestation, the attestation's own
    digest against the generation id.  Republication of identical content
    converges on the same generation; publication of different content gets a
    new generation and leaves the first byte-identical.
    """

    archive, manifest, other_manifest = _synthetic_campaign(tmp_path, monkeypatch)
    root = _root(tmp_path)

    assert _run_prepare_tool(tmp_path, monkeypatch, archive, manifest) == 0
    first_out = capsys.readouterr().out
    published = resolve_published_generation(root)
    assert (
        f"STAGE7_V2_PREPARE_PUBLICATION_ID={published.generation_id}" in first_out
    )

    candidate_body = published.candidate_archive.read_text(encoding="utf-8")
    bundle_body = published.runtime_input.read_text(encoding="utf-8")
    attestation_body = published.prepare_attestation.read_text(encoding="utf-8")
    attestation = load_prepare_attestation(attestation_body)
    assert attestation.attestation_digest == published.generation_id
    assert attestation.recomputed_digest() == published.generation_id
    assert file_sha256(candidate_body) == attestation.candidate_archive_file_sha256
    assert file_sha256(bundle_body) == attestation.runtime_input_file_sha256
    assert file_sha256(candidate_body) == published.candidate_archive_file_sha256
    assert file_sha256(bundle_body) == published.runtime_input_file_sha256
    assert file_sha256(attestation_body) == (
        published.prepare_attestation_file_sha256
    )
    bundle = load_runtime_input(bundle_body)
    assert bundle.digest == attestation.runtime_input_digest
    assert (
        runtime_input_binding_failures(
            attestation,
            bundle,
            runtime_input_file_sha256=file_sha256(bundle_body),
            exact_code_head=SYNTHETIC_CODE_HEAD,
        )
        == ()
    )
    _assert_no_residue(root)

    # Identical content again: same generation, no duplicate, bytes untouched.
    generation_before = _tree_bytes(published.generation_path)
    assert _run_prepare_tool(tmp_path, monkeypatch, archive, manifest) == 0
    second_out = capsys.readouterr().out
    assert _publication_id_from(second_out) == published.generation_id
    assert [
        path.name for path in sorted((root / GENERATIONS_DIRECTORY_NAME).iterdir())
    ] == [published.generation_id]
    assert _tree_bytes(published.generation_path) == generation_before

    # Different content: a second generation appears, the first is immutable,
    # and the pointer — the only authority — moves to the new one.
    assert _run_prepare_tool(tmp_path, monkeypatch, archive, other_manifest) == 0
    third_out = capsys.readouterr().out
    second_id = _publication_id_from(third_out)
    assert second_id != published.generation_id
    assert _tree_bytes(published.generation_path) == generation_before
    assert resolve_published_generation(root).generation_id == second_id
    assert len(list((root / GENERATIONS_DIRECTORY_NAME).iterdir())) == 2
    _assert_no_residue(root)


# ==========================================================================
# 5.7 Reader pinning: a moved pointer cannot redirect a running pipeline
# ==========================================================================
def test_5_7_a_pointer_moved_after_prepare_cannot_redirect_a_pinned_pipeline(
    tmp_path, monkeypatch, capsys
) -> None:
    """Phase M returned an id; a second writer then re-pointed CURRENT.

    The pinned resolve keeps returning the first generation — its paths, its
    bytes, its hashes — and a pinned Phase V verifies it end-to-end while the
    pointer names the second one.  The cross-generation direction fails by
    name: verifying the pinned first generation against the second writer's
    manifest hits the replay gates, and pairing the second attestation with
    the first bundle fails the binding — which is what "Phase V, R and G must
    fail rather than mix generations" means mechanically.
    """

    archive, manifest, other_manifest = _synthetic_campaign(tmp_path, monkeypatch)
    root = _root(tmp_path)

    assert _run_prepare_tool(tmp_path, monkeypatch, archive, manifest) == 0
    first_id = _publication_id_from(capsys.readouterr().out)

    # The second writer publishes and takes the pointer.
    assert _run_prepare_tool(tmp_path, monkeypatch, archive, other_manifest) == 0
    second_id = _publication_id_from(capsys.readouterr().out)
    assert second_id != first_id
    assert resolve_published_generation(root).generation_id == second_id

    # The first pipeline is pinned to the id Phase M returned, not to CURRENT.
    pinned = resolve_published_generation(root, publication_id=first_id)
    assert pinned.generation_id == first_id
    assert pinned.generation_path.name == first_id
    first_attestation = load_prepare_attestation(
        pinned.prepare_attestation.read_text(encoding="utf-8")
    )
    assert first_attestation.attestation_digest == first_id

    # A pinned Phase V verifies the first generation against the first
    # manifest and passes, with the pointer still naming the second.
    status = _run_verifier_pinned(
        tmp_path, monkeypatch, archive, manifest, first_id
    )
    verifier_out = capsys.readouterr().out
    assert status == 0, verifier_out
    assert f"STAGE7_V2_VERIFY_PREPARE_PUBLICATION_ID={first_id}" in verifier_out
    assert "STAGE7_V2_VERIFY_PREPARE_ACCEPTANCE=PASS" in verifier_out
    assert resolve_published_generation(root).generation_id == second_id

    # The mixed direction is a named refusal, not a quiet re-pin: the first
    # generation against the second writer's manifest fails the replay.
    status = _run_verifier_pinned(
        tmp_path, monkeypatch, archive, other_manifest, first_id
    )
    mixed_out = capsys.readouterr().out
    assert status == 2, mixed_out
    assert "replay_manifest_digest_mismatch" in mixed_out

    # And the second attestation cannot admit the first bundle: Phase R and
    # Phase G's shared binding check refuses the cross-generation pair.
    second = resolve_published_generation(root, publication_id=second_id)
    second_attestation = load_prepare_attestation(
        second.prepare_attestation.read_text(encoding="utf-8")
    )
    first_bundle_body = pinned.runtime_input.read_text(encoding="utf-8")
    failures = runtime_input_binding_failures(
        second_attestation,
        load_runtime_input(first_bundle_body),
        runtime_input_file_sha256=file_sha256(first_bundle_body),
    )
    assert "prepare_manifest_digest_mismatch" in failures


# ==========================================================================
# 5.8 Concurrent writers, interleaved deterministically
# ==========================================================================
def test_5_8_two_interleaved_writers_never_share_staging_or_mix_authority(
    tmp_path,
) -> None:
    """Every interleaving invariant, without a sleep anywhere.

    The two transactions are driven through stage and commit in lockstep from
    one thread — a deterministic schedule that covers the shared-state
    hazards concurrency would randomize: staging isolation, generation
    completeness at every observation point, pointer validity between the two
    commits, last-writer-wins on the pointer, and the first pipeline's pin
    surviving the second writer's commit.
    """

    root = _root(tmp_path)
    bodies_a, attestation_a = _generation_bodies(1)
    bodies_b, attestation_b = _generation_bodies(2)
    assert attestation_a.attestation_digest != attestation_b.attestation_digest

    writer_a = GenerationTransaction(root)
    writer_b = GenerationTransaction(root)
    try:
        assert writer_a.token != writer_b.token
        staging = _staging_directories(root)
        assert len(staging) == 2

        for name in GENERATION_ARTIFACT_NAMES:
            writer_a.stage(name, bodies_a[name])
            writer_b.stage(name, bodies_b[name])

        ref_a = writer_a.commit(attestation_a.attestation_digest)
        # Between the two commits: A is the complete authority, and B's
        # staging still exists untouched by A's publication.
        mid = resolve_published_generation(root)
        assert mid.generation_id == ref_a.generation_id
        assert len(_staging_directories(root)) == 1

        ref_b = writer_b.commit(attestation_b.attestation_digest)
        final = resolve_published_generation(root)
        assert final.generation_id == ref_b.generation_id
    finally:
        writer_a.abort()
        writer_b.abort()

    # Both generations are complete and byte-correct; the loser of the
    # pointer race is still resolvable by its pin, which is exactly what the
    # first pipeline holds.
    for ref, bodies in ((ref_a, bodies_a), (ref_b, bodies_b)):
        pinned = resolve_published_generation(root, publication_id=ref.generation_id)
        for name in GENERATION_ARTIFACT_NAMES:
            assert (pinned.generation_path / name).read_text(
                encoding="utf-8"
            ) == bodies[name]
    _assert_no_residue(root)


def test_5_8_two_writers_of_identical_content_converge_on_one_generation(
    tmp_path,
) -> None:
    """Deterministic rebuilds collide by design, and the collision is benign.

    The second writer finds the generation directory already present, proves
    it byte-identical to what it staged, discards its own staging, and swings
    the pointer to the same id.  One generation, no corruption, no residue.
    """

    root = _root(tmp_path)
    bodies, attestation = _generation_bodies(7)

    writer_a = GenerationTransaction(root)
    writer_b = GenerationTransaction(root)
    for name in GENERATION_ARTIFACT_NAMES:
        writer_a.stage(name, bodies[name])
        writer_b.stage(name, bodies[name])
    ref_a = writer_a.commit(attestation.attestation_digest)
    ref_b = writer_b.commit(attestation.attestation_digest)

    assert ref_a.generation_id == ref_b.generation_id
    assert [
        path.name for path in sorted((root / GENERATIONS_DIRECTORY_NAME).iterdir())
    ] == [ref_a.generation_id]
    resolved = resolve_published_generation(root)
    for name in GENERATION_ARTIFACT_NAMES:
        assert (resolved.generation_path / name).read_text(
            encoding="utf-8"
        ) == bodies[name]
    _assert_no_residue(root)


def test_5_8_a_colliding_id_over_different_bytes_is_refused_untouched(
    tmp_path,
) -> None:
    """The id is content-addressed, so this collision is tampering by definition.

    A generation directory already exists under the id but its candidate
    archive has been altered.  The second writer refuses under
    ``publication_generation_collision``, does not modify or delete the
    existing directory, and cleans only its own staging.  The reader side then
    refuses the tampered generation too — fail closed on both ends.
    """

    root = _root(tmp_path)
    bodies, attestation = _generation_bodies(9)
    ref = _publish(root, bodies, attestation)
    tampered = ref.generation_path / CANDIDATE_ARCHIVE_NAME
    tampered.write_text(bodies[CANDIDATE_ARCHIVE_NAME] + "tampered\n", "utf-8")
    tampered_bytes = tampered.read_bytes()

    with pytest.raises(PublicationRefused) as refusal:
        _publish(root, bodies, attestation)

    assert PublicationFailure.generation_collision.value in str(refusal.value)
    assert tampered.read_bytes() == tampered_bytes
    assert ref.generation_path.is_dir()
    _assert_no_residue(root)

    with pytest.raises(PublicationRefused) as reader_refusal:
        resolve_published_generation(root)
    assert PublicationFailure.generation_file_sha_mismatch.value in str(
        reader_refusal.value
    )


# ==========================================================================
# 5.9 Pointer validation: every malformed authority is refused by name
# ==========================================================================
def _resigned(payload: dict) -> dict:
    """A forged pointer whose self-digest is consistent with its forgery.

    Re-signing is what a capable attacker does; a control that only ever
    tests an inconsistent forgery would only ever exercise the digest gate.
    """

    forged = {key: value for key, value in payload.items() if key != "pointer_digest"}
    forged["pointer_digest"] = canonical_digest(forged)
    return forged


@pytest.mark.parametrize(
    "corrupt, gate",
    [
        pytest.param(
            lambda payload: "{ this is not json",
            PublicationFailure.pointer_malformed.value,
            id="malformed_json",
        ),
        pytest.param(
            lambda payload: "[]\n",
            PublicationFailure.pointer_malformed.value,
            id="not_an_object",
        ),
        pytest.param(
            lambda payload: _body(
                {k: v for k, v in payload.items() if k != "generation_id"}
            ),
            PublicationFailure.pointer_malformed.value,
            id="generation_id_field_removed",
        ),
        pytest.param(
            lambda payload: _body(dict(payload, version="pointer-v999")),
            PublicationFailure.pointer_version_unknown.value,
            id="unknown_schema_version",
        ),
        pytest.param(
            lambda payload: _body(dict(payload, generation_id="")),
            PublicationFailure.generation_id_missing.value,
            id="empty_generation_id",
        ),
        pytest.param(
            lambda payload: _body(dict(payload, generation_id="../evil")),
            PublicationFailure.generation_id_malformed.value,
            id="path_traversal_id",
        ),
        pytest.param(
            lambda payload: _body(dict(payload, generation_id="/etc/passwd")),
            PublicationFailure.generation_id_malformed.value,
            id="absolute_path_id",
        ),
        pytest.param(
            lambda payload: _body(
                dict(payload, generation_id="aaaa/" + "b" * 59)
            ),
            PublicationFailure.generation_id_malformed.value,
            id="separator_injection_id",
        ),
        pytest.param(
            lambda payload: _body(dict(payload, generation_id="A" * 64)),
            PublicationFailure.generation_id_malformed.value,
            id="uppercase_id",
        ),
        pytest.param(
            lambda payload: _body(dict(payload, pointer_digest="0" * 64)),
            PublicationFailure.pointer_digest_mismatch.value,
            id="pointer_digest_tampered",
        ),
        pytest.param(
            lambda payload: _body(
                _resigned(
                    dict(
                        payload,
                        generation_id="f" * 64,
                        prepare_attestation_digest="f" * 64,
                    )
                )
            ),
            PublicationFailure.generation_missing.value,
            id="nonexistent_generation",
        ),
        pytest.param(
            lambda payload: _body(
                _resigned(dict(payload, prepare_attestation_digest="e" * 64))
            ),
            PublicationFailure.generation_attestation_mismatch.value,
            id="pointer_and_generation_metadata_disagree",
        ),
        pytest.param(
            lambda payload: _body(
                _resigned(dict(payload, candidate_archive_file_sha256="d" * 64))
            ),
            PublicationFailure.generation_file_sha_mismatch.value,
            id="forged_artifact_hash",
        ),
    ],
)
def test_5_9_a_corrupted_pointer_is_refused_by_name_and_repairs_nothing(
    tmp_path, corrupt, gate
) -> None:
    root = _root(tmp_path)
    bodies, attestation = _generation_bodies(3)
    _publish(root, bodies, attestation)
    payload = json.loads((root / CURRENT_POINTER_NAME).read_text(encoding="utf-8"))

    (root / CURRENT_POINTER_NAME).write_text(corrupt(payload), encoding="utf-8")
    before = _tree_bytes(root)

    with pytest.raises(PublicationRefused) as refusal:
        resolve_published_generation(root)

    assert gate in str(refusal.value), refusal.value
    # A refusal never repairs: the resolver is read-only even about a
    # corrupted authority.
    assert _tree_bytes(root) == before


def test_5_9_a_missing_pointer_and_a_missing_artifact_are_named(tmp_path) -> None:
    root = _root(tmp_path)
    bodies, attestation = _generation_bodies(4)
    ref = _publish(root, bodies, attestation)

    (ref.generation_path / RUNTIME_INPUT_NAME).unlink()
    with pytest.raises(PublicationRefused) as refusal:
        resolve_published_generation(root)
    assert PublicationFailure.generation_artifact_missing.value in str(refusal.value)
    assert RUNTIME_INPUT_NAME in str(refusal.value)

    (root / CURRENT_POINTER_NAME).unlink()
    with pytest.raises(PublicationRefused) as no_pointer:
        resolve_published_generation(root)
    assert PublicationFailure.pointer_missing.value in str(no_pointer.value)


def test_5_9_a_tampered_generation_is_refused_under_its_own_gates(
    tmp_path,
) -> None:
    """Generation-side tampering, distinguished from pointer-side tampering."""

    root = _root(tmp_path)
    bodies, attestation = _generation_bodies(5)
    ref = _publish(root, bodies, attestation)

    candidate = ref.generation_path / CANDIDATE_ARCHIVE_NAME
    candidate.write_text(bodies[CANDIDATE_ARCHIVE_NAME] + "extra\n", "utf-8")
    with pytest.raises(PublicationRefused) as refusal:
        resolve_published_generation(root)
    assert PublicationFailure.generation_file_sha_mismatch.value in str(refusal.value)
    candidate.write_text(bodies[CANDIDATE_ARCHIVE_NAME], "utf-8")

    attestation_path = ref.generation_path / PREPARE_ATTESTATION_NAME
    payload = json.loads(bodies[PREPARE_ATTESTATION_NAME])
    payload["attestation_digest"] = "9" * 64
    attestation_path.write_text(_body(payload), "utf-8")
    with pytest.raises(PublicationRefused) as renamed:
        resolve_published_generation(root, publication_id=ref.generation_id)
    assert PublicationFailure.generation_attestation_mismatch.value in str(
        renamed.value
    )


def test_5_9_a_pinned_resolve_rejects_malformed_and_absent_ids(tmp_path) -> None:
    """The pin is validated exactly as hard as the pointer it bypasses."""

    root = _root(tmp_path)
    bodies, attestation = _generation_bodies(6)
    _publish(root, bodies, attestation)

    for malformed in ("../evil", "/etc/passwd", "A" * 64, "abc", "a/" + "b" * 62):
        with pytest.raises(PublicationRefused) as refusal:
            resolve_published_generation(root, publication_id=malformed)
        assert PublicationFailure.generation_id_malformed.value in str(refusal.value)

    with pytest.raises(PublicationRefused) as missing:
        resolve_published_generation(root, publication_id="f" * 64)
    assert PublicationFailure.generation_missing.value in str(missing.value)


def test_5_9_the_reader_tools_refuse_an_unresolvable_publication(tmp_path) -> None:
    """Phase R and Phase G at the process boundary, before anything else runs.

    An empty publication root has no pointer; both commands exit 2 naming the
    pointer gate, and neither writes an artifact.  The direct-path harness
    contract is also pinned: a publication root beside a direct path is a
    contract refusal, not a silent preference for either.
    """

    empty_root = tmp_path / "empty-publication"
    empty_root.mkdir()

    runtime = subprocess.run(
        [
            sys.executable,
            str(RUNTIME_TOOL),
            "--publication-root",
            str(empty_root),
            "--runtime-snapshot",
            str(tmp_path / "snapshot.json"),
            "--redacted-view",
            str(tmp_path / "redacted.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert runtime.returncode == 2
    assert PublicationFailure.pointer_missing.value in runtime.stderr
    assert not (tmp_path / "snapshot.json").exists()
    assert not (tmp_path / "redacted.json").exists()

    score = subprocess.run(
        [
            sys.executable,
            str(SCORE_TOOL),
            "--corpus-archive",
            str(tmp_path / "no-such-corpus.zip"),
            "--runtime-snapshot",
            str(tmp_path / "no-such-snapshot.json"),
            "--publication-root",
            str(empty_root),
            "--shadow-report",
            str(tmp_path / "report.json"),
            "--scorecard",
            str(tmp_path / "scorecard.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert score.returncode == 2
    assert PublicationFailure.pointer_missing.value in score.stderr
    assert not (tmp_path / "report.json").exists()

    both_modes = subprocess.run(
        [
            sys.executable,
            str(RUNTIME_TOOL),
            "--publication-root",
            str(empty_root),
            "--runtime-input",
            str(tmp_path / "direct.json"),
            "--runtime-snapshot",
            str(tmp_path / "snapshot.json"),
            "--redacted-view",
            str(tmp_path / "redacted.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert both_modes.returncode == 2
    assert "publication_input_contract" in both_modes.stderr


# ==========================================================================
# 5.10 There is no publication path around the transaction
# ==========================================================================
def test_5_10_the_prepare_tool_cannot_publish_outside_the_transaction() -> None:
    """The unsafe flat-path publication is gone, not merely deprecated.

    Read off the AST: Phase M performs no ``replace``, ``rename`` or
    ``write_text`` of its own — every byte it publishes goes through the
    transaction, so a sequential-replacement fallback cannot exist in the
    file, silently or otherwise.  The old per-artifact output flags are gone
    from its CLI, so no caller can even ask for a flat-path publication.
    """

    source = PREPARE_TOOL.read_text("utf-8")
    tree = ast.parse(source)
    attribute_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "replace" not in attribute_calls
    assert "rename" not in attribute_calls
    assert "write_text" not in attribute_calls
    assert "write_bytes" not in attribute_calls
    assert "GenerationTransaction" in source
    for retired_flag in (
        '"--candidate-archive"',
        '"--runtime-input"',
        '"--prepare-attestation"',
    ):
        assert retired_flag not in source

    orchestrator = (TOOLS / "run_phase56_stage7_v2_shadow.py").read_text("utf-8")
    assert '"--publication-root"' in orchestrator
    assert '"--publication-id"' in orchestrator
    assert '"--candidate-archive"' not in orchestrator
