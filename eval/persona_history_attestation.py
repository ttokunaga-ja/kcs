"""Read-only W0 runtime attestation primitives for persona-PC fixtures.

This module deliberately separates two different claims:

* :func:`walk_directory_content_root` proves only a bounded, stable subtree
  below an opened final directory (not trusted-root containment) using a
  directory-local hierarchical Merkle root; and
* :func:`build_runtime_directory_receipt` emits the exact nine-field callback
  receipt accepted by ``verify_history_prepare_envelope`` only after an
  explicit externally supplied KCS semantic checker succeeds, its typed result
  binds profile/person/scope/path/content root/chunk arithmetic, the tree is
  unchanged by it, and the descriptor is opened component-by-component from a
  canonical trusted-root file descriptor.

The generic walker does not understand SQLite, KCS commits, CAS objects, HEAD,
or device-registry semantics.  A content root must therefore never be called a
KCS semantic attestation by itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import itertools
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Callable, Iterable, Mapping
import unicodedata

try:  # Package imports and direct ``python eval/...`` execution.
    from . import generate_persona_corpus as generator
    from . import persona_fixture_spec as fixture_spec
except ImportError:  # pragma: no cover - retained for repository script style.
    import generate_persona_corpus as generator
    import persona_fixture_spec as fixture_spec


CONTENT_ROOT_SCHEMA = "kcs.persona.filesystem-content-root/v2"
PARTIAL_SCOPE_SCHEMA = "kcs.persona.w0.partial-scope-attestation/v1"
PARTIAL_PERSON_SCHEMA = "kcs.persona.w0.partial-person-attestation/v1"
SUITE_RECEIPT_SCHEMA = "kcs.persona.w0.suite-semantic-attestation/v1"
KCS_SEMANTIC_EVIDENCE_SCHEMA = "kcs.persona.kcs-semantic-evidence/v1"
FILESYSTEM_COVERAGE = "filesystem_structure_and_file_bytes_only"
EXPECTED_PERSONAS = 20
EXPECTED_SCOPES_PER_PERSON = 20
EXPECTED_SCOPE_STORES = EXPECTED_PERSONAS * EXPECTED_SCOPES_PER_PERSON
EXPECTED_DEVICE_STATES = EXPECTED_PERSONAS
MAX_SIGNED_COUNT = 2**63 - 1
HARD_MAX_ENTRIES = 250_000
HARD_MAX_DIRECT_ENTRIES = 16_384
HARD_MAX_FILES = 200_000
HARD_MAX_DIRECTORIES = 50_000
HARD_MAX_TOTAL_FILE_BYTES = 8 * 1024 * 1024 * 1024
HARD_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
HARD_MAX_DEPTH = 32
HARD_MAX_RELATIVE_PATH_BYTES = 4_096
HARD_MAX_COMPONENTS = 64
HARD_MAX_READ_SIZE = 16 * 1024 * 1024

_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_PERSONA_RE = re.compile(r"p[0-9]{2}")
_WINDOWS_FORBIDDEN = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED = frozenset(
    ("con", "prn", "aux", "nul")
    + tuple(f"com{index}" for index in range(1, 10))
    + tuple(f"lpt{index}" for index in range(1, 10))
)


class PersonaHistoryAttestationError(RuntimeError):
    """Raised when a read-only W0 attestation cannot be proven safely."""


def _is_digest(value: object) -> bool:
    return type(value) is str and _DIGEST_RE.fullmatch(value) is not None


@dataclass(frozen=True)
class AttestationLimits:
    """Hard resource bounds for one opaque runtime directory walk."""

    max_entries: int = HARD_MAX_ENTRIES
    max_direct_entries: int = HARD_MAX_DIRECT_ENTRIES
    max_files: int = HARD_MAX_FILES
    max_directories: int = HARD_MAX_DIRECTORIES
    max_total_file_bytes: int = HARD_MAX_TOTAL_FILE_BYTES
    max_file_bytes: int = HARD_MAX_FILE_BYTES
    max_depth: int = HARD_MAX_DEPTH
    max_relative_path_bytes: int = HARD_MAX_RELATIVE_PATH_BYTES
    max_components: int = HARD_MAX_COMPONENTS
    read_size: int = 1024 * 1024

    def __post_init__(self):
        values = {
            "max_entries": self.max_entries,
            "max_direct_entries": self.max_direct_entries,
            "max_files": self.max_files,
            "max_directories": self.max_directories,
            "max_total_file_bytes": self.max_total_file_bytes,
            "max_file_bytes": self.max_file_bytes,
            "max_depth": self.max_depth,
            "max_relative_path_bytes": self.max_relative_path_bytes,
            "max_components": self.max_components,
            "read_size": self.read_size,
        }
        for label, value in values.items():
            if type(value) is not int or value <= 0 or value > MAX_SIGNED_COUNT:
                raise PersonaHistoryAttestationError(
                    f"{label} must be a positive bounded integer"
                )
        if self.max_files > self.max_entries:
            raise PersonaHistoryAttestationError(
                "max_files cannot exceed max_entries"
            )
        if self.max_directories > self.max_entries:
            raise PersonaHistoryAttestationError(
                "max_directories cannot exceed max_entries"
            )
        if self.max_file_bytes > self.max_total_file_bytes:
            raise PersonaHistoryAttestationError(
                "max_file_bytes cannot exceed max_total_file_bytes"
            )
        if not 512 <= self.read_size <= 16 * 1024 * 1024:
            raise PersonaHistoryAttestationError(
                "read_size must be between 512 bytes and 16 MiB"
            )
        hard_caps = {
            "max_entries": HARD_MAX_ENTRIES,
            "max_direct_entries": HARD_MAX_DIRECT_ENTRIES,
            "max_files": HARD_MAX_FILES,
            "max_directories": HARD_MAX_DIRECTORIES,
            "max_total_file_bytes": HARD_MAX_TOTAL_FILE_BYTES,
            "max_file_bytes": HARD_MAX_FILE_BYTES,
            "max_depth": HARD_MAX_DEPTH,
            "max_relative_path_bytes": HARD_MAX_RELATIVE_PATH_BYTES,
            "max_components": HARD_MAX_COMPONENTS,
            "read_size": HARD_MAX_READ_SIZE,
        }
        for label, hard_cap in hard_caps.items():
            if getattr(self, label) > hard_cap:
                raise PersonaHistoryAttestationError(
                    f"{label} exceeds the attestor hard cap {hard_cap}"
                )


DEFAULT_LIMITS = AttestationLimits()


@dataclass(frozen=True)
class DirectoryContentRoot:
    """A filesystem-only snapshot; it makes no KCS semantic claim."""

    schema: str
    schema_version: int
    coverage: str
    directory_device: int
    directory_inode: int
    directory_nlink: int
    descendant_directories: int
    regular_files: int
    total_file_bytes: int
    maximum_depth: int
    content_root_sha256: str

    def __post_init__(self):
        if (
            self.schema != CONTENT_ROOT_SCHEMA
            or type(self.schema_version) is not int
            or self.schema_version != 2
            or self.coverage != FILESYSTEM_COVERAGE
            or type(self.directory_device) is not int
            or type(self.directory_inode) is not int
            or type(self.directory_nlink) is not int
            or type(self.descendant_directories) is not int
            or type(self.regular_files) is not int
            or type(self.total_file_bytes) is not int
            or type(self.maximum_depth) is not int
            or min(
                self.directory_device,
                self.directory_inode,
                self.directory_nlink,
                self.descendant_directories,
                self.regular_files,
                self.total_file_bytes,
                self.maximum_depth,
            )
            < 0
            or not _is_digest(self.content_root_sha256)
        ):
            raise PersonaHistoryAttestationError(
                "directory content-root receipt is invalid"
            )


@dataclass(frozen=True)
class KcsSemanticEvidence:
    """Externally supplied KCS result bound to one observed runtime snapshot."""

    schema: str
    schema_version: int
    kind: str
    attestor_schema: str
    profile: str
    persona_id: str
    scope_key: str | None
    relative_path: str
    content_root_sha256: str
    chunk_arithmetic: ChunkArithmetic | None
    semantics_attested: bool

    def __post_init__(self):
        expected = _attestor_schema_for_kind(self.kind)
        _validate_persona_id(self.persona_id)
        _validate_relative_runtime_path(self.relative_path, self.kind)
        if (
            self.schema != KCS_SEMANTIC_EVIDENCE_SCHEMA
            or type(self.schema_version) is not int
            or self.schema_version != 1
            or self.attestor_schema != expected
            or self.profile not in ("tiny", "pilot", "full")
            or not _is_digest(self.content_root_sha256)
            or self.semantics_attested is not True
        ):
            raise PersonaHistoryAttestationError(
                "KCS semantic evidence is absent or incompatible"
            )
        if self.kind == "scope_store":
            if (
                type(self.scope_key) is not str
                or not self.scope_key
                or type(self.chunk_arithmetic) is not ChunkArithmetic
            ):
                raise PersonaHistoryAttestationError(
                    "scope semantic evidence lacks bound identity/arithmetic"
                )
        elif self.scope_key is not None or self.chunk_arithmetic is not None:
            raise PersonaHistoryAttestationError(
                "device semantic evidence must not claim scope arithmetic"
            )
        _validate_canonical_semantic_evidence(self)


@dataclass(frozen=True)
class RuntimeDirectoryReceipt:
    """Exact callback receipt consumed by the history-prepare envelope."""

    schema: str
    schema_version: int
    kind: str
    relative_path: str
    directory_device: int
    directory_inode: int
    directory_nlink: int
    attestor_schema: str
    content_root_sha256: str
    semantic_evidence: KcsSemanticEvidence

    def __post_init__(self):
        expected_schema = _attestor_schema_for_kind(self.kind)
        _validate_relative_runtime_path(self.relative_path, self.kind)
        if (
            self.schema != generator.RUNTIME_DIRECTORY_ATTESTATION_SCHEMA
            or type(self.schema_version) is not int
            or self.schema_version != 1
            or type(self.directory_device) is not int
            or type(self.directory_inode) is not int
            or type(self.directory_nlink) is not int
            or min(
                self.directory_device,
                self.directory_inode,
                self.directory_nlink,
            )
            < 0
            or self.attestor_schema != expected_schema
            or not _is_digest(self.content_root_sha256)
            or type(self.semantic_evidence) is not KcsSemanticEvidence
            or self.semantic_evidence.kind != self.kind
            or self.semantic_evidence.relative_path != self.relative_path
            or self.semantic_evidence.attestor_schema != self.attestor_schema
            or self.semantic_evidence.content_root_sha256
            != self.content_root_sha256
        ):
            raise PersonaHistoryAttestationError(
                "runtime directory callback receipt is invalid"
            )

    def to_callback_dict(self) -> dict[str, object]:
        """Return exactly the nine primitive fields required by the callback."""
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "kind": self.kind,
            "relative_path": self.relative_path,
            "directory_device": self.directory_device,
            "directory_inode": self.directory_inode,
            "directory_nlink": self.directory_nlink,
            "attestor_schema": self.attestor_schema,
            "content_root_sha256": self.content_root_sha256,
        }


@dataclass(frozen=True)
class ChunkArithmetic:
    """Validated observed W0 current-chunk category arithmetic."""

    expected_contract_contributor_chunks: int
    contract_contributor_chunks: int
    incidental_searchable_chunks: int
    raw_only_chunks: int
    all_current_eligible_chunks: int

    def __post_init__(self):
        values = {
            "expected_contract_contributor_chunks": (
                self.expected_contract_contributor_chunks
            ),
            "contract_contributor_chunks": self.contract_contributor_chunks,
            "incidental_searchable_chunks": self.incidental_searchable_chunks,
            "raw_only_chunks": self.raw_only_chunks,
            "all_current_eligible_chunks": self.all_current_eligible_chunks,
        }
        for label, value in values.items():
            _require_count(value, label)
        if self.contract_contributor_chunks != self.expected_contract_contributor_chunks:
            raise PersonaHistoryAttestationError(
                "contract contributor chunks differ from the expected target"
            )
        if self.raw_only_chunks != 0:
            raise PersonaHistoryAttestationError(
                "raw-only sources contributed searchable chunks"
            )
        if self.all_current_eligible_chunks != (
            self.contract_contributor_chunks + self.incidental_searchable_chunks
        ):
            raise PersonaHistoryAttestationError(
                "all-current eligible arithmetic does not equal contributor plus incidental"
            )


@dataclass(frozen=True)
class PartialScopeReceipt:
    """One scope observation; by construction it is never history-ready."""

    schema: str
    schema_version: int
    profile: str
    persona_id: str
    scope_key: str
    relative_path: str
    directory_content: DirectoryContentRoot
    chunk_arithmetic: ChunkArithmetic
    runtime_callback_receipt: RuntimeDirectoryReceipt | None = None
    history_ready_attested: bool = field(default=False, init=False)

    def __post_init__(self):
        _validate_persona_id(self.persona_id)
        if (
            self.schema != PARTIAL_SCOPE_SCHEMA
            or type(self.schema_version) is not int
            or self.schema_version != 1
            or self.profile not in ("tiny", "pilot", "full")
            or type(self.scope_key) is not str
            or not self.scope_key
            or type(self.directory_content) is not DirectoryContentRoot
            or type(self.chunk_arithmetic) is not ChunkArithmetic
            or (
                self.runtime_callback_receipt is not None
                and type(self.runtime_callback_receipt)
                is not RuntimeDirectoryReceipt
            )
        ):
            raise PersonaHistoryAttestationError("partial scope receipt is invalid")
        _validate_relative_runtime_path(self.relative_path, "scope_store")
        runtime = self.runtime_callback_receipt
        if runtime is not None:
            evidence = runtime.semantic_evidence
            if (
                runtime.kind != "scope_store"
                or runtime.relative_path != self.relative_path
                or evidence.profile != self.profile
                or evidence.persona_id != self.persona_id
                or evidence.scope_key != self.scope_key
                or evidence.chunk_arithmetic != self.chunk_arithmetic
                or (
                    runtime.directory_device,
                    runtime.directory_inode,
                    runtime.directory_nlink,
                    runtime.content_root_sha256,
                )
                != (
                    self.directory_content.directory_device,
                    self.directory_content.directory_inode,
                    self.directory_content.directory_nlink,
                    self.directory_content.content_root_sha256,
                )
            ):
                raise PersonaHistoryAttestationError(
                    "scope semantic/runtime receipt differs from its bound snapshot"
                )

    @property
    def kcs_semantics_attested(self) -> bool:
        return self.runtime_callback_receipt is not None


@dataclass(frozen=True)
class PartialPersonReceipt:
    """One device plus zero or more scopes; never a suite readiness claim."""

    schema: str
    schema_version: int
    profile: str
    persona_id: str
    expected_contract_contributor_chunks: int
    device_relative_path: str
    device_content: DirectoryContentRoot
    scopes: tuple[PartialScopeReceipt, ...]
    device_runtime_callback_receipt: RuntimeDirectoryReceipt | None = None
    history_ready_attested: bool = field(default=False, init=False)

    def __post_init__(self):
        _validate_persona_id(self.persona_id)
        if (
            self.schema != PARTIAL_PERSON_SCHEMA
            or type(self.schema_version) is not int
            or self.schema_version != 1
            or self.profile not in ("tiny", "pilot", "full")
            or type(self.device_content) is not DirectoryContentRoot
            or (
                self.device_runtime_callback_receipt is not None
                and type(self.device_runtime_callback_receipt)
                is not RuntimeDirectoryReceipt
            )
        ):
            raise PersonaHistoryAttestationError("partial person receipt is invalid")
        _require_count(
            self.expected_contract_contributor_chunks,
            "expected_contract_contributor_chunks",
        )
        _validate_relative_runtime_path(self.device_relative_path, "device_state")
        if type(self.scopes) is not tuple or len(self.scopes) > EXPECTED_SCOPES_PER_PERSON:
            raise PersonaHistoryAttestationError(
                "partial person contains too many or non-tuple scope receipts"
            )
        scope_keys = set()
        relative_paths = set()
        for scope in self.scopes:
            if (
                type(scope) is not PartialScopeReceipt
                or scope.persona_id != self.persona_id
                or scope.profile != self.profile
            ):
                raise PersonaHistoryAttestationError(
                    "partial person contains a foreign scope receipt"
                )
            if scope.scope_key in scope_keys or scope.relative_path in relative_paths:
                raise PersonaHistoryAttestationError(
                    "partial person contains duplicate scope identity"
                )
            scope_keys.add(scope.scope_key)
            relative_paths.add(scope.relative_path)
        runtime = self.device_runtime_callback_receipt
        if runtime is not None:
            evidence = runtime.semantic_evidence
            if (
                runtime.kind != "device_state"
                or runtime.relative_path != self.device_relative_path
                or evidence.profile != self.profile
                or evidence.persona_id != self.persona_id
                or (
                    runtime.directory_device,
                    runtime.directory_inode,
                    runtime.directory_nlink,
                    runtime.content_root_sha256,
                )
                != (
                    self.device_content.directory_device,
                    self.device_content.directory_inode,
                    self.device_content.directory_nlink,
                    self.device_content.content_root_sha256,
                )
            ):
                raise PersonaHistoryAttestationError(
                    "device semantic/runtime receipt differs from its bound snapshot"
                )

    @property
    def scope_coverage_complete(self) -> bool:
        return len(self.scopes) == EXPECTED_SCOPES_PER_PERSON

    @property
    def chunk_arithmetic_complete(self) -> bool:
        return self.scope_coverage_complete and sum(
            scope.chunk_arithmetic.contract_contributor_chunks
            for scope in self.scopes
        ) == self.expected_contract_contributor_chunks

    @property
    def kcs_semantics_attested(self) -> bool:
        return (
            self.device_runtime_callback_receipt is not None
            and self.scope_coverage_complete
            and all(scope.kcs_semantics_attested for scope in self.scopes)
        )


@dataclass(frozen=True)
class SuiteAttestationReceipt:
    """Root-independent W0 coverage projection, never history readiness.

    ``semantic_coverage_attested`` means only that all 420 externally supplied,
    identity-bound callback results are represented.  It is not this module's
    own SQLite/CAS/KCS semantic conclusion.
    """

    schema: str
    schema_version: int
    profile: str
    personas: int
    scope_stores: int
    device_states: int
    expected_contract_contributor_chunks: int
    contract_contributor_chunks: int
    incidental_searchable_chunks: int
    raw_only_chunks: int
    all_current_eligible_chunks: int
    filesystem_coverage_complete: bool
    kcs_semantics_callback_attested: bool
    semantic_coverage_attested: bool
    history_ready_attested: bool
    persona_plan_root_sha256: str
    event_projection_root_sha256: str
    projection_root_sha256: str

    def __post_init__(self):
        if (
            self.schema != SUITE_RECEIPT_SCHEMA
            or type(self.schema_version) is not int
            or self.schema_version != 1
            or self.profile not in ("tiny", "pilot", "full")
            or not _is_digest(self.persona_plan_root_sha256)
            or not _is_digest(self.event_projection_root_sha256)
            or not _is_digest(self.projection_root_sha256)
        ):
            raise PersonaHistoryAttestationError("suite receipt header is invalid")
        for label in (
            "personas",
            "scope_stores",
            "device_states",
            "expected_contract_contributor_chunks",
            "contract_contributor_chunks",
            "incidental_searchable_chunks",
            "raw_only_chunks",
            "all_current_eligible_chunks",
        ):
            _require_count(getattr(self, label), label)
        for label in (
            "filesystem_coverage_complete",
            "kcs_semantics_callback_attested",
            "semantic_coverage_attested",
            "history_ready_attested",
        ):
            if type(getattr(self, label)) is not bool:
                raise PersonaHistoryAttestationError(
                    f"suite {label} must be a bool"
                )
        if self.raw_only_chunks != 0 or self.all_current_eligible_chunks != (
            self.contract_contributor_chunks + self.incidental_searchable_chunks
        ):
            raise PersonaHistoryAttestationError(
                "suite chunk category arithmetic is invalid"
            )
        if self.filesystem_coverage_complete and (
            self.personas,
            self.scope_stores,
            self.device_states,
        ) != (
            EXPECTED_PERSONAS,
            EXPECTED_SCOPE_STORES,
            EXPECTED_DEVICE_STATES,
        ):
            raise PersonaHistoryAttestationError(
                "complete filesystem coverage requires exactly 20/400/20"
            )
        if self.history_ready_attested:
            raise PersonaHistoryAttestationError(
                "this structural/callback substrate cannot attest history readiness"
            )
        if self.kcs_semantics_callback_attested or self.semantic_coverage_attested:
            if (
                not self.filesystem_coverage_complete
                or not self.kcs_semantics_callback_attested
                or not self.semantic_coverage_attested
                or self.expected_contract_contributor_chunks
                != self.contract_contributor_chunks
            ):
                raise PersonaHistoryAttestationError(
                    "suite semantic/history readiness prerequisites are incomplete"
                )


def _attestor_schema_for_kind(kind: str) -> str:
    if kind == "scope_store":
        return generator.RUNTIME_SCOPE_STORE_SEMANTIC_CONTRACT
    if kind == "device_state":
        return generator.RUNTIME_DEVICE_STATE_SEMANTIC_CONTRACT
    raise PersonaHistoryAttestationError(f"unknown runtime kind: {kind!r}")


def _require_count(value: object, label: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SIGNED_COUNT:
        raise PersonaHistoryAttestationError(
            f"{label} must be a non-negative bounded integer"
        )
    return value


def _bounded_tuple(values: Iterable[object], maximum: int, label: str) -> tuple:
    try:
        iterator = iter(values)
    except TypeError as error:
        raise PersonaHistoryAttestationError(f"{label} must be iterable") from error
    bounded = tuple(itertools.islice(iterator, maximum + 1))
    if len(bounded) > maximum:
        raise PersonaHistoryAttestationError(
            f"{label} exceeds its {maximum}-item bound"
        )
    return bounded


def _validate_persona_id(value: object) -> str:
    if type(value) is not str or _PERSONA_RE.fullmatch(value) is None:
        raise PersonaHistoryAttestationError("persona_id must match pNN")
    return value


def _validate_portable_component(value: str, label: str) -> None:
    try:
        encoded = value.encode("utf-8")
    except (AttributeError, UnicodeEncodeError) as error:
        raise PersonaHistoryAttestationError(
            f"{label} is not canonical UTF-8"
        ) from error
    if (
        not value
        or value in (".", "..")
        or unicodedata.normalize("NFC", value) != value
        or len(encoded) > 255
        or value.endswith((".", " "))
        or any(character in _WINDOWS_FORBIDDEN for character in value)
        or any(
            unicodedata.category(character) in ("Cc", "Cf")
            for character in value
        )
        or value.split(".", 1)[0].casefold() in _WINDOWS_RESERVED
    ):
        raise PersonaHistoryAttestationError(
            f"{label} is not a canonical portable path component"
        )


def _validate_relative_runtime_path(value: object, kind: str) -> str:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        raise PersonaHistoryAttestationError("runtime relative_path is invalid")
    if unicodedata.normalize("NFC", value) != value:
        raise PersonaHistoryAttestationError("runtime relative_path must be NFC")
    path = PurePosixPath(value)
    if str(path) != value or len(value.encode("utf-8")) > 4_096:
        raise PersonaHistoryAttestationError("runtime relative_path is not canonical")
    for index, component in enumerate(path.parts):
        _validate_portable_component(component, f"relative_path[{index}]")
    expected_name = (
        generator.SCOPE_STORE_DIRECTORY_NAME
        if kind == "scope_store"
        else generator.DEVICE_STATE_DIRECTORY_NAME
        if kind == "device_state"
        else None
    )
    if expected_name is None:
        _attestor_schema_for_kind(kind)
    if path.name != expected_name:
        raise PersonaHistoryAttestationError(
            f"{kind} relative_path must end in {expected_name}"
        )
    return value


def _validate_canonical_semantic_evidence(
    evidence: KcsSemanticEvidence,
) -> None:
    try:
        persona = fixture_spec.get_persona(evidence.persona_id)
    except KeyError as error:
        raise PersonaHistoryAttestationError(
            "semantic evidence refers to an unknown persona"
        ) from error
    device_slug = f"{persona['id']}-{persona['role']}"
    if evidence.kind == "device_state":
        expected_path = (
            f"devices/{device_slug}/{generator.DEVICE_STATE_DIRECTORY_NAME}"
        )
        if evidence.relative_path != expected_path:
            raise PersonaHistoryAttestationError(
                "device semantic evidence path differs from the canonical persona"
            )
        return
    scope_map = {
        scope["scope_key"]: scope
        for scope in fixture_spec.scope_specs(persona)
    }
    scope = scope_map.get(evidence.scope_key)
    if scope is None:
        raise PersonaHistoryAttestationError(
            "scope semantic evidence refers to a non-canonical scope"
        )
    expected_path = (
        f"devices/{device_slug}/home/{scope['relative_path']}/"
        f"{generator.SCOPE_STORE_DIRECTORY_NAME}"
    )
    try:
        target = fixture_spec.scope_contributor_chunk_targets(
            persona, evidence.profile
        )[evidence.scope_key]
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise PersonaHistoryAttestationError(
            "semantic evidence profile/scope target is invalid"
        ) from error
    arithmetic = evidence.chunk_arithmetic
    if (
        evidence.relative_path != expected_path
        or arithmetic.expected_contract_contributor_chunks != target
        or arithmetic.contract_contributor_chunks != target
    ):
        raise PersonaHistoryAttestationError(
            "scope semantic evidence path/arithmetic differs from the canonical plan"
        )


def _stable_metadata(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        getattr(metadata, "st_mtime_ns", int(metadata.st_mtime * 1_000_000_000)),
        getattr(metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000)),
    )


def _required_open_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int or value == 0:
        raise PersonaHistoryAttestationError(
            f"required safe-open flag is unavailable: {name}"
        )
    return value


def _open_flags(*, directory: bool) -> int:
    flags = os.O_RDONLY
    flags |= _required_open_flag("O_CLOEXEC")
    flags |= _required_open_flag("O_NOFOLLOW")
    if directory:
        flags |= _required_open_flag("O_DIRECTORY")
    else:
        # A same-user race must not turn a regular-file open into a blocking
        # FIFO/device open before the post-open fstat rejects the new type.
        flags |= _required_open_flag("O_NONBLOCK")
    return flags


def _require_noninheritable(descriptor: int, label: str) -> None:
    try:
        inheritable = os.get_inheritable(descriptor)
    except OSError as error:
        raise PersonaHistoryAttestationError(
            f"cannot confirm close-on-exec for {label}"
        ) from error
    if inheritable:
        raise PersonaHistoryAttestationError(
            f"close-on-exec was not applied to {label}"
        )


def _open_root_directory(path: Path) -> tuple[int, os.stat_result]:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISDIR(before.st_mode):
            raise PersonaHistoryAttestationError(
                "runtime root must be a plain non-link directory"
            )
        descriptor = os.open(path, _open_flags(directory=True))
    except PersonaHistoryAttestationError:
        raise
    except OSError as error:
        raise PersonaHistoryAttestationError(
            f"cannot open runtime root safely: {path}"
        ) from error
    try:
        _require_noninheritable(descriptor, "runtime root")
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode) or (
            opened.st_dev,
            opened.st_ino,
        ) != (before.st_dev, before.st_ino):
            raise PersonaHistoryAttestationError(
                "runtime root changed while opening"
            )
    except PersonaHistoryAttestationError:
        os.close(descriptor)
        raise
    except OSError as error:
        os.close(descriptor)
        raise PersonaHistoryAttestationError(
            "cannot identity-bind the opened runtime root"
        ) from error
    return descriptor, opened


def _require_handle_platform() -> None:
    if os.name == "nt":
        raise PersonaHistoryAttestationError(
            "handle-relative runtime attestation is not implemented on Windows"
        )
    if (
        os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.stat not in os.supports_follow_symlinks
    ):
        raise PersonaHistoryAttestationError(
            "required handle-relative no-follow filesystem APIs are unavailable"
        )


def _read_regular_file(
    parent_fd: int,
    name: str,
    expected: os.stat_result,
    limits: AttestationLimits,
) -> tuple[int, str]:
    if expected.st_nlink != 1:
        raise PersonaHistoryAttestationError(
            "runtime regular files must have exactly one link"
        )
    if expected.st_size < 0 or expected.st_size > limits.max_file_bytes:
        raise PersonaHistoryAttestationError(
            "runtime file exceeds its per-file byte bound"
        )
    try:
        descriptor = os.open(
            name,
            _open_flags(directory=False),
            dir_fd=parent_fd,
        )
    except OSError as error:
        raise PersonaHistoryAttestationError(
            f"cannot open runtime file safely: {name}"
        ) from error
    digest = hashlib.sha256()
    total = 0
    try:
        _require_noninheritable(descriptor, "runtime file")
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or _stable_metadata(opened) != _stable_metadata(expected)
        ):
            raise PersonaHistoryAttestationError(
                "runtime file changed while opening"
            )
        while True:
            block = os.read(descriptor, limits.read_size)
            if not block:
                break
            total += len(block)
            if total > expected.st_size or total > limits.max_file_bytes:
                raise PersonaHistoryAttestationError(
                    "runtime file grew while reading"
                )
            digest.update(block)
        after = os.fstat(descriptor)
        if total != expected.st_size or _stable_metadata(after) != _stable_metadata(opened):
            raise PersonaHistoryAttestationError(
                "runtime file changed while reading"
            )
        namespace = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _stable_metadata(namespace) != _stable_metadata(after):
            raise PersonaHistoryAttestationError(
                "runtime file namespace changed while reading"
            )
        return total, digest.hexdigest()
    finally:
        os.close(descriptor)


def _directory_merkle(
    children: list[tuple[bytes, bytes, int, bytes]],
) -> str:
    """Hash one directory's bounded direct children without a global tree."""
    children.sort(key=lambda row: row[0])
    digest = hashlib.sha256()
    digest.update(b"kcs.persona.filesystem-directory-merkle/v2\x00")
    digest.update(len(children).to_bytes(8, "big"))
    for name, kind, size, child_digest in children:
        digest.update(kind)
        digest.update(len(name).to_bytes(2, "big"))
        digest.update(name)
        if kind == b"F":
            digest.update(size.to_bytes(8, "big"))
        digest.update(child_digest)
    return digest.hexdigest()


def _walk_directory_fd(
    root_fd: int,
    root_metadata: os.stat_result,
    limits: AttestationLimits,
) -> DirectoryContentRoot:
    """Walk an already identity-bound directory descriptor."""
    seen_inodes: set[tuple[int, int]] = {
        (root_metadata.st_dev, root_metadata.st_ino)
    }
    counts = {
        "entries": 0,
        "files": 0,
        "directories": 0,
        "bytes": 0,
        "maximum_depth": 0,
    }

    def visit(
        directory_fd: int,
        depth: int,
        relative_path_bytes: int,
    ) -> str:
        directory_before = os.fstat(directory_fd)
        children: list[tuple[bytes, bytes, int, bytes]] = []
        # Retain a fixed-width, deterministic token rather than an expanded
        # Unicode casefold string.  Equal casefolds always collide; a SHA-256
        # collision between unequal casefolds also rejects fail-closed.
        folded_names: set[bytes] = set()
        direct_entries = 0
        try:
            iterator = os.scandir(directory_fd)
        except OSError as error:
            raise PersonaHistoryAttestationError(
                "cannot scan runtime directory"
            ) from error
        with iterator:
            for entry in iterator:
                name = entry.name
                direct_entries += 1
                if direct_entries > limits.max_direct_entries:
                    raise PersonaHistoryAttestationError(
                        "runtime directory exceeds its direct-entry bound"
                    )
                _validate_portable_component(name, "runtime entry")
                folded_name = hashlib.sha256(
                    b"kcs.persona.portable-casefold/v1\x00"
                    + name.casefold().encode("utf-8")
                ).digest()
                if folded_name in folded_names:
                    raise PersonaHistoryAttestationError(
                        "runtime directory has a case-insensitive name collision"
                    )
                folded_names.add(folded_name)
                name_bytes = name.encode("utf-8")
                child_depth = depth + 1
                child_path_bytes = (
                    relative_path_bytes
                    + (1 if relative_path_bytes else 0)
                    + len(name_bytes)
                )
                if (
                    child_depth > limits.max_depth
                    or child_depth > limits.max_components
                    or child_path_bytes > limits.max_relative_path_bytes
                ):
                    raise PersonaHistoryAttestationError(
                        "runtime tree exceeds its canonical path bound"
                    )
                counts["entries"] += 1
                if counts["entries"] > limits.max_entries:
                    raise PersonaHistoryAttestationError(
                        "runtime tree exceeds its entry bound"
                    )
                try:
                    metadata = os.stat(
                        name,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except OSError as error:
                    raise PersonaHistoryAttestationError(
                        f"cannot stat runtime entry safely: {name}"
                    ) from error
                if metadata.st_dev != root_metadata.st_dev:
                    raise PersonaHistoryAttestationError(
                        f"runtime entry crosses a filesystem boundary: {name}"
                    )
                inode = (metadata.st_dev, metadata.st_ino)
                if inode in seen_inodes:
                    raise PersonaHistoryAttestationError(
                        f"runtime inode is reused: {name}"
                    )
                seen_inodes.add(inode)
                if stat.S_ISDIR(metadata.st_mode):
                    counts["directories"] += 1
                    if counts["directories"] > limits.max_directories:
                        raise PersonaHistoryAttestationError(
                            "runtime tree exceeds its directory bound"
                        )
                    try:
                        child_fd = os.open(
                            name,
                            _open_flags(directory=True),
                            dir_fd=directory_fd,
                        )
                    except OSError as error:
                        raise PersonaHistoryAttestationError(
                            f"cannot open runtime directory safely: {name}"
                        ) from error
                    try:
                        _require_noninheritable(child_fd, "runtime directory")
                        opened = os.fstat(child_fd)
                        if (
                            not stat.S_ISDIR(opened.st_mode)
                            or _stable_metadata(opened) != _stable_metadata(metadata)
                        ):
                            raise PersonaHistoryAttestationError(
                                f"runtime directory changed while opening: {name}"
                            )
                        child_root = visit(
                            child_fd,
                            child_depth,
                            child_path_bytes,
                        )
                        after = os.fstat(child_fd)
                        namespace = os.stat(
                            name,
                            dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                        if (
                            _stable_metadata(after) != _stable_metadata(opened)
                            or _stable_metadata(namespace) != _stable_metadata(after)
                        ):
                            raise PersonaHistoryAttestationError(
                                f"runtime directory changed while scanning: {name}"
                            )
                    finally:
                        os.close(child_fd)
                    children.append((
                        name_bytes,
                        b"D",
                        0,
                        bytes.fromhex(child_root),
                    ))
                elif stat.S_ISREG(metadata.st_mode):
                    counts["files"] += 1
                    if counts["files"] > limits.max_files:
                        raise PersonaHistoryAttestationError(
                            "runtime tree exceeds its file bound"
                        )
                    if metadata.st_nlink != 1:
                        raise PersonaHistoryAttestationError(
                            f"runtime file is hard-linked: {name}"
                        )
                    if counts["bytes"] + metadata.st_size > limits.max_total_file_bytes:
                        raise PersonaHistoryAttestationError(
                            "runtime tree exceeds its total byte bound"
                        )
                    size, raw_sha256 = _read_regular_file(
                        directory_fd,
                        name,
                        metadata,
                        limits,
                    )
                    counts["bytes"] += size
                    children.append((
                        name_bytes,
                        b"F",
                        size,
                        bytes.fromhex(raw_sha256),
                    ))
                else:
                    raise PersonaHistoryAttestationError(
                        f"runtime entry is a link/reparse/special: {name}"
                    )
                counts["maximum_depth"] = max(
                    counts["maximum_depth"], child_depth
                )
        directory_after = os.fstat(directory_fd)
        if _stable_metadata(directory_after) != _stable_metadata(directory_before):
            raise PersonaHistoryAttestationError(
                "runtime directory changed during traversal"
            )
        return _directory_merkle(children)

    root_digest = visit(root_fd, 0, 0)
    return DirectoryContentRoot(
        schema=CONTENT_ROOT_SCHEMA,
        schema_version=2,
        coverage=FILESYSTEM_COVERAGE,
        directory_device=root_metadata.st_dev,
        directory_inode=root_metadata.st_ino,
        directory_nlink=root_metadata.st_nlink,
        descendant_directories=counts["directories"],
        regular_files=counts["files"],
        total_file_bytes=counts["bytes"],
        maximum_depth=counts["maximum_depth"],
        content_root_sha256=root_digest,
    )


def walk_directory_content_root(
    path: os.PathLike[str] | str,
    *,
    limits: AttestationLimits = DEFAULT_LIMITS,
) -> DirectoryContentRoot:
    """Return a bounded stable content root without following any child link.

    The digest is a domain-separated hierarchical Merkle root.  Each directory
    sorts only its direct UTF-8 child names and incrementally hashes typed child
    descriptors; no global record/path list or whole-tree JSON is materialized.
    It excludes the absolute root, device/inode identities, permissions, and
    timestamps, so equivalent trees at different safe roots have the same
    digest.  This generic entry point binds the final root component and all
    descendants; formal callback containment additionally requires the
    trusted-root entry point below.
    """
    _require_handle_platform()
    if type(limits) is not AttestationLimits:
        raise PersonaHistoryAttestationError("limits must be AttestationLimits")
    root = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    root_fd, root_metadata = _open_root_directory(root)
    try:
        result = _walk_directory_fd(root_fd, root_metadata, limits)
        final_metadata = os.fstat(root_fd)
        try:
            namespace_metadata = root.lstat()
        except OSError as error:
            raise PersonaHistoryAttestationError(
                "runtime root namespace disappeared during traversal"
            ) from error
        if (
            root.is_symlink()
            or _stable_metadata(final_metadata) != _stable_metadata(root_metadata)
            or _stable_metadata(namespace_metadata) != _stable_metadata(final_metadata)
        ):
            raise PersonaHistoryAttestationError(
                "runtime root changed during traversal"
            )
        return result
    finally:
        os.close(root_fd)


def _canonical_existing_absolute_directory(
    path: os.PathLike[str] | str,
    label: str,
) -> Path:
    raw = os.fspath(path)
    if type(raw) is not str:
        raise PersonaHistoryAttestationError(f"{label} must be a text path")
    candidate = Path(raw)
    if not candidate.is_absolute() or str(candidate) != raw:
        raise PersonaHistoryAttestationError(
            f"{label} must be a canonical absolute path"
        )
    try:
        resolved = candidate.resolve(strict=True)
        metadata = candidate.lstat()
    except (OSError, RuntimeError) as error:
        raise PersonaHistoryAttestationError(
            f"{label} cannot be resolved safely"
        ) from error
    if (
        resolved != candidate
        or candidate.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise PersonaHistoryAttestationError(
            f"{label} or one of its ancestors is a link/non-directory"
        )
    return candidate


def _open_relative_directory(
    trusted_fd: int,
    parts: tuple[str, ...],
    trusted_device: int,
) -> tuple[int, os.stat_result]:
    try:
        current_fd = os.dup(trusted_fd)
    except OSError as error:
        raise PersonaHistoryAttestationError(
            "cannot duplicate the trusted-root descriptor"
        ) from error
    try:
        _require_noninheritable(current_fd, "trusted-root duplicate")
        current_metadata = os.fstat(current_fd)
        for component in parts:
            try:
                namespace = os.stat(
                    component,
                    dir_fd=current_fd,
                    follow_symlinks=False,
                )
                child_fd = os.open(
                    component,
                    _open_flags(directory=True),
                    dir_fd=current_fd,
                )
            except OSError as error:
                raise PersonaHistoryAttestationError(
                    f"cannot open contained runtime component safely: {component}"
                ) from error
            try:
                _require_noninheritable(child_fd, "contained runtime directory")
                opened = os.fstat(child_fd)
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or opened.st_dev != trusted_device
                    or _stable_metadata(opened) != _stable_metadata(namespace)
                ):
                    raise PersonaHistoryAttestationError(
                        f"contained runtime component changed while opening: {component}"
                    )
            except Exception:
                os.close(child_fd)
                raise
            os.close(current_fd)
            current_fd = child_fd
            current_metadata = opened
        return current_fd, current_metadata
    except Exception:
        os.close(current_fd)
        raise


def _walk_trusted_runtime_content_root(
    trusted_root: os.PathLike[str] | str,
    path: os.PathLike[str] | str,
    relative_path: str,
    limits: AttestationLimits,
) -> DirectoryContentRoot:
    """Walk one descriptor path from a held canonical trusted-root FD."""
    _require_handle_platform()
    trusted = _canonical_existing_absolute_directory(
        trusted_root, "trusted_root"
    )
    runtime = _canonical_existing_absolute_directory(path, "runtime path")
    parts = PurePosixPath(relative_path).parts
    expected_runtime = trusted.joinpath(*parts)
    if runtime != expected_runtime:
        raise PersonaHistoryAttestationError(
            "runtime path is not the descriptor child of trusted_root"
        )
    trusted_fd, trusted_metadata = _open_root_directory(trusted)
    target_fd = None
    try:
        target_fd, target_metadata = _open_relative_directory(
            trusted_fd,
            parts,
            trusted_metadata.st_dev,
        )
        namespace = runtime.lstat()
        if _stable_metadata(namespace) != _stable_metadata(target_metadata):
            raise PersonaHistoryAttestationError(
                "contained runtime namespace differs from its held descriptor"
            )
        result = _walk_directory_fd(target_fd, target_metadata, limits)
        target_after = os.fstat(target_fd)
        if _stable_metadata(target_after) != _stable_metadata(target_metadata):
            raise PersonaHistoryAttestationError(
                "contained runtime root changed during traversal"
            )
        reopened_fd, reopened_metadata = _open_relative_directory(
            trusted_fd,
            parts,
            trusted_metadata.st_dev,
        )
        try:
            if _stable_metadata(reopened_metadata) != _stable_metadata(target_after):
                raise PersonaHistoryAttestationError(
                    "contained runtime namespace changed during traversal"
                )
        finally:
            os.close(reopened_fd)
        trusted_after = os.fstat(trusted_fd)
        trusted_namespace = trusted.lstat()
        if (
            _stable_metadata(trusted_after) != _stable_metadata(trusted_metadata)
            or _stable_metadata(trusted_namespace) != _stable_metadata(trusted_after)
            or trusted.resolve(strict=True) != trusted
            or runtime.resolve(strict=True) != runtime
        ):
            raise PersonaHistoryAttestationError(
                "trusted-root/runtime containment changed during traversal"
            )
        return result
    finally:
        if target_fd is not None:
            os.close(target_fd)
        os.close(trusted_fd)


SemanticChecker = Callable[
    [Path, Mapping[str, str], DirectoryContentRoot],
    KcsSemanticEvidence,
]


def build_runtime_directory_receipt(
    path: os.PathLike[str] | str,
    descriptor: Mapping[str, str],
    *,
    trusted_root: os.PathLike[str] | str,
    semantic_checker: SemanticChecker,
    limits: AttestationLimits = DEFAULT_LIMITS,
) -> RuntimeDirectoryReceipt:
    """Build an envelope-compatible receipt after explicit KCS semantics.

    The checker is intentionally a required keyword argument.  A generic tree
    walk cannot be promoted accidentally.  ``trusted_root`` is also mandatory;
    every descriptor component is opened no-follow relative to its held FD.
    The directory is walked again after the checker and both filesystem-only
    receipts must match exactly.
    """
    if type(descriptor) is not dict or set(descriptor) != {"kind", "relative_path"}:
        raise PersonaHistoryAttestationError(
            "runtime descriptor must contain exactly kind and relative_path"
        )
    kind = descriptor.get("kind")
    relative_path = descriptor.get("relative_path")
    if type(kind) is not str:
        raise PersonaHistoryAttestationError("runtime descriptor kind is invalid")
    _validate_relative_runtime_path(relative_path, kind)
    if not callable(semantic_checker):
        raise PersonaHistoryAttestationError(
            "an explicit KCS semantic checker is required"
        )
    root = _canonical_existing_absolute_directory(path, "runtime path")
    before = _walk_trusted_runtime_content_root(
        trusted_root,
        root,
        relative_path,
        limits,
    )
    try:
        evidence = semantic_checker(root, dict(descriptor), before)
    except Exception as error:
        raise PersonaHistoryAttestationError(
            "KCS semantic checker failed"
        ) from error
    if type(evidence) is not KcsSemanticEvidence:
        raise PersonaHistoryAttestationError(
            "KCS semantic checker did not return typed evidence"
        )
    if (
        evidence.kind != kind
        or evidence.relative_path != relative_path
        or evidence.content_root_sha256 != before.content_root_sha256
    ):
        raise PersonaHistoryAttestationError(
            "KCS semantic evidence is not bound to this runtime snapshot"
        )
    after = _walk_trusted_runtime_content_root(
        trusted_root,
        root,
        relative_path,
        limits,
    )
    if after != before:
        raise PersonaHistoryAttestationError(
            "runtime directory changed during KCS semantic checking"
        )
    return RuntimeDirectoryReceipt(
        schema=generator.RUNTIME_DIRECTORY_ATTESTATION_SCHEMA,
        schema_version=1,
        kind=kind,
        relative_path=relative_path,
        directory_device=before.directory_device,
        directory_inode=before.directory_inode,
        directory_nlink=before.directory_nlink,
        attestor_schema=evidence.attestor_schema,
        content_root_sha256=before.content_root_sha256,
        semantic_evidence=evidence,
    )


def make_runtime_attestor(
    semantic_checker: SemanticChecker,
    *,
    trusted_root: os.PathLike[str] | str,
    limits: AttestationLimits = DEFAULT_LIMITS,
) -> Callable[[Path, dict[str, str]], dict[str, object]]:
    """Adapt a typed checker to the envelope's exact callback protocol."""
    if not callable(semantic_checker):
        raise PersonaHistoryAttestationError(
            "an explicit KCS semantic checker is required"
        )

    def callback(path: Path, descriptor: dict[str, str]) -> dict[str, object]:
        return build_runtime_directory_receipt(
            path,
            descriptor,
            trusted_root=trusted_root,
            semantic_checker=semantic_checker,
            limits=limits,
        ).to_callback_dict()

    return callback


def validate_chunk_arithmetic(
    value: Mapping[str, object],
) -> ChunkArithmetic:
    """Validate the exact W0 contributor/incidental/raw-only equations."""
    fields = {
        "expected_contract_contributor_chunks",
        "contract_contributor_chunks",
        "incidental_searchable_chunks",
        "raw_only_chunks",
        "all_current_eligible_chunks",
    }
    if type(value) is not dict or set(value) != fields:
        raise PersonaHistoryAttestationError(
            "chunk arithmetic has an invalid field set"
        )
    counts = {label: _require_count(value[label], label) for label in fields}
    if (
        counts["contract_contributor_chunks"]
        != counts["expected_contract_contributor_chunks"]
    ):
        raise PersonaHistoryAttestationError(
            "contract contributor chunks differ from the expected target"
        )
    if counts["raw_only_chunks"] != 0:
        raise PersonaHistoryAttestationError(
            "raw-only sources contributed searchable chunks"
        )
    if counts["all_current_eligible_chunks"] != (
        counts["contract_contributor_chunks"]
        + counts["incidental_searchable_chunks"]
    ):
        raise PersonaHistoryAttestationError(
            "all-current eligible arithmetic does not equal contributor plus incidental"
        )
    return ChunkArithmetic(**counts)


def build_partial_scope_receipt(
    *,
    profile: str,
    persona_id: str,
    scope_key: str,
    relative_path: str,
    directory_content: DirectoryContentRoot,
    chunk_arithmetic: ChunkArithmetic,
    runtime_callback_receipt: RuntimeDirectoryReceipt | None = None,
) -> PartialScopeReceipt:
    if type(directory_content) is not DirectoryContentRoot:
        raise PersonaHistoryAttestationError(
            "scope directory_content must be a typed content root"
        )
    if type(chunk_arithmetic) is not ChunkArithmetic:
        raise PersonaHistoryAttestationError(
            "scope chunk_arithmetic must be validated first"
        )
    return PartialScopeReceipt(
        schema=PARTIAL_SCOPE_SCHEMA,
        schema_version=1,
        profile=profile,
        persona_id=persona_id,
        scope_key=scope_key,
        relative_path=relative_path,
        directory_content=directory_content,
        chunk_arithmetic=chunk_arithmetic,
        runtime_callback_receipt=runtime_callback_receipt,
    )


def build_partial_person_receipt(
    *,
    profile: str,
    persona_id: str,
    expected_contract_contributor_chunks: int,
    device_relative_path: str,
    device_content: DirectoryContentRoot,
    scopes: Iterable[PartialScopeReceipt],
    device_runtime_callback_receipt: RuntimeDirectoryReceipt | None = None,
) -> PartialPersonReceipt:
    if type(device_content) is not DirectoryContentRoot:
        raise PersonaHistoryAttestationError(
            "device directory_content must be a typed content root"
        )
    bounded_scopes = _bounded_tuple(
        scopes, EXPECTED_SCOPES_PER_PERSON, "partial-person scopes"
    )
    return PartialPersonReceipt(
        schema=PARTIAL_PERSON_SCHEMA,
        schema_version=1,
        profile=profile,
        persona_id=persona_id,
        expected_contract_contributor_chunks=expected_contract_contributor_chunks,
        device_relative_path=device_relative_path,
        device_content=device_content,
        scopes=bounded_scopes,
        device_runtime_callback_receipt=device_runtime_callback_receipt,
    )


def _canonical_digest(value: object) -> str:
    try:
        return generator.generation_plan_sha256(value)
    except (generator.PersonaGenerationError, TypeError, ValueError) as error:
        raise PersonaHistoryAttestationError(
            "canonical attestation projection cannot be hashed"
        ) from error


def _canonical_persona_contract(
    profile: str,
    person: PartialPersonReceipt,
) -> tuple[dict[str, tuple[str, int]], dict[str, str]]:
    """Rebuild and release one bounded canonical persona plan at a time."""
    try:
        persona_plan = generator.build_persona_generation_plan(
            profile, person.persona_id
        )
        generator.validate_persona_generation_plan(
            persona_plan,
            expected_profile=profile,
            expected_persona_id=person.persona_id,
        )
        event_projection = generator.persona_event_plan_projection(
            persona_plan,
            expected_profile=profile,
            expected_persona_id=person.persona_id,
        )
    except (generator.PersonaGenerationError, KeyError, TypeError, ValueError) as error:
        raise PersonaHistoryAttestationError(
            f"cannot derive canonical {profile} plan for {person.persona_id}"
        ) from error
    canonical = persona_plan["persona"]
    expected_person_target = canonical["planned_contract_chunks"]
    if person.expected_contract_contributor_chunks != expected_person_target:
        raise PersonaHistoryAttestationError(
            f"{person.persona_id} expected contributor total differs from "
            f"the canonical {profile} plan"
        )
    expected_scopes = {
        scope["scope_key"]: (
            f"devices/{canonical['device_slug']}/home/{scope['relative_path']}/"
            f"{generator.SCOPE_STORE_DIRECTORY_NAME}",
            scope["expected_contract_chunks"],
        )
        for scope in canonical["scopes"]
    }
    expected_device_path = (
        f"devices/{canonical['device_slug']}/"
        f"{generator.DEVICE_STATE_DIRECTORY_NAME}"
    )
    if person.device_relative_path != expected_device_path:
        raise PersonaHistoryAttestationError(
            f"{person.persona_id} device path differs from the canonical plan"
        )
    for scope in person.scopes:
        expected = expected_scopes.get(scope.scope_key)
        if expected is None or scope.relative_path != expected[0]:
            raise PersonaHistoryAttestationError(
                f"{person.persona_id} scope identity/path differs from the "
                f"canonical {profile} plan: {scope.scope_key}"
            )
        target = expected[1]
        arithmetic = scope.chunk_arithmetic
        if (
            arithmetic.expected_contract_contributor_chunks != target
            or arithmetic.contract_contributor_chunks != target
        ):
            raise PersonaHistoryAttestationError(
                f"{person.persona_id} scope contributor chunks differ from the "
                f"canonical {profile} target: {scope.scope_key}"
            )
    binding = {
        "persona_id": person.persona_id,
        "persona_plan_sha256": _canonical_digest(persona_plan),
        "event_projection_sha256": _canonical_digest(event_projection),
    }
    # Only bounded path/target pairs and two digests escape this helper.  The
    # potentially large source expansion becomes collectible before the next
    # persona is derived by the caller.
    return expected_scopes, binding


def _binding_root(bindings: tuple[dict[str, str], ...], field_name: str) -> str:
    return _canonical_digest({
        "schema": "kcs.persona.w0.canonical-persona-binding-root/v1",
        "schema_version": 1,
        "field": field_name,
        "bindings": [
            {
                "persona_id": row["persona_id"],
                field_name: row[field_name],
            }
            for row in sorted(bindings, key=lambda value: value["persona_id"])
        ],
    })


def _suite_projection(
    profile: str,
    people: tuple[PartialPersonReceipt, ...],
    canonical_bindings: tuple[dict[str, str], ...],
) -> str:
    rows = []
    for person in sorted(people, key=lambda value: value.persona_id):
        rows.append({
            "kind": "device_state",
            "persona_id": person.persona_id,
            "relative_path": person.device_relative_path,
            "content_root_sha256": person.device_content.content_root_sha256,
        })
        for scope in sorted(person.scopes, key=lambda value: value.scope_key):
            rows.append({
                "kind": "scope_store",
                "persona_id": person.persona_id,
                "scope_key": scope.scope_key,
                "relative_path": scope.relative_path,
                "content_root_sha256": scope.directory_content.content_root_sha256,
                "chunk_arithmetic": {
                    "expected_contract_contributor_chunks": (
                        scope.chunk_arithmetic.expected_contract_contributor_chunks
                    ),
                    "contract_contributor_chunks": (
                        scope.chunk_arithmetic.contract_contributor_chunks
                    ),
                    "incidental_searchable_chunks": (
                        scope.chunk_arithmetic.incidental_searchable_chunks
                    ),
                    "raw_only_chunks": scope.chunk_arithmetic.raw_only_chunks,
                    "all_current_eligible_chunks": (
                        scope.chunk_arithmetic.all_current_eligible_chunks
                    ),
                },
            })
    raw = json.dumps(
        {
            "schema": SUITE_RECEIPT_SCHEMA,
            "schema_version": 1,
            "profile": profile,
            "canonical_persona_bindings": sorted(
                canonical_bindings,
                key=lambda value: value["persona_id"],
            ),
            "runtime_projections": rows,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_suite_receipt(
    *,
    profile: str,
    people: Iterable[PartialPersonReceipt],
    kcs_semantics_callback_attested: bool = False,
) -> SuiteAttestationReceipt:
    """Build a suite projection while enforcing the 400/20 readiness gate.

    An incomplete set is useful as a progress receipt but cannot claim semantic
    coverage.  Requesting the semantic-callback coverage flag on anything other
    than the exact canonical 20-person/400-scope shape fails closed.  Even when
    all 420 external checker callbacks are represented, this module has not
    itself validated SQLite/CAS, HEAD/commit relations, KCS binary/config, plan,
    root, or prepare-intent binding.  It therefore always leaves
    ``history_ready_attested=False``; a later concrete full semantic attestor
    must produce that stronger claim.
    """
    if profile not in ("tiny", "pilot", "full"):
        raise PersonaHistoryAttestationError(f"unknown profile: {profile!r}")
    if type(kcs_semantics_callback_attested) is not bool:
        raise PersonaHistoryAttestationError(
            "kcs_semantics_callback_attested must be a bool"
        )
    people = _bounded_tuple(people, EXPECTED_PERSONAS, "suite people")
    if any(type(person) is not PartialPersonReceipt for person in people):
        raise PersonaHistoryAttestationError(
            "suite people must be typed partial-person receipts"
        )
    persona_ids = [person.persona_id for person in people]
    if len(persona_ids) != len(set(persona_ids)):
        raise PersonaHistoryAttestationError("suite contains duplicate personas")
    scope_count = sum(len(person.scopes) for person in people)
    expected_ids = {persona["id"] for persona in fixture_spec.PERSONAS}
    exact_personas = set(persona_ids) == expected_ids and len(people) == EXPECTED_PERSONAS
    canonical_bindings = []
    exact_scope_sets = exact_personas
    # Build and release one canonical persona expansion before proceeding to
    # the next.  Never materialize the all-person generation plan here.
    for person in people:
        if person.profile != profile:
            raise PersonaHistoryAttestationError(
                f"{person.persona_id} receipt profile differs from suite profile"
            )
        expected_scopes, binding = _canonical_persona_contract(profile, person)
        canonical_bindings.append(binding)
        actual_scope_keys = {scope.scope_key for scope in person.scopes}
        if (
            actual_scope_keys != set(expected_scopes)
            or len(person.scopes) != EXPECTED_SCOPES_PER_PERSON
        ):
            exact_scope_sets = False
        del expected_scopes
    canonical_bindings = tuple(canonical_bindings)
    exact_shape = (
        exact_personas
        and exact_scope_sets
        and scope_count == EXPECTED_SCOPE_STORES
        and len(people) == EXPECTED_DEVICE_STATES
    )
    arithmetic_complete = exact_shape and all(
        person.chunk_arithmetic_complete for person in people
    )
    runtime_receipts = [
        receipt
        for person in people
        for receipt in (
            person.device_runtime_callback_receipt,
            *(scope.runtime_callback_receipt for scope in person.scopes),
        )
        if receipt is not None
    ]
    runtime_identities = {
        (receipt.directory_device, receipt.directory_inode)
        for receipt in runtime_receipts
    }
    runtime_semantics_complete = (
        exact_shape
        and all(person.kcs_semantics_attested for person in people)
        and len(runtime_receipts) == EXPECTED_SCOPE_STORES + EXPECTED_DEVICE_STATES
        and len(runtime_identities) == len(runtime_receipts)
    )
    if kcs_semantics_callback_attested and not (
        exact_shape and arithmetic_complete and runtime_semantics_complete
    ):
        raise PersonaHistoryAttestationError(
            "semantic coverage requires exactly 400 canonical scopes, 20 devices, "
            "complete arithmetic, and 420 typed runtime callback receipts"
        )
    semantic_coverage = (
        kcs_semantics_callback_attested
        and exact_shape
        and arithmetic_complete
        and runtime_semantics_complete
    )
    arithmetic = [
        scope.chunk_arithmetic
        for person in people
        for scope in person.scopes
    ]
    return SuiteAttestationReceipt(
        schema=SUITE_RECEIPT_SCHEMA,
        schema_version=1,
        profile=profile,
        personas=len(people),
        scope_stores=scope_count,
        device_states=len(people),
        expected_contract_contributor_chunks=sum(
            person.expected_contract_contributor_chunks for person in people
        ),
        contract_contributor_chunks=sum(
            row.contract_contributor_chunks for row in arithmetic
        ),
        incidental_searchable_chunks=sum(
            row.incidental_searchable_chunks for row in arithmetic
        ),
        raw_only_chunks=sum(row.raw_only_chunks for row in arithmetic),
        all_current_eligible_chunks=sum(
            row.all_current_eligible_chunks for row in arithmetic
        ),
        filesystem_coverage_complete=exact_shape,
        kcs_semantics_callback_attested=kcs_semantics_callback_attested,
        semantic_coverage_attested=semantic_coverage,
        history_ready_attested=False,
        persona_plan_root_sha256=_binding_root(
            canonical_bindings, "persona_plan_sha256"
        ),
        event_projection_root_sha256=_binding_root(
            canonical_bindings, "event_projection_sha256"
        ),
        projection_root_sha256=_suite_projection(
            profile, people, canonical_bindings
        ),
    )
