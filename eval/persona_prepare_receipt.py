"""Canonical, non-executing W0 prepare receipts for persona-PC fixtures.

This module composes declared artifact hashes into an exact
root/person/device/scope hierarchy.  It regenerates the canonical all-person
generation-plan digest one bounded person at a time, but it deliberately
performs no filesystem I/O, subprocess execution, API access, SQLite
inspection, CAS inspection, or typed command-receipt validation.  Consequently
every semantic-evidence claim is fixed to ``False`` and no value emitted here
can make history assignment executable.

The all-person receipt is bounded to twenty compact person summaries.  Exact
persona/source contracts are rebuilt one persona at a time with
``build_persona_generation_plan``; the all-person generation plan is never
materialized by this module.
"""

from __future__ import annotations

import copy
from functools import lru_cache
import hashlib
from pathlib import PurePosixPath
import re
import unicodedata

try:  # Package imports and direct ``python eval/...`` execution.
    from . import generate_persona_corpus as generator
    from . import persona_fixture_spec as fixture_spec
    from . import persona_manifest as manifest
    from . import persona_renderers as renderers
except ImportError:  # pragma: no cover - retained for repository script style.
    import generate_persona_corpus as generator
    import persona_fixture_spec as fixture_spec
    import persona_manifest as manifest
    import persona_renderers as renderers


PREPARE_RECEIPT_INTENT_SCHEMA = "kio.persona.w0.prepare-receipt-intent/v1"
PERSON_COMMAND_BINDING_SCHEMA = "kio.persona.w0.person-command-binding/v1"
SCOPE_COMMAND_BINDING_SCHEMA = "kio.persona.w0.scope-command-binding/v1"
ROOT_RECEIPT_SCHEMA = "kio.persona.w0.prepare-root-receipt/v1"
PERSON_RECEIPT_SCHEMA = "kio.persona.w0.prepare-person-receipt/v1"
DEVICE_RECEIPT_SCHEMA = "kio.persona.w0.prepare-device-receipt/v1"
SCOPE_RECEIPT_SCHEMA = "kio.persona.w0.prepare-scope-receipt/v1"
SEMANTIC_EVIDENCE_SCHEMA = "kio.persona.w0.unimplemented-semantic-evidence/v1"

EXPECTED_PERSONAS = 20
EXPECTED_SCOPES_PER_PERSON = 20
EXPECTED_SCOPE_STORES = EXPECTED_PERSONAS * EXPECTED_SCOPES_PER_PERSON
MAX_INTENT_BYTES = 4 * 1024 * 1024
MAX_ROOT_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_SIGNED_INT = 2**63 - 1
MAX_DESTINATION_ROOT_BYTES = 4_096
MAX_DESTINATION_ROOT_COMPONENTS = 64
MAX_PORTABLE_COMPONENT_BYTES = 255

_PROFILES = frozenset(("tiny", "pilot", "full"))
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_PERSONA_ID_RE = re.compile(r"p[0-9]{2}\Z")
_WINDOWS_FORBIDDEN = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED = frozenset(
    ("con", "prn", "aux", "nul")
    + tuple(f"com{number}" for number in range(1, 10))
    + tuple(f"lpt{number}" for number in range(1, 10))
)

_INTENT_CONTRACTS = {
    "read_only_schema_composition": True,
    "filesystem_mutation": False,
    "subprocess_execution": False,
    "external_api_execution": False,
    "semantic_store_inspection": False,
    "history_ready_claim": False,
    "history_assignment_execution": False,
}

_NEGATIVE_CLAIMS = {
    "semantic_checks_complete": False,
    "actual_kio_chunks_attested": False,
    "opaque_runtime_contents_attested": False,
    "external_api_absence_attested": False,
    "history_ready_attested": False,
    "history_assignment_executable": False,
}

ROOT_SEMANTIC_CHECKS = (
    "generation_plan_on_disk_bytes_attested",
    "suite_manifest_on_disk_bytes_attested",
    "capacity_receipt_attested",
    "root_binding_on_disk_bytes_attested",
    "persona_manifests_attested",
    "prepare_intent_declared_files_attested",
    "owner_marker_attested",
    "immutable_source_tree_attested",
    "runtime_directory_identities_attested",
    "binary_identity_revalidated",
    "command_receipt_contents_attested",
    "all_person_semantics_attested",
    "cross_replay_projection_attested",
)
PERSON_SEMANTIC_CHECKS = (
    "persona_manifest_attested",
    "persona_root_identity_attested",
    "environment_receipt_content_attested",
    "device_semantics_attested",
    "all_scope_semantics_attested",
    "unique_scope_ids_attested",
    "exact_person_chunk_arithmetic_attested",
    "one_person_resource_bound_attested",
)
DEVICE_SEMANTIC_CHECKS = (
    "isolated_xdg_root_attested",
    "environment_receipt_content_attested",
    "registry_sqlite_snapshot_attested",
    "registry_schema_attested",
    "registry_integrity_attested",
    "registry_exact_scope_rows_attested",
    "registry_scope_paths_attested",
    "registry_global_indexed_flags_attested",
    "registry_no_cross_person_state_attested",
    "cost_ledger_zero_attested",
    "reservation_ledger_zero_attested",
    "reclaim_ledger_zero_attested",
    "no_external_credentials_attested",
    "stable_snapshot_attested",
)
SCOPE_SEMANTIC_CHECKS = (
    "scope_root_binding_attested",
    "scope_id_attested",
    "kio_layout_attested",
    "config_attested",
    "tool_lock_attested",
    "head_ref_attested",
    "commit_cas_attested",
    "tree_cas_attested",
    "raw_cas_attested",
    "prepared_objects_attested",
    "normalized_instances_attested",
    "chunk_ledger_attested",
    "chunk_cas_attested",
    "sqlite_schema_attested",
    "sqlite_integrity_attested",
    "current_chunk_eligibility_attested",
    "scope_manifest_binding_attested",
    "per_source_contributor_quota_attested",
    "contract_contributor_chunks_attested",
    "incidental_searchable_chunks_attested",
    "raw_only_zero_attested",
    "fts_coverage_attested",
    "embedding_offline_state_attested",
    "durable_task_state_attested",
    "unsupported_input_state_attested",
    "approval_state_attested",
    "quarantine_state_attested",
    "no_purge_state_attested",
    "w0_no_history_state_attested",
    "init_receipt_content_attested",
    "index_receipt_content_attested",
    "stable_snapshot_attested",
)

_SEMANTIC_CHECKS_BY_KIND = {
    "root": ROOT_SEMANTIC_CHECKS,
    "person": PERSON_SEMANTIC_CHECKS,
    "device": DEVICE_SEMANTIC_CHECKS,
    "scope": SCOPE_SEMANTIC_CHECKS,
}


class PersonaPrepareReceiptError(ValueError):
    """Raised when a prepare intent or receipt is not exact and canonical."""


def _canonical_bytes(value: object) -> bytes:
    try:
        return manifest.canonical_json_bytes(value)
    except (manifest.PersonaManifestError, TypeError, ValueError) as error:
        raise PersonaPrepareReceiptError("value is not canonical JSON") from error


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _canonical_file_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value) + b"\n").hexdigest()


def _exact_dict(value: object, fields: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise PersonaPrepareReceiptError(f"{label} has an invalid field set")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise PersonaPrepareReceiptError(f"{label} must be a lowercase SHA-256")
    return value


def _count(value: object, label: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SIGNED_INT:
        raise PersonaPrepareReceiptError(
            f"{label} must be a non-negative bounded integer"
        )
    return value


def _profile(value: object) -> str:
    if type(value) is not str or value not in _PROFILES:
        raise PersonaPrepareReceiptError(f"invalid profile: {value!r}")
    return value


def _replay_id(value: object) -> str:
    if type(value) is not str or value not in generator.REPLAY_IDS:
        raise PersonaPrepareReceiptError(f"invalid replay id: {value!r}")
    return value


def _persona_id(value: object) -> str:
    canonical = tuple(row["id"] for row in fixture_spec.PERSONAS)
    if (
        type(value) is not str
        or _PERSONA_ID_RE.fullmatch(value) is None
        or value not in canonical
    ):
        raise PersonaPrepareReceiptError(f"invalid persona id: {value!r}")
    return value


def _absolute_root(value: object) -> str:
    if type(value) is not str:
        raise PersonaPrepareReceiptError("destination_root is not a canonical path")
    if (
        not value
        or value == "/"
        or len(value) > MAX_DESTINATION_ROOT_BYTES
        or value.startswith("//")
        or "\\" in value
        or "\x00" in value
        or unicodedata.normalize("NFC", value) != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise PersonaPrepareReceiptError("destination_root is not a canonical path")
    if len(value.encode("utf-8")) > MAX_DESTINATION_ROOT_BYTES:
        raise PersonaPrepareReceiptError("destination_root is not a canonical path")
    path = PurePosixPath(value)
    if not path.is_absolute() or str(path) != value:
        raise PersonaPrepareReceiptError("destination_root is not canonical absolute POSIX")
    components = path.parts[1:]
    if (
        not components
        or len(components) > MAX_DESTINATION_ROOT_COMPONENTS
        or any(
            component in ("", ".", "..")
            or len(component.encode("utf-8")) > MAX_PORTABLE_COMPONENT_BYTES
            for component in components
        )
    ):
        raise PersonaPrepareReceiptError("destination_root has an invalid component")
    return value


def _portable_declared_path(value: object, namespace: str, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > generator.MAX_HISTORY_PREPARE_RELATIVE_PATH_BYTES
    ):
        raise PersonaPrepareReceiptError(f"{label} path must be a string")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as error:
        raise PersonaPrepareReceiptError(f"{label} path must be ASCII") from error
    path = PurePosixPath(value)
    allowed = PurePosixPath(namespace)
    if (
        len(encoded) > generator.MAX_HISTORY_PREPARE_RELATIVE_PATH_BYTES
        or path.is_absolute()
        or str(path) != value
        or len(path.parts) < 2
        or len(path.parts) > generator.MAX_HISTORY_PREPARE_PATH_COMPONENTS
        or allowed not in path.parents
    ):
        raise PersonaPrepareReceiptError(f"{label} path is outside its namespace")
    for component in path.parts:
        stem = component.split(".", 1)[0].casefold()
        if (
            component in ("", ".", "..")
            or len(component.encode("ascii")) > MAX_PORTABLE_COMPONENT_BYTES
            or component.endswith((".", " "))
            or any(character in _WINDOWS_FORBIDDEN for character in component)
            or any(ord(character) < 32 or ord(character) == 127 for character in component)
            or stem in _WINDOWS_RESERVED
            or component.casefold()
            in {
                generator.SCOPE_STORE_DIRECTORY_NAME.casefold(),
                generator.DEVICE_STATE_DIRECTORY_NAME.casefold(),
            }
        ):
            raise PersonaPrepareReceiptError(f"{label} path is not portable")
    return value


def _canonical_declared_files(rows: object, namespace: str, label: str) -> list[dict]:
    if type(rows) not in (list, tuple):
        raise PersonaPrepareReceiptError(f"{label} rows must be a list")
    if len(rows) > generator.MAX_HISTORY_PREPARE_DECLARED_FILES:
        raise PersonaPrepareReceiptError(f"{label} rows exceed their count bound")
    result = []
    for row in rows:
        row = _exact_dict(
            row, {"relative_path", "raw_sha256", "bytes"}, f"{label} row"
        )
        result.append({
            "relative_path": _portable_declared_path(
                row["relative_path"], namespace, label
            ),
            "raw_sha256": _digest(row["raw_sha256"], f"{label} raw_sha256"),
            "bytes": _count(row["bytes"], f"{label} bytes"),
        })
        if result[-1]["bytes"] > generator.MAX_HISTORY_PREPARE_DECLARED_FILE_BYTES:
            raise PersonaPrepareReceiptError(f"{label} row exceeds its byte bound")
    result.sort(key=lambda row: row["relative_path"])
    paths = [row["relative_path"] for row in result]
    if len(paths) != len(set(paths)) or len(paths) != len({p.casefold() for p in paths}):
        raise PersonaPrepareReceiptError(f"{label} paths are duplicated")
    return result


@lru_cache(maxsize=len(_PROFILES))
def _canonical_generation_plan_sha256(profile: str) -> str:
    """Stream the exact all-person plan digest one bounded person at a time."""
    top_level = {
        "schema": generator.PLAN_SCHEMA,
        "schema_version": 1,
        "fixture_schema_version": fixture_spec.SCHEMA_VERSION,
        "fixture_id": fixture_spec.FIXTURE_ID,
        "seed": fixture_spec.SEED,
        "profile": profile,
        "replay_count": fixture_spec.REPLAY_COUNT,
        "renderer_id": renderers.RENDERER_ID,
        "renderer_schema_version": renderers.RENDERER_SCHEMA_VERSION,
    }
    fields = {*top_level, "personas", "totals"}
    totals = {
        "personas": 0,
        "scope_shards": 0,
        "physical_sources": 0,
        "planned_contract_chunks": 0,
    }
    digest = hashlib.sha256()
    digest.update(b"{")
    for field_ordinal, field in enumerate(sorted(fields)):
        if field_ordinal:
            digest.update(b",")
        digest.update(_canonical_bytes(field))
        digest.update(b":")
        if field == "personas":
            digest.update(b"[")
            for ordinal, persona in enumerate(fixture_spec.PERSONAS):
                persona_id = persona["id"]
                try:
                    plan = generator.build_persona_generation_plan(
                        profile, persona_id
                    )
                    generator.validate_persona_generation_plan(
                        plan,
                        expected_profile=profile,
                        expected_persona_id=persona_id,
                    )
                except (
                    generator.PersonaGenerationError,
                    KeyError,
                    TypeError,
                    ValueError,
                ) as error:
                    raise PersonaPrepareReceiptError(
                        f"cannot rebuild canonical persona plan for {persona_id}"
                    ) from error
                projection = plan["persona"]
                if ordinal:
                    digest.update(b",")
                digest.update(_canonical_bytes(projection))
                totals["personas"] += 1
                totals["scope_shards"] += len(projection["scopes"])
                totals["physical_sources"] += projection["raw_file_count"]
                totals["planned_contract_chunks"] += projection[
                    "planned_contract_chunks"
                ]
                del projection, plan
            digest.update(b"]")
        elif field == "totals":
            if (
                totals["personas"] != EXPECTED_PERSONAS
                or totals["scope_shards"] != EXPECTED_SCOPE_STORES
            ):
                raise PersonaPrepareReceiptError(
                    "canonical generation plan does not expand to exact 20/400"
                )
            digest.update(_canonical_bytes(totals))
        else:
            digest.update(_canonical_bytes(top_level[field]))
    digest.update(b"}")
    return digest.hexdigest()


def canonical_generation_plan_sha256(profile: str) -> str:
    """Return the canonical suite-plan SHA without materializing all people."""
    return _canonical_generation_plan_sha256(_profile(profile))


def _expected_runtime_directories() -> tuple[list[str], list[str]]:
    scopes = []
    devices = []
    for persona in fixture_spec.PERSONAS:
        device_slug = f"{persona['id']}-{persona['role']}"
        devices.append(
            f"devices/{device_slug}/{generator.DEVICE_STATE_DIRECTORY_NAME}"
        )
        for scope in fixture_spec.scope_specs(persona):
            scopes.append(
                f"devices/{device_slug}/home/{scope['relative_path']}/"
                f"{generator.SCOPE_STORE_DIRECTORY_NAME}"
            )
    if len(devices) != EXPECTED_PERSONAS or len(scopes) != EXPECTED_SCOPE_STORES:
        raise PersonaPrepareReceiptError("fixture does not expand to exact 20/400")
    return scopes, devices


def build_canonical_history_prepare_intent(
    *,
    profile: str,
    replay_id: str,
    generation_plan_sha256: str,
    receipt_files=(),
    control_files=(),
) -> dict:
    """Build the existing root-independent history-prepare intent, without I/O."""
    profile = _profile(profile)
    replay_id = _replay_id(replay_id)
    plan_sha256 = _digest(generation_plan_sha256, "generation_plan_sha256")
    if (
        type(receipt_files) not in (list, tuple)
        or type(control_files) not in (list, tuple)
        or len(receipt_files) > generator.MAX_HISTORY_PREPARE_DECLARED_FILES
        or len(control_files) > generator.MAX_HISTORY_PREPARE_DECLARED_FILES
        or len(receipt_files) + len(control_files)
        > generator.MAX_HISTORY_PREPARE_DECLARED_FILES
    ):
        raise PersonaPrepareReceiptError(
            "declared receipt/control file counts overflow"
        )
    if plan_sha256 != canonical_generation_plan_sha256(profile):
        raise PersonaPrepareReceiptError(
            "generation_plan_sha256 differs from the canonical suite plan"
        )
    receipts = _canonical_declared_files(
        receipt_files, generator.HISTORY_PREPARE_RECEIPT_DIRECTORY, "receipt"
    )
    controls = _canonical_declared_files(
        control_files, generator.HISTORY_PREPARE_CONTROL_DIRECTORY, "control"
    )
    combined = [*receipts, *controls]
    paths = [row["relative_path"] for row in combined]
    if (
        len(combined) > generator.MAX_HISTORY_PREPARE_DECLARED_FILES
        or sum(row["bytes"] for row in combined)
        > generator.MAX_HISTORY_PREPARE_DECLARED_TOTAL_BYTES
        or len(paths) != len(set(paths))
        or len(paths) != len({path.casefold() for path in paths})
    ):
        raise PersonaPrepareReceiptError("declared receipt/control files overlap or overflow")
    scope_stores, device_states = _expected_runtime_directories()
    return {
        "schema": generator.HISTORY_PREPARE_INTENT_SCHEMA,
        "schema_version": 1,
        "fixture_id": fixture_spec.FIXTURE_ID,
        "profile": profile,
        "replay_id": replay_id,
        "plan_sha256": plan_sha256,
        "scope_store_directories": scope_stores,
        "device_state_directories": device_states,
        "receipt_files": receipts,
        "control_files": controls,
    }


def validate_canonical_history_prepare_intent(value: object) -> dict:
    fields = {
        "schema", "schema_version", "fixture_id", "profile", "replay_id",
        "plan_sha256", "scope_store_directories", "device_state_directories",
        "receipt_files", "control_files",
    }
    value = _exact_dict(value, fields, "history prepare intent")
    expected = build_canonical_history_prepare_intent(
        profile=value["profile"],
        replay_id=value["replay_id"],
        generation_plan_sha256=value["plan_sha256"],
        receipt_files=value["receipt_files"],
        control_files=value["control_files"],
    )
    if value != expected or _canonical_bytes(value) != _canonical_bytes(expected):
        raise PersonaPrepareReceiptError("history prepare intent is not canonical")
    return copy.deepcopy(expected)


def _validate_root_binding(
    value: object,
    *,
    profile: str,
    replay_id: str,
    destination_root: str,
    generation_plan_sha256: str,
) -> dict:
    fields = {
        "schema", "schema_version", "fixture_id", "profile", "replay_id",
        "destination_root", "filesystem_device", "plan_sha256",
        "suite_manifest_sha256", "capacity_receipt_sha256",
        "persona_manifest_root_sha256",
    }
    value = _exact_dict(value, fields, "root binding")
    if (
        value["schema"] != generator.ROOT_BINDING_SCHEMA
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["fixture_id"] != fixture_spec.FIXTURE_ID
        or value["profile"] != profile
        or value["replay_id"] != replay_id
        or value["destination_root"] != destination_root
        or value["plan_sha256"] != generation_plan_sha256
    ):
        raise PersonaPrepareReceiptError("root binding header/substitution mismatch")
    _absolute_root(value["destination_root"])
    _count(value["filesystem_device"], "root binding filesystem_device")
    for field in (
        "plan_sha256", "suite_manifest_sha256", "capacity_receipt_sha256",
        "persona_manifest_root_sha256",
    ):
        _digest(value[field], f"root binding {field}")
    if len(_canonical_bytes(value) + b"\n") > generator.ROOT_BINDING_BUDGET:
        raise PersonaPrepareReceiptError("root binding exceeds its byte bound")
    return copy.deepcopy(value)


def root_binding_sha256(value: object) -> str:
    """Hash a root binding with the same terminal-LF convention as the generator."""
    if type(value) is not dict:
        raise PersonaPrepareReceiptError("root binding must be a dict")
    return _canonical_file_sha256(value)


def build_person_command_binding(
    *,
    profile: str,
    replay_id: str,
    destination_root: str,
    root_binding_sha256: str,
    binary_identity_sha256: str,
    persona_id: str,
    environment_receipt_sha256: str,
    scope_receipt_hashes,
) -> dict:
    """Bind one person's environment and twenty command-receipt hashes."""
    profile = _profile(profile)
    replay_id = _replay_id(replay_id)
    destination_root = _absolute_root(destination_root)
    root_sha = _digest(root_binding_sha256, "root_binding_sha256")
    binary_sha = _digest(binary_identity_sha256, "binary_identity_sha256")
    persona_id = _persona_id(persona_id)
    environment_sha = _digest(
        environment_receipt_sha256, "environment_receipt_sha256"
    )
    if type(scope_receipt_hashes) not in (list, tuple):
        raise PersonaPrepareReceiptError("scope receipt hashes must be a list")
    persona = fixture_spec.get_persona(persona_id)
    expected_keys = [scope["scope_key"] for scope in fixture_spec.scope_specs(persona)]
    if len(scope_receipt_hashes) != EXPECTED_SCOPES_PER_PERSON:
        raise PersonaPrepareReceiptError("person must bind exactly twenty scopes")
    scopes = []
    for expected_key, compact in zip(expected_keys, scope_receipt_hashes, strict=True):
        compact = _exact_dict(
            compact,
            {"scope_key", "init_receipt_sha256", "index_receipt_sha256"},
            "scope receipt hash binding",
        )
        if compact["scope_key"] != expected_key:
            raise PersonaPrepareReceiptError("scope receipt hashes are out of order")
        scopes.append({
            "schema": SCOPE_COMMAND_BINDING_SCHEMA,
            "schema_version": 1,
            "fixture_id": fixture_spec.FIXTURE_ID,
            "profile": profile,
            "replay_id": replay_id,
            "destination_root": destination_root,
            "root_binding_sha256": root_sha,
            "binary_identity_sha256": binary_sha,
            "environment_receipt_sha256": environment_sha,
            "persona_id": persona_id,
            "scope_key": expected_key,
            "init_receipt_sha256": _digest(
                compact["init_receipt_sha256"], "init_receipt_sha256"
            ),
            "index_receipt_sha256": _digest(
                compact["index_receipt_sha256"], "index_receipt_sha256"
            ),
        })
    command_hashes = [
        value
        for scope in scopes
        for value in (scope["init_receipt_sha256"], scope["index_receipt_sha256"])
    ]
    if len(command_hashes) != len(set(command_hashes)):
        raise PersonaPrepareReceiptError("person command receipt hashes are duplicated")
    return {
        "schema": PERSON_COMMAND_BINDING_SCHEMA,
        "schema_version": 1,
        "fixture_id": fixture_spec.FIXTURE_ID,
        "profile": profile,
        "replay_id": replay_id,
        "destination_root": destination_root,
        "root_binding_sha256": root_sha,
        "binary_identity_sha256": binary_sha,
        "persona_id": persona_id,
        "environment_receipt_sha256": environment_sha,
        "scopes": scopes,
    }


def _validate_person_command_binding(
    value: object,
    *,
    profile: str,
    replay_id: str,
    destination_root: str,
    root_binding_sha256: str,
    binary_identity_sha256: str,
    expected_persona_id: str,
) -> dict:
    person_fields = {
        "schema", "schema_version", "fixture_id", "profile", "replay_id",
        "destination_root", "root_binding_sha256", "binary_identity_sha256",
        "persona_id", "environment_receipt_sha256", "scopes",
    }
    value = _exact_dict(value, person_fields, "person command binding")
    if (
        type(value["scopes"]) is not list
        or len(value["scopes"]) != EXPECTED_SCOPES_PER_PERSON
    ):
        raise PersonaPrepareReceiptError(
            "person command scopes must contain exactly twenty rows"
        )
    scope_fields = {
        "schema", "schema_version", "fixture_id", "profile", "replay_id",
        "destination_root", "root_binding_sha256", "binary_identity_sha256",
        "environment_receipt_sha256", "persona_id", "scope_key",
        "init_receipt_sha256", "index_receipt_sha256",
    }
    compact = []
    for scope in value["scopes"]:
        scope = _exact_dict(scope, scope_fields, "scope command binding")
        compact.append({
            "scope_key": scope["scope_key"],
            "init_receipt_sha256": scope["init_receipt_sha256"],
            "index_receipt_sha256": scope["index_receipt_sha256"],
        })
    expected = build_person_command_binding(
        profile=profile,
        replay_id=replay_id,
        destination_root=destination_root,
        root_binding_sha256=root_binding_sha256,
        binary_identity_sha256=binary_identity_sha256,
        persona_id=expected_persona_id,
        environment_receipt_sha256=value["environment_receipt_sha256"],
        scope_receipt_hashes=compact,
    )
    if value != expected or _canonical_bytes(value) != _canonical_bytes(expected):
        raise PersonaPrepareReceiptError("person command binding is not canonical")
    return copy.deepcopy(expected)


def build_prepare_receipt_intent(
    *,
    profile: str,
    replay_id: str,
    destination_root: str,
    generation_plan_sha256: str,
    root_binding: dict,
    binary_identity_sha256: str,
    history_prepare_intent: dict,
    person_command_bindings,
) -> dict:
    """Build an exact, self-contained input to prepare-receipt composition."""
    profile = _profile(profile)
    replay_id = _replay_id(replay_id)
    destination_root = _absolute_root(destination_root)
    plan_sha = _digest(generation_plan_sha256, "generation_plan_sha256")
    if plan_sha != canonical_generation_plan_sha256(profile):
        raise PersonaPrepareReceiptError(
            "generation_plan_sha256 differs from the canonical suite plan"
        )
    binary_sha = _digest(binary_identity_sha256, "binary_identity_sha256")
    root_binding = _validate_root_binding(
        root_binding,
        profile=profile,
        replay_id=replay_id,
        destination_root=destination_root,
        generation_plan_sha256=plan_sha,
    )
    root_sha = _canonical_file_sha256(root_binding)
    history_intent = validate_canonical_history_prepare_intent(
        history_prepare_intent
    )
    if (
        history_intent["profile"] != profile
        or history_intent["replay_id"] != replay_id
        or history_intent["plan_sha256"] != plan_sha
    ):
        raise PersonaPrepareReceiptError("history prepare intent substitution detected")
    if type(person_command_bindings) not in (list, tuple):
        raise PersonaPrepareReceiptError("person command bindings must be a list")
    expected_ids = [persona["id"] for persona in fixture_spec.PERSONAS]
    if len(person_command_bindings) != EXPECTED_PERSONAS:
        raise PersonaPrepareReceiptError("intent must bind exactly twenty people")
    people = []
    for expected_id, binding in zip(expected_ids, person_command_bindings, strict=True):
        people.append(_validate_person_command_binding(
            binding,
            profile=profile,
            replay_id=replay_id,
            destination_root=destination_root,
            root_binding_sha256=root_sha,
            binary_identity_sha256=binary_sha,
            expected_persona_id=expected_id,
        ))
    environment_hashes = [row["environment_receipt_sha256"] for row in people]
    command_hashes = [
        value
        for person in people
        for scope in person["scopes"]
        for value in (scope["init_receipt_sha256"], scope["index_receipt_sha256"])
    ]
    all_receipt_hashes = [*environment_hashes, *command_hashes]
    if len(all_receipt_hashes) != len(set(all_receipt_hashes)):
        raise PersonaPrepareReceiptError("environment/command receipt hashes are duplicated")
    person_binding_root = _canonical_sha256({
        "domain": "kio.persona.w0.person-command-binding-root/v1",
        "fixture_id": fixture_spec.FIXTURE_ID,
        "profile": profile,
        "replay_id": replay_id,
        "destination_root": destination_root,
        "bindings": [
            {
                "persona_id": person["persona_id"],
                "sha256": _canonical_sha256(person),
            }
            for person in people
        ],
    })
    result = {
        "schema": PREPARE_RECEIPT_INTENT_SCHEMA,
        "schema_version": 1,
        "fixture_id": fixture_spec.FIXTURE_ID,
        "fixture_schema_version": fixture_spec.SCHEMA_VERSION,
        "profile": profile,
        "replay_id": replay_id,
        "destination_root": destination_root,
        "generation_plan_sha256": plan_sha,
        "root_binding": root_binding,
        "root_binding_sha256": root_sha,
        "binary_identity_sha256": binary_sha,
        "history_prepare_intent": history_intent,
        "history_prepare_intent_sha256": _canonical_sha256(history_intent),
        "person_command_bindings": people,
        "person_command_binding_root_sha256": person_binding_root,
        "contracts": dict(_INTENT_CONTRACTS),
    }
    if len(_canonical_bytes(result)) > MAX_INTENT_BYTES:
        raise PersonaPrepareReceiptError("prepare receipt intent exceeds its byte bound")
    return result


def validate_prepare_receipt_intent(value: object) -> dict:
    fields = {
        "schema", "schema_version", "fixture_id", "fixture_schema_version",
        "profile", "replay_id", "destination_root", "generation_plan_sha256",
        "root_binding", "root_binding_sha256", "binary_identity_sha256",
        "history_prepare_intent", "history_prepare_intent_sha256",
        "person_command_bindings", "person_command_binding_root_sha256",
        "contracts",
    }
    value = _exact_dict(value, fields, "prepare receipt intent")
    expected = build_prepare_receipt_intent(
        profile=value["profile"],
        replay_id=value["replay_id"],
        destination_root=value["destination_root"],
        generation_plan_sha256=value["generation_plan_sha256"],
        root_binding=value["root_binding"],
        binary_identity_sha256=value["binary_identity_sha256"],
        history_prepare_intent=value["history_prepare_intent"],
        person_command_bindings=value["person_command_bindings"],
    )
    if value != expected or _canonical_bytes(value) != _canonical_bytes(expected):
        raise PersonaPrepareReceiptError("prepare receipt intent is not canonical")
    return copy.deepcopy(expected)


def _semantic_evidence(kind: str) -> dict:
    try:
        checks = _SEMANTIC_CHECKS_BY_KIND[kind]
    except KeyError as error:  # pragma: no cover - internal construction only.
        raise PersonaPrepareReceiptError(f"unknown semantic evidence kind: {kind}") from error
    return {
        "schema": SEMANTIC_EVIDENCE_SCHEMA,
        "schema_version": 1,
        "kind": kind,
        "checks": {name: False for name in checks},
        **_NEGATIVE_CLAIMS,
    }


def _operational_false_claims() -> dict:
    return {
        "filesystem_mutation_performed": False,
        "kio_commands_executed_by_this_module": False,
        "external_api_execution_performed": False,
        "history_ready_attested": False,
        "history_assignment_executable": False,
    }


def _scope_contract_sha256(
    *, profile: str, persona_id: str, persona_plan_sha256: str, scope: dict
) -> str:
    return _canonical_sha256({
        "domain": "kio.persona.w0.scope-plan-binding/v1",
        "fixture_id": fixture_spec.FIXTURE_ID,
        "profile": profile,
        "persona_id": persona_id,
        "persona_plan_sha256": persona_plan_sha256,
        "scope": scope,
    })


def _build_person_receipt(intent: dict, binding: dict) -> dict:
    profile = intent["profile"]
    persona_id = binding["persona_id"]
    try:
        persona_plan = generator.build_persona_generation_plan(profile, persona_id)
        generator.validate_persona_generation_plan(
            persona_plan,
            expected_profile=profile,
            expected_persona_id=persona_id,
        )
    except (generator.PersonaGenerationError, KeyError, TypeError, ValueError) as error:
        raise PersonaPrepareReceiptError(
            f"cannot rebuild canonical persona plan for {persona_id}"
        ) from error
    person = persona_plan["persona"]
    persona_plan_sha = _canonical_sha256(persona_plan)
    device_slug = person["device_slug"]
    scope_receipts = []
    scope_roots = []
    for ordinal, (scope, command) in enumerate(
        zip(person["scopes"], binding["scopes"], strict=True), start=1
    ):
        if scope["scope_key"] != command["scope_key"]:
            raise PersonaPrepareReceiptError("scope command binding substitution detected")
        scope_root = f"devices/{device_slug}/home/{scope['relative_path']}"
        scope_store = f"{scope_root}/{generator.SCOPE_STORE_DIRECTORY_NAME}"
        scope_roots.append(scope_root)
        role_counts = {
            role: sum(1 for source in scope["sources"] if source["gate_role"] == role)
            for role in manifest.GATE_ROLES
        }
        if sum(role_counts.values()) != scope["expected_physical_rows"]:
            raise PersonaPrepareReceiptError("scope gate-role source arithmetic drifted")
        scope_receipts.append({
            "schema": SCOPE_RECEIPT_SCHEMA,
            "schema_version": 1,
            "fixture_id": fixture_spec.FIXTURE_ID,
            "profile": profile,
            "replay_id": intent["replay_id"],
            "destination_root": intent["destination_root"],
            "persona_id": persona_id,
            "device_slug": device_slug,
            "scope_ordinal": ordinal,
            "scope_key": scope["scope_key"],
            "scope_relative_path": scope["relative_path"],
            "scope_root_relative_path": scope_root,
            "scope_store_relative_path": scope_store,
            "expected_physical_sources": scope["expected_physical_rows"],
            "expected_contract_contributor_chunks": scope["expected_contract_chunks"],
            "expected_source_counts_by_gate_role": role_counts,
            "generation_plan_sha256": intent["generation_plan_sha256"],
            "persona_plan_sha256": persona_plan_sha,
            "scope_contract_sha256": _scope_contract_sha256(
                profile=profile,
                persona_id=persona_id,
                persona_plan_sha256=persona_plan_sha,
                scope=scope,
            ),
            "root_binding_sha256": intent["root_binding_sha256"],
            "binary_identity_sha256": intent["binary_identity_sha256"],
            "environment_receipt_sha256": binding["environment_receipt_sha256"],
            "init_receipt_sha256": command["init_receipt_sha256"],
            "index_receipt_sha256": command["index_receipt_sha256"],
            "canonical_fixture_projection_complete": True,
            "semantic_evidence": _semantic_evidence("scope"),
            **_operational_false_claims(),
        })
    if len(scope_receipts) != EXPECTED_SCOPES_PER_PERSON:
        raise PersonaPrepareReceiptError("person receipt does not contain twenty scopes")
    device_receipt = {
        "schema": DEVICE_RECEIPT_SCHEMA,
        "schema_version": 1,
        "fixture_id": fixture_spec.FIXTURE_ID,
        "profile": profile,
        "replay_id": intent["replay_id"],
        "destination_root": intent["destination_root"],
        "persona_id": persona_id,
        "device_slug": device_slug,
        "device_state_relative_path": (
            f"devices/{device_slug}/{generator.DEVICE_STATE_DIRECTORY_NAME}"
        ),
        "expected_registry_rows": EXPECTED_SCOPES_PER_PERSON,
        "expected_scope_root_relative_paths": scope_roots,
        "generation_plan_sha256": intent["generation_plan_sha256"],
        "root_binding_sha256": intent["root_binding_sha256"],
        "binary_identity_sha256": intent["binary_identity_sha256"],
        "environment_receipt_sha256": binding["environment_receipt_sha256"],
        "canonical_fixture_projection_complete": True,
        "semantic_evidence": _semantic_evidence("device"),
        **_operational_false_claims(),
    }
    result = {
        "schema": PERSON_RECEIPT_SCHEMA,
        "schema_version": 1,
        "fixture_id": fixture_spec.FIXTURE_ID,
        "profile": profile,
        "replay_id": intent["replay_id"],
        "destination_root": intent["destination_root"],
        "persona_id": persona_id,
        "role": person["role"],
        "device_slug": device_slug,
        "expected_physical_sources": person["raw_file_count"],
        "expected_contract_contributor_chunks": person["planned_contract_chunks"],
        "generation_plan_sha256": intent["generation_plan_sha256"],
        "persona_plan_sha256": persona_plan_sha,
        "root_binding_sha256": intent["root_binding_sha256"],
        "binary_identity_sha256": intent["binary_identity_sha256"],
        "environment_receipt_sha256": binding["environment_receipt_sha256"],
        "person_command_binding_sha256": _canonical_sha256(binding),
        "device": device_receipt,
        "scopes": scope_receipts,
        "canonical_fixture_projection_complete": True,
        "semantic_evidence": _semantic_evidence("person"),
        **_operational_false_claims(),
    }
    del scope_receipts, scope_roots, person, persona_plan
    return result


def _person_binding_for(intent: dict, persona_id: str) -> dict:
    persona_id = _persona_id(persona_id)
    expected_ids = [persona["id"] for persona in fixture_spec.PERSONAS]
    ordinal = expected_ids.index(persona_id)
    binding = intent["person_command_bindings"][ordinal]
    if binding["persona_id"] != persona_id:
        raise PersonaPrepareReceiptError("person command binding order changed")
    return binding


def build_person_prepare_receipt(intent: dict, persona_id: str) -> dict:
    """Build one bounded person receipt without materializing the other nineteen."""
    intent = validate_prepare_receipt_intent(intent)
    return _build_person_receipt(intent, _person_binding_for(intent, persona_id))


def build_device_prepare_receipt(intent: dict, persona_id: str) -> dict:
    """Build the isolated-device projection for one person."""
    return build_person_prepare_receipt(intent, persona_id)["device"]


def build_scope_prepare_receipt(
    intent: dict, persona_id: str, scope_key: str
) -> dict:
    """Build one scope projection through its canonical one-person contract."""
    if type(scope_key) is not str or not scope_key:
        raise PersonaPrepareReceiptError("scope_key must be a non-empty string")
    person = build_person_prepare_receipt(intent, persona_id)
    matches = [scope for scope in person["scopes"] if scope["scope_key"] == scope_key]
    if len(matches) != 1:
        raise PersonaPrepareReceiptError("scope_key is not canonical for this person")
    return matches[0]


def _validate_exact_projection(value: object, expected: dict, label: str) -> dict:
    value = _exact_dict(value, set(expected), label)
    if value != expected or _canonical_bytes(value) != _canonical_bytes(expected):
        raise PersonaPrepareReceiptError(f"{label} is not canonical")
    return copy.deepcopy(expected)


def validate_person_prepare_receipt(value: object, intent: dict) -> dict:
    if type(value) is not dict or type(value.get("persona_id")) is not str:
        raise PersonaPrepareReceiptError("person prepare receipt is invalid")
    expected = build_person_prepare_receipt(intent, value["persona_id"])
    return _validate_exact_projection(value, expected, "person prepare receipt")


def validate_device_prepare_receipt(value: object, intent: dict) -> dict:
    if type(value) is not dict or type(value.get("persona_id")) is not str:
        raise PersonaPrepareReceiptError("device prepare receipt is invalid")
    expected = build_device_prepare_receipt(intent, value["persona_id"])
    return _validate_exact_projection(value, expected, "device prepare receipt")


def validate_scope_prepare_receipt(value: object, intent: dict) -> dict:
    if (
        type(value) is not dict
        or type(value.get("persona_id")) is not str
        or type(value.get("scope_key")) is not str
    ):
        raise PersonaPrepareReceiptError("scope prepare receipt is invalid")
    expected = build_scope_prepare_receipt(
        intent, value["persona_id"], value["scope_key"]
    )
    return _validate_exact_projection(value, expected, "scope prepare receipt")


def build_prepare_receipt(intent: dict) -> dict:
    """Build the compact root receipt, one canonical persona plan at a time."""
    intent = validate_prepare_receipt_intent(intent)
    people = []
    for binding in intent["person_command_bindings"]:
        people.append(_build_person_receipt(intent, binding))
    if len(people) != EXPECTED_PERSONAS:
        raise PersonaPrepareReceiptError("root receipt does not contain twenty people")
    scope_count = sum(len(person["scopes"]) for person in people)
    if scope_count != EXPECTED_SCOPE_STORES:
        raise PersonaPrepareReceiptError("root receipt does not contain 400 scopes")
    result = {
        "schema": ROOT_RECEIPT_SCHEMA,
        "schema_version": 1,
        "fixture_id": fixture_spec.FIXTURE_ID,
        "fixture_schema_version": fixture_spec.SCHEMA_VERSION,
        "profile": intent["profile"],
        "replay_id": intent["replay_id"],
        "destination_root": intent["destination_root"],
        "generation_plan_sha256": intent["generation_plan_sha256"],
        "root_binding_sha256": intent["root_binding_sha256"],
        "binary_identity_sha256": intent["binary_identity_sha256"],
        "history_prepare_intent_sha256": intent["history_prepare_intent_sha256"],
        "person_command_binding_root_sha256": intent[
            "person_command_binding_root_sha256"
        ],
        "prepare_receipt_intent": intent,
        "prepare_receipt_intent_sha256": _canonical_sha256(intent),
        "persons": people,
        "totals": {
            "personas": len(people),
            "scope_stores": scope_count,
            "device_states": len(people),
            "physical_sources": sum(
                person["expected_physical_sources"] for person in people
            ),
            "planned_contract_contributor_chunks": sum(
                person["expected_contract_contributor_chunks"] for person in people
            ),
        },
        "canonical_fixture_projection_complete": True,
        "semantic_evidence": _semantic_evidence("root"),
        **_operational_false_claims(),
    }
    if len(_canonical_bytes(result)) > MAX_ROOT_RECEIPT_BYTES:
        raise PersonaPrepareReceiptError("prepare root receipt exceeds its byte bound")
    return result


def validate_prepare_receipt(value: object) -> dict:
    fields = {
        "schema", "schema_version", "fixture_id", "fixture_schema_version",
        "profile", "replay_id", "destination_root", "generation_plan_sha256",
        "root_binding_sha256", "binary_identity_sha256",
        "history_prepare_intent_sha256", "person_command_binding_root_sha256",
        "prepare_receipt_intent",
        "prepare_receipt_intent_sha256", "persons", "totals",
        "canonical_fixture_projection_complete", "semantic_evidence",
        "filesystem_mutation_performed", "kio_commands_executed_by_this_module",
        "external_api_execution_performed", "history_ready_attested",
        "history_assignment_executable",
    }
    value = _exact_dict(value, fields, "prepare root receipt")
    if (
        type(value["persons"]) is not list
        or len(value["persons"]) != EXPECTED_PERSONAS
        or value["canonical_fixture_projection_complete"] is not True
        or value["semantic_evidence"] != _semantic_evidence("root")
        or any(
            value[field] is not False
            for field in (
                "filesystem_mutation_performed",
                "kio_commands_executed_by_this_module",
                "external_api_execution_performed",
                "history_ready_attested",
                "history_assignment_executable",
            )
        )
    ):
        raise PersonaPrepareReceiptError(
            "prepare root receipt cardinality or fixed claims differ"
        )
    expected = build_prepare_receipt(value["prepare_receipt_intent"])
    if value != expected or _canonical_bytes(value) != _canonical_bytes(expected):
        raise PersonaPrepareReceiptError("prepare root receipt is not canonical")
    return copy.deepcopy(expected)


def prepare_receipt_sha256(value: object) -> str:
    """Validate and hash one canonical root receipt without a storage LF."""
    return _canonical_sha256(validate_prepare_receipt(value))
