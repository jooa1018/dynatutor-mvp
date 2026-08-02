"""One immutable generation, one pointer replace: how a preparation is published.

Phase M produces three artifacts that are only meaningful together — the
candidate archive, the runtime input, and the attestation that binds them.  The
previous publication moved them to three final paths with three consecutive
``os.replace`` calls.  Each rename was atomic; the *set* was not.  An exception
or a process kill between the first rename and the last left the final paths
holding artifacts from two different preparations — a new candidate archive
beside an old runtime input and an old attestation — and deleting the leftover
staging files could not undo a rename that had already happened.  Phase V would
later refuse the mixed set, but "a later phase rejects it" is a property of the
verifier, not of the publication: between the partial publish and that
verification, the authoritative paths themselves were lying.

This module closes that by making the unit of publication a *generation* and
the unit of authority a *pointer*:

    <publication-root>/
        generations/
            .tmp-<token>/            one writer's private staging directory
            <generation-id>/         an immutable, complete generation
                candidate-archive.json
                runtime-input.json
                prepare-attestation.json
        CURRENT.json                 the single authority pointer
        CURRENT.<token>.partial      the pointer's staged replacement, briefly

* **Immutable generations.**  Every successful preparation becomes its own
  directory named by its attestation's canonical digest, holding all three
  artifacts.  Nothing ever writes into an existing generation: a second
  publication of the same content adopts the byte-identical directory that is
  already there, and a colliding id over *different* bytes is refused.
* **Unique staging.**  Each run stages into ``generations/.tmp-<token>`` with a
  fresh random token and ``exist_ok=False``, so two writers cannot share or
  overwrite each other's staging, and a failed run deletes only the directory
  it owns.  Staging lives inside ``generations/`` so the promote is a rename
  on one filesystem.
* **One commit point.**  Authority changes exactly once, at
  ``os.replace(CURRENT.<token>.partial, CURRENT.json)``, after the whole
  generation is complete, validated, and promoted.  A reader that resolves the
  pointer either sees the old complete generation or the new complete
  generation.  There is no instant at which it can see a mixture, because the
  three artifacts are never at the authoritative location separately.
* **Pinned readers.**  ``resolve_published_generation`` with a
  ``publication_id`` never opens ``CURRENT.json`` at all: a pipeline that
  captured Phase M's publication id once keeps reading that generation however
  many times another writer replaces the pointer afterwards.

Failure semantics, stated exactly rather than optimistically.  A failure before
the promote leaves the previous pointer and every existing generation
byte-unchanged and removes the failed run's staging directory.  A failure
*after* the promote but before the pointer replace leaves the previous pointer
authoritative and byte-unchanged — and leaves the new generation on disk as a
complete but unreferenced orphan, which is deliberate: deleting it would mean
deleting a directory another writer may legitimately have just committed a
pointer to.  "No mixed authoritative generation, previous authority preserved,
a failed publication may leave an unreferenced complete generation" is the
claim this module makes, and the one its controls prove.

Durability is claimed at the process level, not the power-cable level.  Files
are flushed with ``os.fsync`` before they are renamed and the enclosing
directories are fsynced best-effort afterwards, which is the conventional POSIX
ordering discipline — but no test here pulls a power cable, so crash-consistency
across an OS or hardware failure is *not* asserted.  What is asserted is that no
reader of a live filesystem can observe a mixed or half-published authority.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .canonical import canonical_digest, file_sha256

PUBLICATION_POINTER_VERSION = "phase56-stage7-corpus-v2-publication-pointer-v1"

GENERATIONS_DIRECTORY_NAME = "generations"
CURRENT_POINTER_NAME = "CURRENT.json"
STAGING_DIRECTORY_PREFIX = ".tmp-"

CANDIDATE_ARCHIVE_NAME = "candidate-archive.json"
RUNTIME_INPUT_NAME = "runtime-input.json"
PREPARE_ATTESTATION_NAME = "prepare-attestation.json"
GENERATION_ARTIFACT_NAMES = (
    CANDIDATE_ARCHIVE_NAME,
    RUNTIME_INPUT_NAME,
    PREPARE_ATTESTATION_NAME,
)

# A generation id is a lowercase SHA-256 hex digest and nothing else.  The id
# is used as a path component, so this pattern is also the traversal guard: a
# separator, a dot-dot, an absolute path or a drive letter cannot match it.
_GENERATION_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_POINTER_FIELDS = frozenset(
    {
        "version",
        "generation_id",
        "prepare_attestation_digest",
        "candidate_archive_file_sha256",
        "runtime_input_file_sha256",
        "prepare_attestation_file_sha256",
        "pointer_digest",
    }
)


class PublicationFailure(str, Enum):
    """The names a publication is refused under.

    Names rather than booleans, for the same reason every other gate in this
    package has them: a control must be able to assert the gate it meant to
    hit, and a pointer-tampering attack that surfaced only as "something went
    wrong" would be no evidence that the pointer is checked at all.
    """

    pointer_missing = "publication_pointer_missing"
    pointer_malformed = "publication_pointer_malformed"
    pointer_version_unknown = "publication_pointer_version_unknown"
    pointer_digest_mismatch = "publication_pointer_digest_mismatch"
    generation_id_missing = "publication_generation_id_missing"
    generation_id_malformed = "publication_generation_id_malformed"
    generation_missing = "publication_generation_missing"
    generation_artifact_missing = "publication_generation_artifact_missing"
    generation_attestation_mismatch = "publication_generation_attestation_mismatch"
    generation_file_sha_mismatch = "publication_generation_file_sha_mismatch"
    staging_conflict = "publication_staging_conflict"
    staged_write_mismatch = "publication_staged_write_mismatch"
    generation_incomplete = "publication_generation_incomplete"
    generation_collision = "publication_generation_collision"
    generation_promote_failed = "publication_generation_promote_failed"
    pointer_commit_failed = "publication_pointer_commit_failed"


class PublicationRefused(RuntimeError):
    """A publication that cannot be completed honestly is not made authoritative.

    Raised fail-closed on both sides: a writer that cannot prove its staged
    bytes refuses to move the pointer, and a reader that cannot validate the
    pointer or the generation refuses to hand any artifact path out.  A refusal
    never repairs anything — the previous valid authority is left exactly as it
    was found.
    """


# --------------------------------------------------------------------------
# Filesystem seams.  Module-level and single-purpose, so a fault-injection
# control can fail exactly one step of the protocol — "the pointer replace
# fails" is a different attack from "the pointer cannot be staged", and a
# monkeypatched os would not let a test tell them apart.
# --------------------------------------------------------------------------
def _rename_directory(source: Path, destination: Path) -> None:
    """Promote a staged generation.  Atomic on one filesystem; fails, never merges."""

    os.rename(source, destination)


def _replace_file(source: Path, destination: Path) -> None:
    """The single authority commit point."""

    os.replace(source, destination)


def _write_file(path: Path, body: str) -> None:
    """Write and flush an artifact's bytes.  ``fsync`` before any rename, so the
    rename cannot be durable while the content it names is not — the POSIX
    ordering discipline, claimed as ordering and not as power-loss proof."""

    data = body.encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        while data:
            data = data[os.write(descriptor, data) :]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_back_file_sha256(path: Path) -> str:
    """The hash of what a reader would actually get, not of what was meant."""

    return file_sha256(path.read_text(encoding="utf-8"))


def _fsync_directory(path: Path) -> None:
    """Best-effort directory-entry flush.  Platforms that cannot fsync a
    directory keep the atomic-visibility guarantee and lose only the
    crash-ordering hint, which is why this swallows ``OSError`` and the module
    docstring does not claim power-loss durability."""

    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _assert_generation_id(value: Any) -> str:
    if not isinstance(value, str) or not _GENERATION_ID_PATTERN.fullmatch(value):
        raise PublicationRefused(
            f"{PublicationFailure.generation_id_malformed.value}: {value!r}"
        )
    return value


@dataclass(frozen=True)
class PublicationPointer:
    """The validated content of ``CURRENT.json``.

    ``prepare_attestation_digest`` repeats the generation id on purpose: the id
    *is* the attestation's canonical digest, and carrying the same fact twice
    makes a pointer edited in one place refuse in a named way instead of
    resolving to whichever field the editor forgot.
    """

    version: str
    generation_id: str
    prepare_attestation_digest: str
    candidate_archive_file_sha256: str
    runtime_input_file_sha256: str
    prepare_attestation_file_sha256: str
    pointer_digest: str


@dataclass(frozen=True)
class PublishedPreparationRef:
    """A pinned, validated view of one published generation.

    This is the only object a downstream phase should take artifact paths
    from.  It is a *reference*, not an authority: authority was decided once,
    when the pointer (or an explicitly pinned publication id) was resolved, and
    this object keeps naming that same generation no matter what happens to
    ``CURRENT.json`` afterwards.  Any flat-path copy a caller makes from these
    paths is a non-authoritative export by definition.
    """

    publication_root: Path
    generation_id: str
    generation_path: Path
    candidate_archive: Path
    runtime_input: Path
    prepare_attestation: Path
    candidate_archive_file_sha256: str
    runtime_input_file_sha256: str
    prepare_attestation_file_sha256: str


def _pointer_body(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def load_publication_pointer(publication_root: Path) -> PublicationPointer:
    """Read and validate ``CURRENT.json``, refusing every malformed shape by name."""

    pointer_path = publication_root / CURRENT_POINTER_NAME
    if not pointer_path.is_file():
        raise PublicationRefused(
            f"{PublicationFailure.pointer_missing.value}: {pointer_path}"
        )
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PublicationRefused(
            f"{PublicationFailure.pointer_malformed.value}: {exc}"
        ) from None
    if not isinstance(payload, dict) or set(payload) != _POINTER_FIELDS:
        raise PublicationRefused(
            f"{PublicationFailure.pointer_malformed.value}: unexpected field set"
        )
    if payload["version"] != PUBLICATION_POINTER_VERSION:
        raise PublicationRefused(
            f"{PublicationFailure.pointer_version_unknown.value}: "
            f"{payload['version']!r}"
        )
    if not payload["generation_id"]:
        raise PublicationRefused(PublicationFailure.generation_id_missing.value)
    generation_id = _assert_generation_id(payload["generation_id"])
    try:
        recomputed = canonical_digest(
            {key: value for key, value in payload.items() if key != "pointer_digest"}
        )
    except (TypeError, ValueError) as exc:
        raise PublicationRefused(
            f"{PublicationFailure.pointer_malformed.value}: {exc}"
        ) from None
    if payload["pointer_digest"] != recomputed:
        raise PublicationRefused(PublicationFailure.pointer_digest_mismatch.value)
    if payload["prepare_attestation_digest"] != generation_id:
        raise PublicationRefused(
            f"{PublicationFailure.generation_attestation_mismatch.value}: the "
            "pointer's attestation digest is not its generation id"
        )
    return PublicationPointer(**payload)


def _validated_generation(
    publication_root: Path,
    generation_id: str,
    *,
    pointer: PublicationPointer | None,
) -> PublishedPreparationRef:
    """Check one generation is complete and is the one its name claims.

    The attestation's *internal* consistency — its digest over its own material
    — is recomputed here from plain JSON, so a generation cannot resolve under
    an id its content does not hash to.  The heavier semantic loads
    (`load_prepare_attestation`, `load_runtime_input`, Phase V's rebuild) stay
    where they are; this layer decides only whether these bytes are one
    complete, self-consistent, correctly-named generation.
    """

    generation_path = publication_root / GENERATIONS_DIRECTORY_NAME / generation_id
    if not generation_path.is_dir():
        raise PublicationRefused(
            f"{PublicationFailure.generation_missing.value}: {generation_id}"
        )
    paths = {name: generation_path / name for name in GENERATION_ARTIFACT_NAMES}
    digests: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            raise PublicationRefused(
                f"{PublicationFailure.generation_artifact_missing.value}: {name}"
            )
        try:
            digests[name] = _read_back_file_sha256(path)
        except OSError as exc:
            raise PublicationRefused(
                f"{PublicationFailure.generation_artifact_missing.value}: "
                f"{name}: {exc}"
            ) from None

    try:
        attestation_payload = json.loads(
            paths[PREPARE_ATTESTATION_NAME].read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise PublicationRefused(
            f"{PublicationFailure.generation_attestation_mismatch.value}: {exc}"
        ) from None
    if not isinstance(attestation_payload, dict):
        raise PublicationRefused(
            f"{PublicationFailure.generation_attestation_mismatch.value}: the "
            "attestation is not an object"
        )
    if attestation_payload.get("attestation_digest") != generation_id:
        raise PublicationRefused(
            f"{PublicationFailure.generation_attestation_mismatch.value}: the "
            "attestation names a different digest than the generation id"
        )
    try:
        recomputed = canonical_digest(
            {
                key: value
                for key, value in attestation_payload.items()
                if key != "attestation_digest"
            }
        )
    except (TypeError, ValueError) as exc:
        raise PublicationRefused(
            f"{PublicationFailure.generation_attestation_mismatch.value}: {exc}"
        ) from None
    if recomputed != generation_id:
        raise PublicationRefused(
            f"{PublicationFailure.generation_attestation_mismatch.value}: the "
            "attestation's material does not hash to the generation id"
        )

    expected = {
        CANDIDATE_ARCHIVE_NAME: attestation_payload.get(
            "candidate_archive_file_sha256"
        ),
        RUNTIME_INPUT_NAME: attestation_payload.get("runtime_input_file_sha256"),
    }
    if pointer is not None:
        pointer_expected = {
            CANDIDATE_ARCHIVE_NAME: pointer.candidate_archive_file_sha256,
            RUNTIME_INPUT_NAME: pointer.runtime_input_file_sha256,
            PREPARE_ATTESTATION_NAME: pointer.prepare_attestation_file_sha256,
        }
        for name, value in pointer_expected.items():
            current = expected.get(name)
            if current is not None and current != value:
                raise PublicationRefused(
                    f"{PublicationFailure.generation_file_sha_mismatch.value}: "
                    f"{name}: the pointer and the attestation disagree"
                )
            expected[name] = value
    for name, value in expected.items():
        if value != digests[name]:
            raise PublicationRefused(
                f"{PublicationFailure.generation_file_sha_mismatch.value}: {name}"
            )

    return PublishedPreparationRef(
        publication_root=publication_root,
        generation_id=generation_id,
        generation_path=generation_path,
        candidate_archive=paths[CANDIDATE_ARCHIVE_NAME],
        runtime_input=paths[RUNTIME_INPUT_NAME],
        prepare_attestation=paths[PREPARE_ATTESTATION_NAME],
        candidate_archive_file_sha256=digests[CANDIDATE_ARCHIVE_NAME],
        runtime_input_file_sha256=digests[RUNTIME_INPUT_NAME],
        prepare_attestation_file_sha256=digests[PREPARE_ATTESTATION_NAME],
    )


def resolve_published_generation(
    publication_root: Path, *, publication_id: str | None = None
) -> PublishedPreparationRef:
    """Resolve the authority once, and pin what it resolved to.

    With ``publication_id`` the pointer is never opened: the caller was handed
    an exact generation by Phase M — or by the orchestrator that captured Phase
    M's output — and re-reading ``CURRENT.json`` here is precisely the re-
    interpretation that would let two phases of one pipeline observe two
    different preparations.  Without it, the pointer is read and validated
    exactly once, and the returned reference stays on that generation whatever
    happens to the pointer afterwards.
    """

    if publication_id is not None:
        _assert_generation_id(publication_id)
        return _validated_generation(publication_root, publication_id, pointer=None)
    pointer = load_publication_pointer(publication_root)
    return _validated_generation(
        publication_root, pointer.generation_id, pointer=pointer
    )


class GenerationTransaction:
    """Stage a whole preparation, validate it, then publish it at one commit point.

    Used as a context manager.  Leaving the context without a successful
    :meth:`commit` — an early ``return``, a raised exception, a refused gate —
    aborts the transaction, which removes the staging directory this run owns
    and nothing else.  After the generation has been promoted, an abort no
    longer touches it: a complete generation is immutable even when the pointer
    swing after it failed, in which case it remains an unreferenced orphan and
    the previous authority stands.
    """

    def __init__(self, publication_root: Path) -> None:
        self.publication_root = publication_root
        self._generations = publication_root / GENERATIONS_DIRECTORY_NAME
        self._token = uuid.uuid4().hex
        self._staging = self._generations / f"{STAGING_DIRECTORY_PREFIX}{self._token}"
        self._staged: dict[str, str] = {}
        self._promoted: Path | None = None
        self._published = False
        try:
            self._generations.mkdir(parents=True, exist_ok=True)
            # ``exist_ok=False`` is the whole concurrency story for staging: a
            # colliding token — however unlikely — refuses instead of letting
            # two writers interleave bytes in one directory.
            self._staging.mkdir(exist_ok=False)
        except OSError as exc:
            raise PublicationRefused(
                f"{PublicationFailure.staging_conflict.value}: {exc}"
            ) from None

    def __enter__(self) -> "GenerationTransaction":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if not self._published:
            self.abort()
        return False

    @property
    def token(self) -> str:
        return self._token

    def stage(self, name: str, body: str) -> str:
        """Write one artifact into this run's staging directory and prove it.

        The returned hash is recomputed from the bytes read back off the
        filesystem, never from ``body``: the attestation built over this value
        is a statement about the file a later phase will open, so a write that
        lost its tail must fail *here*, before anything is attested.  On a
        mismatch the whole transaction is refused — there is no per-file
        cleanup to forget, because abort removes the one directory this run
        owns.
        """

        if name not in GENERATION_ARTIFACT_NAMES:
            raise PublicationRefused(
                f"{PublicationFailure.generation_incomplete.value}: {name} is "
                "not a generation artifact"
            )
        path = self._staging / name
        _write_file(path, body)
        written = _read_back_file_sha256(path)
        if written != file_sha256(body):
            raise PublicationRefused(
                f"{PublicationFailure.staged_write_mismatch.value}: {name}"
            )
        self._staged[name] = written
        return written

    def staged_body(self, name: str) -> str:
        """Re-read a staged artifact from disk.

        Validation before the commit must judge the bytes a reader would see,
        not the value the writer still holds in memory.
        """

        return (self._staging / name).read_text(encoding="utf-8")

    def abort(self) -> None:
        """Remove only what this run owns.

        The staging directory is this run's; a promoted generation is not —
        it is immutable, and possibly the very directory another writer has
        meanwhile pointed ``CURRENT.json`` at.  Another writer's staging is
        never touched: the token in the name is the ownership boundary.
        """

        if self._promoted is None and self._staging.exists():
            shutil.rmtree(self._staging, ignore_errors=True)

    def commit(self, generation_id: str) -> PublishedPreparationRef:
        """Promote the staged generation, then replace the pointer.  In that order.

        Everything that can refuse has refused by the time the promote happens;
        everything after the promote either completes the publication or leaves
        a complete orphan behind the unchanged previous authority.  The
        authority itself moves in the single ``_replace_file`` call and nowhere
        else.
        """

        _assert_generation_id(generation_id)
        missing = [
            name for name in GENERATION_ARTIFACT_NAMES if name not in self._staged
        ]
        if missing:
            raise PublicationRefused(
                f"{PublicationFailure.generation_incomplete.value}: "
                + ",".join(missing)
            )

        # The staged attestation must itself name this generation.  The id is
        # content-addressed, so committing these bytes under any other id would
        # be publishing a generation whose name lies about its content.
        try:
            attestation_payload = json.loads(
                self.staged_body(PREPARE_ATTESTATION_NAME)
            )
        except ValueError as exc:
            raise PublicationRefused(
                f"{PublicationFailure.generation_attestation_mismatch.value}: "
                f"{exc}"
            ) from None
        if (
            not isinstance(attestation_payload, dict)
            or attestation_payload.get("attestation_digest") != generation_id
        ):
            raise PublicationRefused(
                f"{PublicationFailure.generation_attestation_mismatch.value}: "
                "the staged attestation does not name this generation id"
            )
        staged_expectations = {
            CANDIDATE_ARCHIVE_NAME: attestation_payload.get(
                "candidate_archive_file_sha256"
            ),
            RUNTIME_INPUT_NAME: attestation_payload.get(
                "runtime_input_file_sha256"
            ),
        }
        for name, value in staged_expectations.items():
            if value != self._staged[name]:
                raise PublicationRefused(
                    f"{PublicationFailure.generation_file_sha_mismatch.value}: "
                    f"{name}: the staged attestation disagrees with the staged "
                    "bytes"
                )

        _fsync_directory(self._staging)
        destination = self._generations / generation_id
        try:
            _rename_directory(self._staging, destination)
        except OSError as exc:
            if destination.is_dir():
                # Deterministic rebuilds make identical republication a normal
                # event, not an attack: adopt a byte-identical existing
                # generation, refuse a different one, and never write into it
                # either way.
                self._adopt_existing(destination)
            else:
                raise PublicationRefused(
                    f"{PublicationFailure.generation_promote_failed.value}: "
                    f"{exc}"
                ) from None
        self._promoted = destination
        _fsync_directory(self._generations)

        payload: dict[str, Any] = {
            "version": PUBLICATION_POINTER_VERSION,
            "generation_id": generation_id,
            "prepare_attestation_digest": generation_id,
            "candidate_archive_file_sha256": self._staged[CANDIDATE_ARCHIVE_NAME],
            "runtime_input_file_sha256": self._staged[RUNTIME_INPUT_NAME],
            "prepare_attestation_file_sha256": self._staged[
                PREPARE_ATTESTATION_NAME
            ],
        }
        payload["pointer_digest"] = canonical_digest(payload)
        body = _pointer_body(payload)
        partial = self.publication_root / f"CURRENT.{self._token}.partial"
        try:
            _write_file(partial, body)
            if _read_back_file_sha256(partial) != file_sha256(body):
                raise PublicationRefused(
                    f"{PublicationFailure.pointer_commit_failed.value}: the "
                    "staged pointer read back differently than written"
                )
            _replace_file(partial, self.publication_root / CURRENT_POINTER_NAME)
        except BaseException as exc:
            # Whatever interrupted the swing, the staged pointer is this run's
            # to remove; the previous CURRENT was never touched.  Only a kill
            # that outruns this handler can leave the token-named partial
            # behind, and a stray partial is inert — no reader opens one and
            # no later writer can collide with its token.
            partial.unlink(missing_ok=True)
            if isinstance(exc, OSError):
                raise PublicationRefused(
                    f"{PublicationFailure.pointer_commit_failed.value}: {exc}"
                ) from None
            raise
        _fsync_directory(self.publication_root)
        self._published = True

        return PublishedPreparationRef(
            publication_root=self.publication_root,
            generation_id=generation_id,
            generation_path=destination,
            candidate_archive=destination / CANDIDATE_ARCHIVE_NAME,
            runtime_input=destination / RUNTIME_INPUT_NAME,
            prepare_attestation=destination / PREPARE_ATTESTATION_NAME,
            candidate_archive_file_sha256=self._staged[CANDIDATE_ARCHIVE_NAME],
            runtime_input_file_sha256=self._staged[RUNTIME_INPUT_NAME],
            prepare_attestation_file_sha256=self._staged[PREPARE_ATTESTATION_NAME],
        )

    def _adopt_existing(self, destination: Path) -> None:
        """Same id, existing directory: adopt byte-identical content, or refuse.

        Every staged artifact must already be in the existing generation with
        the same file hash.  Nothing is written into the existing directory in
        either case, and a refusal leaves it exactly as found — the colliding
        writer's staging is the only thing cleaned up, by the abort path.
        """

        for name, staged_sha in self._staged.items():
            try:
                existing_sha = _read_back_file_sha256(destination / name)
            except OSError:
                raise PublicationRefused(
                    f"{PublicationFailure.generation_collision.value}: {name} "
                    "is missing from the existing generation"
                ) from None
            if existing_sha != staged_sha:
                raise PublicationRefused(
                    f"{PublicationFailure.generation_collision.value}: {name} "
                    "differs from the existing generation"
                )
        shutil.rmtree(self._staging, ignore_errors=True)


__all__ = [
    "CANDIDATE_ARCHIVE_NAME",
    "CURRENT_POINTER_NAME",
    "GENERATIONS_DIRECTORY_NAME",
    "GENERATION_ARTIFACT_NAMES",
    "GenerationTransaction",
    "PREPARE_ATTESTATION_NAME",
    "PUBLICATION_POINTER_VERSION",
    "PublicationFailure",
    "PublicationPointer",
    "PublicationRefused",
    "PublishedPreparationRef",
    "RUNTIME_INPUT_NAME",
    "STAGING_DIRECTORY_PREFIX",
    "load_publication_pointer",
    "resolve_published_generation",
]
