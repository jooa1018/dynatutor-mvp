"""Bounded cache for validated-on-read structured mechanics drafts."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import threading
import time

from engine.mechanics.contracts import (
    CONTRACT_VERSION,
    DRAFT_SCHEMA_VERSION,
    IR_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
)
from engine.mechanics.modeler_config import MechanicsModelerConfig
from engine.mechanics.modeler_inputs import VerifiedModelerInput
from engine.mechanics.modeler_prompt import (
    MECHANICS_MODELER_PROMPT_VERSION,
    modeler_prompt_hash,
)
from engine.mechanics.modeler_repair import MECHANICS_REPAIR_POLICY_VERSION
from engine.mechanics.normalization import (
    NORMALIZATION_POLICY_VERSION,
    VALIDATION_POLICY_VERSION,
)


MECHANICS_MODELER_VERSION = "mechanics-modeler-v1"
MECHANICS_CACHE_FORMAT_VERSION = "mechanics-modeler-cache-v1"


@dataclass(frozen=True)
class MechanicsCacheCompatibilityVersions:
    """Stage-2-owned cache invalidation contract for downstream mechanics stages."""

    evidence: str = "mechanics-evidence-contract-v1"
    law: str = "mechanics-law-contract-v1"
    compiler: str = "mechanics-compiler-contract-v1"
    solver: str = "mechanics-solver-contract-v1"
    verification: str = "mechanics-verification-contract-v1"

    def __post_init__(self) -> None:
        for value in (
            self.evidence,
            self.law,
            self.compiler,
            self.solver,
            self.verification,
        ):
            if not isinstance(value, str) or not 1 <= len(value) <= 80:
                raise ValueError("cache compatibility version is invalid")


DEFAULT_MECHANICS_CACHE_COMPATIBILITY_VERSIONS = (
    MechanicsCacheCompatibilityVersions()
)


@dataclass(frozen=True)
class MechanicsCacheEntry:
    draft: MechanicsProblemDraftV1
    created_at: float


class CacheSecurityError(RuntimeError):
    """The configured L2 path cannot safely hold structured source drafts."""


_DEFAULT_CACHE_DIRECTORY = "dynatutor_mechanics_modeler_cache"
_DEFAULT_CACHE_FILENAME = "modeler.sqlite3"
_MAX_CACHE_PATH_LENGTH = 1_024


def _resolve_cache_path(path: str | os.PathLike[str] | None) -> tuple[Path, bool]:
    managed_parent = path is None
    if path is not None and not isinstance(path, (str, os.PathLike)):
        raise CacheSecurityError("cache path type is invalid")
    try:
        candidate = (
            Path(tempfile.gettempdir())
            / _DEFAULT_CACHE_DIRECTORY
            / _DEFAULT_CACHE_FILENAME
            if path is None
            else Path(path)
        )
    except (TypeError, ValueError, OSError) as exc:
        raise CacheSecurityError("cache path type is invalid") from exc
    if not str(candidate) or len(str(candidate)) > _MAX_CACHE_PATH_LENGTH:
        raise CacheSecurityError("cache path length is invalid")
    try:
        # Normalize ``..`` lexically without following links, then reject every
        # existing link/junction component before the final canonical resolve.
        absolute = Path(os.path.abspath(candidate))
        for component in (absolute, *absolute.parents):
            is_junction = getattr(component, "is_junction", lambda: False)
            if component.is_symlink() or (
                component.exists() and is_junction()
            ):
                raise CacheSecurityError(
                    "cache path cannot traverse a symbolic link or junction"
                )
        resolved = absolute.resolve(strict=False)
    except CacheSecurityError:
        raise
    except (OSError, RuntimeError) as exc:
        raise CacheSecurityError("cache path cannot be resolved") from exc
    if len(str(resolved)) > _MAX_CACHE_PATH_LENGTH:
        raise CacheSecurityError("resolved cache path length is invalid")
    if resolved == resolved.parent or not resolved.name or (
        resolved.exists() and not resolved.is_file()
    ):
        raise CacheSecurityError("cache path must name a file")
    return resolved, managed_parent


def build_modeler_cache_key(
    verified_input: VerifiedModelerInput,
    config: MechanicsModelerConfig,
    *,
    correction_revision: int,
    modeling_input_identity: str | None,
    compatibility_versions: MechanicsCacheCompatibilityVersions = (
        DEFAULT_MECHANICS_CACHE_COMPATIBILITY_VERSIONS
    ),
) -> str:
    selected_model = config.selected_model(has_images=bool(verified_input.images))
    image_identities = [
        {
            "asset_id": image.asset_id,
            "content_sha256": image.content_sha256,
            "media_type": image.media_type,
            "page_id": image.page_id,
            "page_number": image.page_number,
            "parent_asset_id": image.parent_asset_id,
        }
        for image in verified_input.images
    ]
    payload = {
        "normalized_text_sha256": verified_input.normalized_text_sha256,
        # Evidence offsets bind to exact source bytes, so normalized identity
        # alone is intentionally insufficient.
        "source_text_sha256": verified_input.source_text_sha256,
        "ordered_images": image_identities,
        "primary_model": config.model,
        "figure_model_override": config.figure_model,
        "selected_model": selected_model,
        "reasoning_effort": config.reasoning_effort,
        "max_output_tokens": config.max_output_tokens,
        "prompt_version": MECHANICS_MODELER_PROMPT_VERSION,
        "prompt_sha256": modeler_prompt_hash(),
        "contract_version": CONTRACT_VERSION,
        "draft_schema_version": DRAFT_SCHEMA_VERSION,
        "ir_schema_version": IR_SCHEMA_VERSION,
        "validation_policy_version": VALIDATION_POLICY_VERSION,
        "normalization_policy_version": NORMALIZATION_POLICY_VERSION,
        "repair_policy_version": MECHANICS_REPAIR_POLICY_VERSION,
        "cache_format_version": MECHANICS_CACHE_FORMAT_VERSION,
        "modeler_version": MECHANICS_MODELER_VERSION,
        "evidence_version": compatibility_versions.evidence,
        "law_version": compatibility_versions.law,
        "compiler_version": compatibility_versions.compiler,
        "solver_version": compatibility_versions.solver,
        "verification_version": compatibility_versions.verification,
        "correction_revision": correction_revision,
        "modeling_input_identity_sha256": (
            hashlib.sha256(modeling_input_identity.encode("utf-8")).hexdigest()
            if modeling_input_identity is not None
            else None
        ),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class MechanicsModelerCache:
    """TTL LRU plus bounded SQLite; cached drafts are parsed afresh on every read."""

    def __init__(
        self,
        *,
        path: str | os.PathLike[str] | None = None,
        ttl_seconds: int = 604_800,
        l1_entries: int = 256,
        l2_entries: int = 5_000,
        clock=time.time,
    ) -> None:
        self.path, self._managed_parent = _resolve_cache_path(path)
        self.ttl_seconds = ttl_seconds
        self.l1_entries = l1_entries
        self.l2_entries = l2_entries
        self._clock = clock
        self._l1: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = threading.RLock()
        self._initialized = False
        self._prepare_parent()

    def _prepare_parent(self) -> None:
        parent = self.path.parent
        try:
            if parent.exists():
                if parent.is_symlink() or not parent.is_dir():
                    raise CacheSecurityError("cache parent must be a real directory")
            else:
                parent.mkdir(parents=True, mode=0o700, exist_ok=False)
            if os.name == "posix":
                if self._managed_parent:
                    os.chmod(parent, 0o700)
                parent_metadata = parent.stat()
                mode = stat.S_IMODE(parent_metadata.st_mode)
                if mode & 0o077:
                    raise CacheSecurityError("cache parent permissions are not private")
                if hasattr(os, "geteuid") and parent_metadata.st_uid != os.geteuid():
                    raise CacheSecurityError("cache parent ownership is not private")
        except CacheSecurityError:
            raise
        except OSError as exc:
            raise CacheSecurityError("cache parent cannot be secured") from exc

    def _prepare_database_file(self) -> None:
        self._prepare_parent()
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags, 0o600)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    raise CacheSecurityError("cache database must be one regular file")
                if os.name == "posix":
                    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
                        raise CacheSecurityError("cache database ownership is not private")
                    os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
            for suffix in ("-journal", "-wal", "-shm"):
                auxiliary = Path(str(self.path) + suffix)
                if not auxiliary.exists():
                    continue
                if auxiliary.is_symlink() or not auxiliary.is_file():
                    raise CacheSecurityError("cache auxiliary path is unsafe")
                if os.name == "posix":
                    os.chmod(auxiliary, 0o600)
        except CacheSecurityError:
            raise
        except OSError as exc:
            raise CacheSecurityError("cache database cannot be secured") from exc

    def _connect(self) -> sqlite3.Connection:
        self._prepare_database_file()
        connection = sqlite3.connect(self.path, timeout=2.0)
        try:
            journal_mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()
            if journal_mode is None or str(journal_mode[0]).lower() != "delete":
                raise CacheSecurityError("cache journal mode is not private")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("PRAGMA busy_timeout=2000")
            if not self._initialized:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mechanics_modeler_cache (
                        cache_key TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
                connection.commit()
                self._initialized = True
            return connection
        except Exception:
            connection.close()
            raise

    @staticmethod
    def _decode(encoded: str, created_at: float) -> MechanicsCacheEntry:
        payload = json.loads(encoded)
        if payload.get("cache_format_version") != MECHANICS_CACHE_FORMAT_VERSION:
            raise ValueError("stale mechanics cache format")
        if set(payload) != {"cache_format_version", "draft"}:
            raise ValueError("mechanics cache payload has unexpected fields")
        draft = MechanicsProblemDraftV1.model_validate(payload["draft"])
        return MechanicsCacheEntry(draft=draft, created_at=created_at)

    def get(self, key: str) -> MechanicsCacheEntry | None:
        now = self._clock()
        with self._lock:
            cached = self._l1.get(key)
            if cached is not None:
                encoded, created_at = cached
                if now - created_at <= self.ttl_seconds:
                    try:
                        entry = self._decode(encoded, created_at)
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                        self._l1.pop(key, None)
                        self.delete(key)
                        return None
                    self._l1.move_to_end(key)
                    return entry
                self._l1.pop(key, None)
            try:
                with self._connect() as connection:
                    row = connection.execute(
                        "SELECT payload_json, created_at FROM mechanics_modeler_cache WHERE cache_key = ?",
                        (key,),
                    ).fetchone()
                    if row is None:
                        return None
                    created_at = float(row[1])
                    if now - created_at > self.ttl_seconds:
                        connection.execute(
                            "DELETE FROM mechanics_modeler_cache WHERE cache_key = ?",
                            (key,),
                        )
                        return None
                    entry = self._decode(str(row[0]), created_at)
                    encoded = str(row[0])
            except (
                OSError,
                CacheSecurityError,
                sqlite3.Error,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ):
                self.delete(key)
                return None
            self._put_l1(key, encoded, entry.created_at)
            return entry

    def put(self, key: str, draft: MechanicsProblemDraftV1) -> None:
        created_at = self._clock()
        encoded = json.dumps(
            {
                "cache_format_version": MECHANICS_CACHE_FORMAT_VERSION,
                "draft": draft.model_dump(mode="json"),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        # Decode what will be stored before mutating either tier.
        self._decode(encoded, created_at)
        with self._lock:
            self._put_l1(key, encoded, created_at)
            try:
                with self._connect() as connection:
                    connection.execute(
                        "INSERT OR REPLACE INTO mechanics_modeler_cache(cache_key, payload_json, created_at) VALUES (?, ?, ?)",
                        (key, encoded, created_at),
                    )
                    connection.execute(
                        "DELETE FROM mechanics_modeler_cache WHERE created_at < ?",
                        (created_at - self.ttl_seconds,),
                    )
                    connection.execute(
                        """
                        DELETE FROM mechanics_modeler_cache
                        WHERE cache_key IN (
                            SELECT cache_key FROM mechanics_modeler_cache
                            ORDER BY created_at DESC LIMIT -1 OFFSET ?
                        )
                        """,
                        (self.l2_entries,),
                    )
            except (OSError, sqlite3.Error, CacheSecurityError):
                # L2 is an optimization.  The bounded in-memory tier remains valid.
                return

    def delete(self, key: str) -> None:
        with self._lock:
            self._l1.pop(key, None)
            try:
                with self._connect() as connection:
                    connection.execute(
                        "DELETE FROM mechanics_modeler_cache WHERE cache_key = ?",
                        (key,),
                    )
            except (OSError, sqlite3.Error, CacheSecurityError):
                pass

    def _put_l1(self, key: str, encoded: str, created_at: float) -> None:
        self._l1[key] = (encoded, created_at)
        self._l1.move_to_end(key)
        while len(self._l1) > self.l1_entries:
            self._l1.popitem(last=False)


__all__ = [
    "CacheSecurityError",
    "DEFAULT_MECHANICS_CACHE_COMPATIBILITY_VERSIONS",
    "MECHANICS_CACHE_FORMAT_VERSION",
    "MECHANICS_MODELER_VERSION",
    "MechanicsCacheEntry",
    "MechanicsCacheCompatibilityVersions",
    "MechanicsModelerCache",
    "build_modeler_cache_key",
]
