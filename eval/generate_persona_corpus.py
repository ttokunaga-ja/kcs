#!/usr/bin/env python3
"""Build and strictly verify the W0 persona-PC synthetic source corpus.

The writer intentionally supports only the ``tiny`` profile.  ``pilot`` and
``full`` plans are deterministic, but physical publication stays blocked
until streaming ledger publication and pilot-derived byte/inode limits exist.
Planned contract chunks in this module are never post-index KIO evidence.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys

try:  # Package imports and direct ``python eval/...`` execution.
    from . import persona_allocation as allocation
    from . import persona_fixture_spec as spec
    from . import persona_manifest as manifest
    from . import persona_renderers as renderers
    from . import persona_storage as storage
except ImportError:  # pragma: no cover - covered by direct-script smoke tests.
    import persona_allocation as allocation
    import persona_fixture_spec as spec
    import persona_manifest as manifest
    import persona_renderers as renderers
    import persona_storage as storage


PLAN_SCHEMA = "kio.persona.w0.generation-plan/v1"
PERSONA_GENERATION_PLAN_SCHEMA = (
    "kio.persona.w0.persona-generation-plan/v1"
)
PERSONA_MANIFEST_SCHEMA = "kio.persona.w0.persona/v1"
CAPACITY_RECEIPT_SCHEMA = "kio.persona.w0.capacity-receipt/v1"
ROOT_BINDING_SCHEMA = "kio.persona.w0.root-binding/v1"
HISTORY_PREPARE_INTENT_SCHEMA = "kio.persona.history-prepare-intent/v1"
RUNTIME_DIRECTORY_ATTESTATION_SCHEMA = (
    "kio.persona.runtime-directory-attestation/v1"
)
RUNTIME_ATTESTATION_ROOT_SCHEMA = "kio.persona.runtime-attestation-root/v1"
PLAN_FILE_NAME = "w0-plan.json"
SUITE_FILE_NAME = manifest.SUITE_MANIFEST_NAME
CAPACITY_FILE_NAME = "generation-capacity-receipt.json"
ROOT_BINDING_FILE_NAME = "w0-root-binding.json"
PERSONA_FILE_NAME = "persona-manifest.json"
MAX_PLAN_BYTES = 512 * 1024 * 1024
MAX_PERSONA_PLAN_SOURCES = 16_000
MAX_PERSONA_PLAN_BYTES = 8 * 1024 * 1024
PERSONA_PLAN_SCOPE_COUNT = 20
MAX_CAPACITY_RECEIPT_BYTES = 256 * 1024
CAPACITY_RECEIPT_BUDGET = 64 * 1024
ROOT_BINDING_BUDGET = 64 * 1024
MAX_HISTORY_PREPARE_DECLARED_FILE_BYTES = 8 * 1024 * 1024
MAX_HISTORY_PREPARE_DECLARED_FILES = 10_000
MAX_HISTORY_PREPARE_DECLARED_TOTAL_BYTES = 512 * 1024 * 1024
MAX_HISTORY_PREPARE_RELATIVE_PATH_BYTES = 1_024
MAX_HISTORY_PREPARE_PATH_COMPONENTS = 32

SCOPE_STORE_DIRECTORY_NAME = ".kio"
DEVICE_STATE_DIRECTORY_NAME = ".kio-eval-device"
HISTORY_PREPARE_RECEIPT_DIRECTORY = ".kio-persona-history/receipts"
HISTORY_PREPARE_CONTROL_DIRECTORY = ".kio-persona-history/control"
RUNTIME_SCOPE_STORE_SEMANTIC_CONTRACT = (
    "kio.persona.scope-store-history-ready/v1"
)
RUNTIME_DEVICE_STATE_SEMANTIC_CONTRACT = (
    "kio.persona.device-state-isolation/v1"
)
_HISTORY_WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{number}"
    for prefix in ("com", "lpt")
    for number in range(1, 10)
}

DEFAULT_TINY_BYTE_CAP = 2 * 1024 * 1024 * 1024
DEFAULT_TINY_INODE_CAP = 100_000
DEFAULT_RESERVE_BYTES = 512 * 1024 * 1024
DEFAULT_RESERVE_INODES = 10_000
WRITABLE_PROFILES = frozenset(("tiny",))
REPLAY_IDS = tuple(f"replay-{index:02d}" for index in range(1, spec.REPLAY_COUNT + 1))

_PROFILES = frozenset(("tiny", "pilot", "full"))
_PERSONA_GENERATION_PLAN_FIELDS = frozenset({
    "schema",
    "schema_version",
    "fixture_schema_version",
    "fixture_id",
    "seed",
    "profile",
    "replay_count",
    "renderer_id",
    "renderer_schema_version",
    "persona_id",
    "contracts",
    "persona",
})
_PERSONA_PROJECTION_FIELDS = frozenset({
    "persona_id",
    "role",
    "device_slug",
    "raw_file_count",
    "planned_contract_chunks",
    "format_percentages",
    "allocation",
    "scopes",
})
_PERSONA_PLAN_CONTRACTS = {
    "root_independent": True,
    "contains_absolute_paths": False,
    "contains_rendered_source_bytes": False,
    "source_expansion": "canonical_w0",
}


class PersonaGenerationError(RuntimeError):
    """Raised when planning, publication, or verification fails closed."""


def _require_physical_publication_platform():
    if os.name == "nt":
        raise PersonaGenerationError(
            "physical persona publication is blocked on Windows until "
            "directory-handle durability confirmation is implemented"
        )


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical_file_bytes(value):
    return manifest.canonical_json_bytes(value) + b"\n"


def generation_plan_sha256(plan):
    """Digest canonical JSON without the storage file's terminal LF."""
    return _sha256(manifest.canonical_json_bytes(plan))


def _variant_rows_in_order(allocation_plan, scope_key):
    return tuple(
        row for row in allocation_plan["assignments"]
        if row["scope_key"] == scope_key
    )


def _source_plan_for_persona(persona, profile, allocation_plan):
    source_number = 0
    scopes = []
    for scope in spec.scope_specs(persona):
        scope_key = scope["scope_key"]
        assignments = _variant_rows_in_order(allocation_plan, scope_key)
        contributor_files = sum(
            row["count"] for row in assignments
            if row["gate_role"] == "contract_contributor"
        )
        chunk_target = allocation_plan["scope_contributor_chunk_targets"][scope_key]
        if contributor_files <= 0:
            raise PersonaGenerationError(f"scope has no contributor file: {scope_key}")
        quotient, remainder = divmod(chunk_target, contributor_files)
        quotas = [quotient + (index < remainder) for index in range(contributor_files)]
        if (
            sum(quotas) != chunk_target
            or min(quotas) < 1
            or max(quotas) > spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE
        ):
            raise PersonaGenerationError(
                f"scope contributor quota cannot satisfy 1..72: {scope_key}"
            )
        quota_index = 0
        sources = []
        expected_variants = {
            variant: 0
            for variants in spec.FORMAT_VARIANTS.values()
            for variant, _weight, _gate, _disposition in variants
        }
        for assignment in assignments:
            extension, media_type = renderers.variant_output_contract(
                assignment["family"], assignment["variant"]
            )
            for _ in range(assignment["count"]):
                source_number += 1
                requested = 0
                if assignment["gate_role"] == "contract_contributor":
                    requested = quotas[quota_index]
                    quota_index += 1
                source_id = f"{persona['id']}-src-{source_number:06d}"
                file_name = spec.validate_source_basename(
                    f"{source_id}.{extension}"
                )
                sources.append({
                    "schema_version": spec.SCHEMA_VERSION,
                    "source_id": source_id,
                    "version": 0,
                    "family": assignment["family"],
                    "variant": assignment["variant"],
                    "gate_role": assignment["gate_role"],
                    "expected_disposition": assignment["expected_disposition"],
                    "extension": extension,
                    "media_type": media_type,
                    "file_name": file_name,
                    "requested_contributor_chunks": requested,
                })
                expected_variants[assignment["variant"]] += 1
        if quota_index != len(quotas):
            raise PersonaGenerationError(f"unused contributor quota: {scope_key}")
        expected_files = allocation_plan["scope_totals"][scope_key]
        if len(sources) != expected_files:
            raise PersonaGenerationError(f"scope source total drifted: {scope_key}")
        if sum(row["requested_contributor_chunks"] for row in sources) != chunk_target:
            raise PersonaGenerationError(f"scope chunk target drifted: {scope_key}")
        scopes.append({
            "scope_key": scope_key,
            "kind": scope["kind"],
            "relative_path": scope["relative_path"],
            "expected_physical_rows": expected_files,
            "expected_contract_chunks": chunk_target,
            "expected_variant_counts": expected_variants,
            "sources": sources,
        })
    expected_total = spec.raw_file_count(persona, profile)
    if source_number != expected_total:
        raise PersonaGenerationError(
            f"persona source ids are not exact: {persona['id']}"
        )
    return scopes


def _persona_projection(persona, profile):
    """Build the exact persona value embedded by the twenty-person plan."""
    allocation_plan = allocation.build_allocation_plan(persona, profile)
    allocation.validate_allocation_plan(allocation_plan, persona)
    scopes = _source_plan_for_persona(persona, profile, allocation_plan)
    return {
        "persona_id": persona["id"],
        "role": persona["role"],
        "device_slug": f"{persona['id']}-{persona['role']}",
        "raw_file_count": spec.raw_file_count(persona, profile),
        "planned_contract_chunks": spec.contributor_plan(persona, profile)[
            "target_chunks"
        ],
        "format_percentages": dict(persona["format_percentages"]),
        "allocation": allocation_plan,
        "scopes": scopes,
    }


def _build_generation_plan(profile):
    if profile not in _PROFILES:
        raise PersonaGenerationError(f"unknown persona profile: {profile!r}")
    people = [
        _persona_projection(persona, profile) for persona in spec.PERSONAS
    ]
    return {
        "schema": PLAN_SCHEMA,
        "schema_version": 1,
        "fixture_schema_version": spec.SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "seed": spec.SEED,
        "profile": profile,
        "replay_count": spec.REPLAY_COUNT,
        "renderer_id": renderers.RENDERER_ID,
        "renderer_schema_version": renderers.RENDERER_SCHEMA_VERSION,
        "personas": people,
        "totals": {
            "personas": len(people),
            "scope_shards": sum(len(person["scopes"]) for person in people),
            "physical_sources": sum(person["raw_file_count"] for person in people),
            "planned_contract_chunks": sum(
                person["planned_contract_chunks"] for person in people
            ),
        },
    }


def _canonical_persona(persona_id):
    if type(persona_id) is not str:
        raise PersonaGenerationError("persona id must be a canonical string")
    try:
        return spec.get_persona(persona_id)
    except KeyError as error:
        raise PersonaGenerationError(f"unknown persona id: {persona_id!r}") from error


def _persona_plan_source_count(plan):
    """Cheap structural bound checked before canonical serialization/rebuild."""
    if type(plan) is not dict or set(plan) != _PERSONA_GENERATION_PLAN_FIELDS:
        raise PersonaGenerationError(
            "persona generation plan has an invalid top-level field set"
        )
    person = plan.get("persona")
    if type(person) is not dict or set(person) != _PERSONA_PROJECTION_FIELDS:
        raise PersonaGenerationError(
            "persona generation plan has an invalid persona projection"
        )
    scopes = person.get("scopes")
    if type(scopes) is not list or len(scopes) != PERSONA_PLAN_SCOPE_COUNT:
        raise PersonaGenerationError(
            "persona generation plan must contain exactly 20 scopes"
        )
    source_count = 0
    for ordinal, scope in enumerate(scopes):
        if type(scope) is not dict or type(scope.get("sources")) is not list:
            raise PersonaGenerationError(
                f"persona scope {ordinal} has an invalid source inventory"
            )
        source_count += len(scope["sources"])
        if source_count > MAX_PERSONA_PLAN_SOURCES:
            raise PersonaGenerationError(
                "persona generation plan exceeds its 16000-source bound"
            )
    if (
        type(person.get("raw_file_count")) is not int
        or person["raw_file_count"] != source_count
    ):
        raise PersonaGenerationError(
            "persona generation plan source count differs from raw_file_count"
        )
    return source_count


def _bounded_persona_plan_bytes(plan):
    try:
        raw = canonical_file_bytes(plan)
    except (manifest.PersonaManifestError, TypeError, ValueError) as error:
        raise PersonaGenerationError(
            "persona generation plan is not canonical JSON"
        ) from error
    if len(raw) > MAX_PERSONA_PLAN_BYTES:
        raise PersonaGenerationError(
            "persona generation plan exceeds its 8 MiB canonical-byte bound"
        )
    return raw


def _build_persona_generation_plan(profile, persona_id):
    if type(profile) is not str or profile not in _PROFILES:
        raise PersonaGenerationError(f"unknown persona profile: {profile!r}")
    persona = _canonical_persona(persona_id)
    person = _persona_projection(persona, profile)
    plan = {
        "schema": PERSONA_GENERATION_PLAN_SCHEMA,
        "schema_version": 1,
        "fixture_schema_version": spec.SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "seed": spec.SEED,
        "profile": profile,
        "replay_count": spec.REPLAY_COUNT,
        "renderer_id": renderers.RENDERER_ID,
        "renderer_schema_version": renderers.RENDERER_SCHEMA_VERSION,
        "persona_id": persona_id,
        "contracts": dict(_PERSONA_PLAN_CONTRACTS),
        "persona": person,
    }
    _persona_plan_source_count(plan)
    _bounded_persona_plan_bytes(plan)
    return plan


def build_persona_generation_plan(profile, persona_id):
    """Return one bounded canonical W0 persona plan without building all 20.

    ``plan["persona"]`` is byte-for-byte and value-for-value identical to the
    matching element of ``build_generation_plan(profile)["personas"]``.  The
    wrapper binds that projection to its fixture, profile, renderer, and
    persona identity while remaining independent of a replay root.
    """
    return _build_persona_generation_plan(profile, persona_id)


def validate_persona_generation_plan(
    plan, *, expected_profile=None, expected_persona_id=None
):
    """Require an exact canonical rebuild of one bounded persona plan.

    Callers that already know the shard identity should pass both expected
    values.  This rejects substitution by a different otherwise-canonical
    persona/profile wrapper before it reaches a streaming worker.
    """
    _persona_plan_source_count(plan)
    actual_raw = _bounded_persona_plan_bytes(plan)
    profile = plan.get("profile")
    persona_id = plan.get("persona_id")
    if expected_profile is not None:
        if type(expected_profile) is not str or profile != expected_profile:
            raise PersonaGenerationError(
                "persona generation plan profile differs from the expected profile"
            )
    if expected_persona_id is not None:
        if (
            type(expected_persona_id) is not str
            or persona_id != expected_persona_id
        ):
            raise PersonaGenerationError(
                "persona generation plan identity differs from the expected persona"
            )
    expected = _build_persona_generation_plan(profile, persona_id)
    expected_raw = _bounded_persona_plan_bytes(expected)
    if plan != expected or actual_raw != expected_raw:
        raise PersonaGenerationError(
            "persona generation plan differs from canonical expansion"
        )
    return plan


def persona_event_plan_projection(
    plan, *, expected_profile=None, expected_persona_id=None
):
    """Return the exact validated input expected by the event planner."""
    validated = validate_persona_generation_plan(
        plan,
        expected_profile=expected_profile,
        expected_persona_id=expected_persona_id,
    )
    person = validated["persona"]
    return {
        "persona_id": person["persona_id"],
        "planned_contract_chunks": person["planned_contract_chunks"],
        "scopes": copy.deepcopy(person["scopes"]),
    }


def build_generation_plan(profile):
    """Return the root-independent exact plan for all twenty synthetic PCs."""
    plan = _build_generation_plan(profile)
    validate_generation_plan(plan)
    return plan


def validate_generation_plan(plan):
    """Require exact equality with the canonical allocator/source expansion."""
    if type(plan) is not dict or plan.get("profile") not in ("tiny", "pilot", "full"):
        raise PersonaGenerationError("generation plan has an invalid profile/header")
    expected = _build_generation_plan(plan["profile"])
    if (
        plan != expected
        or manifest.canonical_json_bytes(plan)
        != manifest.canonical_json_bytes(expected)
    ):
        raise PersonaGenerationError("generation plan differs from canonical expansion")
    return plan


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PersonaGenerationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_noninteger(value):
    raise PersonaGenerationError(f"non-integer JSON value is forbidden: {value}")


def _read_plain_file(path, maximum, label):
    path = Path(path)
    before = path.lstat()
    if (
        not storage.is_plain_regular_file_metadata(before)
        or path.is_symlink()
        or before.st_nlink != 1
    ):
        raise PersonaGenerationError(f"{label} must be a single-link plain file")
    if before.st_size > maximum:
        raise PersonaGenerationError(f"{label} exceeds {maximum} bytes")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise PersonaGenerationError(f"{label} changed while opening")
        raw = handle.read(maximum + 1)
    after = path.lstat()
    if (
        len(raw) > maximum
        or not storage.is_plain_regular_file_metadata(after)
        or after.st_nlink != 1
        or (after.st_dev, after.st_ino, after.st_size)
        != (opened.st_dev, opened.st_ino, opened.st_size)
    ):
        raise PersonaGenerationError(f"{label} changed or exceeded its bound")
    return raw


def _decode_canonical_json(raw, label):
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_noninteger,
            parse_constant=_reject_noninteger,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PersonaGenerationError(f"{label} is invalid JSON") from error
    if canonical_file_bytes(value) != raw:
        raise PersonaGenerationError(f"{label} is not canonical JSON")
    return value


def load_generation_plan(path):
    plan = _decode_canonical_json(
        _read_plain_file(path, MAX_PLAN_BYTES, "generation plan"),
        "generation plan",
    )
    return validate_generation_plan(plan)


def write_generation_plan(path, profile, *, repo_root=None):
    """Create a plan with no-replace semantics; identical existing is a no-op."""
    plan = build_generation_plan(profile)
    raw = canonical_file_bytes(plan)
    destination = Path(path).absolute()
    repository = Path(
        Path(__file__).parents[1] if repo_root is None else repo_root
    ).absolute()
    repository_spellings = {repository, repository.resolve(strict=False)}
    if any(
        destination == spelling or spelling in destination.parents
        for spelling in repository_spellings
    ):
        raise PersonaGenerationError("generation plans must remain outside Git")
    try:
        existing = destination.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if _read_plain_file(destination, MAX_PLAN_BYTES, "generation plan") != raw:
            raise PersonaGenerationError("refusing to replace a different plan")
        load_generation_plan(destination)
        return plan, False
    storage.atomic_create_directory(destination.parent, parents=True)
    storage.atomic_write_file(destination, raw)
    return plan, True


def _source_request(persona_id, scope_key, source):
    return renderers.SourceRequest(
        schema_version=source["schema_version"],
        persona_id=persona_id,
        scope_key=scope_key,
        source_id=source["source_id"],
        version=source["version"],
        family=source["family"],
        variant=source["variant"],
        requested_contributor_chunks=source["requested_contributor_chunks"],
    )


def _rows_for_rendered(persona_id, scope, source, rendered):
    if (
        rendered.extension != source["extension"]
        or rendered.media_type != source["media_type"]
        or rendered.renderer_id != renderers.RENDERER_ID
        or rendered.renderer_schema_version != renderers.RENDERER_SCHEMA_VERSION
        or rendered.planned_contract_chunks
        != source["requested_contributor_chunks"]
    ):
        raise PersonaGenerationError(
            f"renderer metadata differs from plan: {source['source_id']}"
        )
    file_name = spec.validate_source_basename(source["file_name"])
    relative_path = f"{scope['relative_path']}/{file_name}"
    physical = {
        "source_id": source["source_id"],
        "persona_id": persona_id,
        "scope_key": scope["scope_key"],
        "relative_path": relative_path,
        "file_name": file_name,
        "format_family": source["family"],
        "extension": rendered.extension,
        "variant": source["variant"],
        "media_type": rendered.media_type,
        "raw_sha256": _sha256(rendered.data),
        "bytes": len(rendered.data),
        "logical_members": len(rendered.logical_members),
        "renderer_id": rendered.renderer_id,
        "renderer_schema_version": rendered.renderer_schema_version,
        "expected_contract_chunks": rendered.planned_contract_chunks,
        "expected_disposition": source["expected_disposition"],
        "gate_role": source["gate_role"],
    }
    logical = []
    for member in rendered.logical_members:
        logical.append({
            "source_id": source["source_id"],
            "persona_id": persona_id,
            "scope_key": scope["scope_key"],
            "unit_index": member.ordinal,
            "unit_kind": member.kind,
            "unit_key": f"{source['source_id']}:{member.unit_key}",
            "parent_unit_key": None,
            "planned_contract_chunks": member.planned_contract_chunks,
        })
    planned_keys = sorted(
        row["unit_key"] for row in logical
        if row["planned_contract_chunks"] > 0
    )
    searchable = {
        "source_id": source["source_id"],
        "persona_id": persona_id,
        "scope_key": scope["scope_key"],
        "gate_role": source["gate_role"],
        "expected_disposition": source["expected_disposition"],
        "planned_contract_chunks": rendered.planned_contract_chunks,
        "planned_unit_keys": planned_keys,
        "actual_chunk_policy": manifest.ACTUAL_CHUNK_POLICY_BY_ROLE[
            source["gate_role"]
        ],
    }
    return physical, logical, searchable


def materialize_source(persona_id, scope, source):
    """Render one planned source and return its complete immutable projection.

    W0 generation and the history-event planner share this boundary so a
    versioned event cannot silently use different renderer or ledger rules.
    The caller still owns canonical source allocation; this helper validates
    the renderer request and the source's declared output contract.
    """
    request = _source_request(persona_id, scope["scope_key"], source)
    rendered = renderers.render_source(request)
    physical, logical, searchable = _rows_for_rendered(
        persona_id, scope, source, rendered
    )
    return {
        "source": source,
        "request": request,
        "rendered": rendered,
        "physical": physical,
        "logical": tuple(logical),
        "searchable": searchable,
    }


def materialize_structural_source(
    persona_id, scope, source, *, parent_materializations=()
):
    """Render one structural source from its typed parent-bound contract.

    Canonical creates still use the ordinary renderer.  Near/derived sources
    must flow through this dispatcher so a new source ID cannot be mistaken
    for a machine-verifiable transform of its declared parent bytes.
    """
    contract = source.get("render_contract")
    if type(contract) is not dict or set(contract) != {
        "kind", "parent_source_ids"
    }:
        raise PersonaGenerationError("structural render contract is invalid")
    kind = contract["kind"]
    parent_ids = contract["parent_source_ids"]
    if type(kind) is not str or type(parent_ids) is not list or any(
        type(value) is not str for value in parent_ids
    ):
        raise PersonaGenerationError("structural render contract is untyped")
    if len(set(parent_ids)) != len(parent_ids):
        raise PersonaGenerationError("structural render parents are duplicated")
    parents = list(parent_materializations)
    if any(type(parent) is not dict for parent in parents):
        raise PersonaGenerationError("structural parent materialization is invalid")
    actual_parent_ids = [parent["source"]["source_id"] for parent in parents]
    if actual_parent_ids != parent_ids:
        raise PersonaGenerationError("structural render parents differ from contract")

    if kind == "canonical-source/v1":
        if parents:
            raise PersonaGenerationError("canonical structural source has a parent")
        result = materialize_source(persona_id, scope, source)
        return {
            **result,
            "render_contract": contract,
            "transform_witness": None,
        }
    if len(parents) != 1:
        raise PersonaGenerationError("structural transform requires exactly one parent")
    parent = parents[0]
    request = _source_request(persona_id, scope["scope_key"], source)
    try:
        if kind == "near-png-one-channel/v1":
            rendered, witness = renderers.render_near_png(
                parent["rendered"].data, request
            )
        elif kind == "png-to-scan-pdf/v1":
            rendered, witness = renderers.render_scan_pdf_from_png(
                parent["rendered"].data, request
            )
        else:
            raise PersonaGenerationError(
                f"unknown structural render contract: {kind!r}"
            )
    except renderers.RendererContractError as error:
        raise PersonaGenerationError(str(error)) from error
    physical, logical, searchable = _rows_for_rendered(
        persona_id, scope, source, rendered
    )
    if (
        witness.get("kind") != kind
        or witness.get("parent_raw_sha256")
        != parent["physical"]["raw_sha256"]
        or witness.get("child_raw_sha256") != physical["raw_sha256"]
    ):
        raise PersonaGenerationError("structural transform witness is inconsistent")
    return {
        "source": source,
        "request": request,
        "rendered": rendered,
        "physical": physical,
        "logical": tuple(logical),
        "searchable": searchable,
        "render_contract": contract,
        "transform_witness": witness,
    }


def _persona_manifest(person, profile):
    persona = spec.get_persona(person["persona_id"])
    return {
        "schema": PERSONA_MANIFEST_SCHEMA,
        "schema_version": 1,
        "fixture_id": spec.FIXTURE_ID,
        "profile": profile,
        "persona_id": person["persona_id"],
        "role": person["role"],
        "device_slug": person["device_slug"],
        "home_relative_path": "home",
        "scope_count": len(person["scopes"]),
        "raw_file_count": person["raw_file_count"],
        "planned_contract_chunks": person["planned_contract_chunks"],
        "format_percentages": persona["format_percentages"],
        "format_file_counts": spec.format_file_counts(persona, profile),
        "scopes": [
            {
                "scope_key": scope["scope_key"],
                "kind": scope["kind"],
                "relative_path": scope["relative_path"],
                "physical_sources": scope["expected_physical_rows"],
                "planned_contract_chunks": scope["expected_contract_chunks"],
                "sources_by_variant": scope["expected_variant_counts"],
            }
            for scope in person["scopes"]
        ],
    }


def prepare_w0_suite(plan):
    """Render the bounded corpus and build all immutable W0 projections."""
    validate_generation_plan(plan)
    profile = plan["profile"]
    if profile not in WRITABLE_PROFILES:
        raise PersonaGenerationError(
            f"{profile} physical generation is blocked: run tiny, then add "
            "streaming/RSS and pilot-derived capacity gates"
        )
    plan_sha256 = generation_plan_sha256(plan)
    shard_manifests = []
    validated_shards = []
    shards = []
    source_entries = []
    persona_manifests = {}
    for person in plan["personas"]:
        persona_id = person["persona_id"]
        persona_manifests[persona_id] = _persona_manifest(person, profile)
        for scope in person["scopes"]:
            physical_rows = []
            logical_rows = []
            searchable_rows = []
            sizes = []
            for source in scope["sources"]:
                materialized = materialize_source(persona_id, scope, source)
                rendered = materialized["rendered"]
                physical = materialized["physical"]
                logical = materialized["logical"]
                searchable = materialized["searchable"]
                physical_rows.append(physical)
                logical_rows.extend(logical)
                searchable_rows.append(searchable)
                sizes.append(len(rendered.data))
                source_entries.append({
                    "person": person,
                    "scope": scope,
                    **materialized,
                })
            storage.check_scope_limits(sizes)
            scope_manifest, validated = manifest.build_w0_scope_manifest(
                physical_rows,
                logical_rows,
                searchable_rows,
                fixture_id=spec.FIXTURE_ID,
                profile=profile,
                persona_id=persona_id,
                scope_key=scope["scope_key"],
                plan_sha256=plan_sha256,
                expected_contract_chunks=scope["expected_contract_chunks"],
                expected_physical_rows=scope["expected_physical_rows"],
                expected_variant_counts=scope["expected_variant_counts"],
            )
            # Manifest validation alone accepts a same-marginal cross-scope
            # swap.  Bind every cell back to the canonical allocation here.
            if (
                scope_manifest["totals"]["sources_by_variant"]
                != scope["expected_variant_counts"]
            ):
                raise PersonaGenerationError(
                    f"scope variant cell differs from plan: {scope['scope_key']}"
                )
            shard_manifests.append(scope_manifest)
            validated_shards.append(validated)
            shards.append({
                "person": person,
                "scope": scope,
                "manifest": scope_manifest,
                "validated": validated,
            })
    suite_manifest = manifest.build_w0_suite_manifest(
        fixture_id=spec.FIXTURE_ID,
        profile=profile,
        plan_sha256=plan_sha256,
        shard_manifests=shard_manifests,
        validated_shards=validated_shards,
    )
    if suite_manifest["totals"] != {
        "personas": plan["totals"]["personas"],
        "scope_shards": plan["totals"]["scope_shards"],
        "physical_sources": plan["totals"]["physical_sources"],
        "logical_items": suite_manifest["totals"]["logical_items"],
        "planned_contract_chunks": plan["totals"]["planned_contract_chunks"],
    }:
        raise PersonaGenerationError("suite totals differ from the generation plan")
    suite_file = canonical_file_bytes(suite_manifest)
    return {
        "plan": plan,
        "plan_sha256": plan_sha256,
        "plan_file": canonical_file_bytes(plan),
        "suite_manifest": suite_manifest,
        "suite_file": suite_file,
        "suite_manifest_sha256": _sha256(suite_file),
        "persona_manifests": persona_manifests,
        "shards": tuple(shards),
        "source_entries": tuple(source_entries),
    }


def _add_directory_with_parents(directories, relative_path):
    path = PurePosixPath(relative_path)
    current = PurePosixPath()
    for component in path.parts:
        current /= component
        directories.add(str(current))


def _expected_layout(prepared, *, ready):
    files = {
        PLAN_FILE_NAME,
        SUITE_FILE_NAME,
        CAPACITY_FILE_NAME,
        ROOT_BINDING_FILE_NAME,
        storage.STAGING_OWNER_MARKER_NAME,
    }
    if ready:
        files.add(storage.OWNER_MARKER_NAME)
    directories = {
        "devices",
        "ledgers",
        storage.NOREPLACE_PROBE_SOURCE,
        storage.NOREPLACE_PROBE_DESTINATION,
    }
    for person in prepared["plan"]["personas"]:
        device = f"devices/{person['device_slug']}"
        _add_directory_with_parents(directories, device)
        _add_directory_with_parents(directories, f"{device}/home")
        files.add(f"{device}/{PERSONA_FILE_NAME}")
        _add_directory_with_parents(directories, f"ledgers/{person['persona_id']}")
        for scope in person["scopes"]:
            _add_directory_with_parents(
                directories, f"{device}/home/{scope['relative_path']}"
            )
            shard = f"ledgers/{person['persona_id']}/{scope['scope_key']}"
            _add_directory_with_parents(directories, shard)
            files.update({
                f"{shard}/{manifest.PHYSICAL_LEDGER_NAME}",
                f"{shard}/{manifest.LOGICAL_LEDGER_NAME}",
                f"{shard}/{manifest.SEARCHABLE_LEDGER_NAME}",
                f"{shard}/{manifest.SCOPE_MANIFEST_NAME}",
            })
            for source in scope["sources"]:
                files.add(
                    f"{device}/home/{scope['relative_path']}/{source['file_name']}"
                )
    return files, directories


def _history_prepare_runtime_directories(plan):
    scope_stores = []
    device_states = []
    for person in plan["personas"]:
        device = f"devices/{person['device_slug']}"
        device_states.append(f"{device}/{DEVICE_STATE_DIRECTORY_NAME}")
        for scope in person["scopes"]:
            scope_stores.append(
                f"{device}/home/{scope['relative_path']}/"
                f"{SCOPE_STORE_DIRECTORY_NAME}"
            )
    return tuple(scope_stores), tuple(device_states)


def _validate_prepare_relative_file_path(relative_path, label):
    if type(relative_path) is not str or not relative_path:
        raise PersonaGenerationError(f"{label} path must be a non-empty string")
    try:
        encoded = relative_path.encode("ascii")
    except UnicodeEncodeError as error:
        raise PersonaGenerationError(f"{label} path must be ASCII") from error
    if len(encoded) > MAX_HISTORY_PREPARE_RELATIVE_PATH_BYTES:
        raise PersonaGenerationError(f"{label} path exceeds its byte bound")
    path = PurePosixPath(relative_path)
    if (
        path.is_absolute()
        or str(path) != relative_path
        or not path.parts
        or len(path.parts) > MAX_HISTORY_PREPARE_PATH_COMPONENTS
    ):
        raise PersonaGenerationError(
            f"{label} path is not canonical relative POSIX"
        )
    forbidden = '<>:"\\|?*'
    for component in path.parts:
        if (
            not component
            or component in (".", "..")
            or component.endswith((".", " "))
            or any(character in forbidden for character in component)
            or any(ord(character) < 32 or ord(character) == 127 for character in component)
        ):
            raise PersonaGenerationError(
                f"{label} path has a non-portable component"
            )
        stem = component.split(".", 1)[0].casefold()
        if stem in _HISTORY_WINDOWS_RESERVED:
            raise PersonaGenerationError(
                f"{label} path has a Windows-reserved component"
            )
        if component.casefold() in {
            SCOPE_STORE_DIRECTORY_NAME.casefold(),
            DEVICE_STATE_DIRECTORY_NAME.casefold(),
        }:
            raise PersonaGenerationError(
                f"{label} path enters an opaque managed directory"
            )
    return relative_path


def _validate_prepare_declared_file(row, label):
    if type(row) is not dict or set(row) != {
        "relative_path", "raw_sha256", "bytes"
    }:
        raise PersonaGenerationError(f"{label} descriptor has an invalid field set")
    relative_path = _validate_prepare_relative_file_path(
        row["relative_path"], label
    )
    raw_sha256 = row["raw_sha256"]
    byte_length = row["bytes"]
    if (
        type(raw_sha256) is not str
        or len(raw_sha256) != 64
        or any(character not in "0123456789abcdef" for character in raw_sha256)
        or type(byte_length) is not int
        or not 0 <= byte_length <= MAX_HISTORY_PREPARE_DECLARED_FILE_BYTES
    ):
        raise PersonaGenerationError(f"{label} descriptor is not bounded and typed")
    return {
        "relative_path": relative_path,
        "raw_sha256": raw_sha256,
        "bytes": byte_length,
    }


def _canonical_prepare_declared_files(rows, label, allowed_directory):
    if type(rows) not in (list, tuple):
        raise PersonaGenerationError(f"{label} descriptors must be a list")
    if len(rows) > MAX_HISTORY_PREPARE_DECLARED_FILES:
        raise PersonaGenerationError(f"{label} descriptor count exceeds its bound")
    canonical = [
        _validate_prepare_declared_file(row, label) for row in rows
    ]
    allowed = PurePosixPath(allowed_directory)
    if any(
        allowed not in PurePosixPath(row["relative_path"]).parents
        for row in canonical
    ):
        raise PersonaGenerationError(
            f"{label} path is outside its canonical namespace"
        )
    canonical.sort(key=lambda row: row["relative_path"])
    paths = [row["relative_path"] for row in canonical]
    if len(paths) != len(set(paths)) or len(paths) != len({path.casefold() for path in paths}):
        raise PersonaGenerationError(f"{label} paths are duplicated")
    return canonical


def _validate_declared_prepare_location_set(plan, receipt_files, control_files):
    combined = [*receipt_files, *control_files]
    if (
        len(combined) > MAX_HISTORY_PREPARE_DECLARED_FILES
        or sum(row["bytes"] for row in combined)
        > MAX_HISTORY_PREPARE_DECLARED_TOTAL_BYTES
    ):
        raise PersonaGenerationError(
            "history prepare declared files exceed their aggregate bound"
        )
    paths = [row["relative_path"] for row in combined]
    if (
        len(paths) != len(set(paths))
        or len(paths) != len({path.casefold() for path in paths})
    ):
        raise PersonaGenerationError(
            "history prepare receipt/control paths overlap"
        )
    immutable_files, immutable_directories = _expected_layout(
        {"plan": plan}, ready=True
    )
    scope_stores, device_states = _history_prepare_runtime_directories(plan)
    opaque_directories = set(scope_stores) | set(device_states)
    protected_subtrees = {
        "ledgers",
        storage.NOREPLACE_PROBE_SOURCE,
        storage.NOREPLACE_PROBE_DESTINATION,
    } | {
        f"devices/{person['device_slug']}/home"
        for person in plan["personas"]
    }
    occupied = immutable_files | immutable_directories | opaque_directories
    occupied_folded = {path.casefold() for path in occupied}
    declared_paths = set(paths)
    inferred_directories = set()
    for relative_path in paths:
        relative = PurePosixPath(relative_path)
        if any(
            relative_path == protected
            or PurePosixPath(protected) in relative.parents
            for protected in protected_subtrees
        ):
            raise PersonaGenerationError(
                "history prepare declared file enters protected W0 content"
            )
        if relative_path.casefold() in occupied_folded:
            raise PersonaGenerationError(
                "history prepare declared file overlaps the W0/runtime layout"
            )
        for parent in relative.parents:
            if str(parent) == ".":
                continue
            parent_path = str(parent)
            if parent_path in immutable_files:
                raise PersonaGenerationError(
                    "history prepare declared parent is an immutable file"
                )
            if any(
                parent_path == opaque
                or PurePosixPath(opaque) in PurePosixPath(parent_path).parents
                for opaque in opaque_directories
            ):
                raise PersonaGenerationError(
                    "history prepare declared file enters opaque runtime state"
                )
            inferred_directories.add(parent_path)
    inferred_folded = {value.casefold() for value in inferred_directories}
    if any(path.casefold() in inferred_folded for path in declared_paths):
        raise PersonaGenerationError(
            "history prepare declared file is another declaration's directory"
        )
    all_spellings = occupied | declared_paths | inferred_directories
    if len(all_spellings) != len({path.casefold() for path in all_spellings}):
        # Exact overlap with an existing directory is expected for inferred
        # ancestors; only differently-cased spellings are ambiguous.  Collapse
        # exact duplicates before making that comparison.
        folded_spellings = {}
        for path in all_spellings:
            previous = folded_spellings.setdefault(path.casefold(), path)
            if previous != path:
                raise PersonaGenerationError(
                    "history prepare paths have a case-insensitive collision"
                )
    return inferred_directories


def build_history_prepare_intent(
    plan,
    replay_id,
    *,
    receipt_files=(),
    control_files=(),
):
    """Build a root-independent, read-only W0 runtime-envelope intent.

    Receipt/control descriptors bind an exact root-relative plain file by
    byte length and SHA-256.  They may not be placed inside either opaque KIO
    runtime directory.  This function plans no mutation and runs no KIO
    subprocess.
    """
    validate_generation_plan(plan)
    if replay_id not in REPLAY_IDS:
        raise PersonaGenerationError(f"invalid replay id: {replay_id!r}")
    receipts = _canonical_prepare_declared_files(
        receipt_files,
        "prepare receipt",
        HISTORY_PREPARE_RECEIPT_DIRECTORY,
    )
    controls = _canonical_prepare_declared_files(
        control_files,
        "prepare control",
        HISTORY_PREPARE_CONTROL_DIRECTORY,
    )
    _validate_declared_prepare_location_set(plan, receipts, controls)
    scope_stores, device_states = _history_prepare_runtime_directories(plan)
    return {
        "schema": HISTORY_PREPARE_INTENT_SCHEMA,
        "schema_version": 1,
        "fixture_id": spec.FIXTURE_ID,
        "profile": plan["profile"],
        "replay_id": replay_id,
        "plan_sha256": generation_plan_sha256(plan),
        "scope_store_directories": list(scope_stores),
        "device_state_directories": list(device_states),
        "receipt_files": receipts,
        "control_files": controls,
    }


def validate_history_prepare_intent(plan, replay_id, prepare_intent):
    """Require exact equality with the canonical W0 prepare intent."""
    if type(prepare_intent) is not dict or set(prepare_intent) != {
        "schema", "schema_version", "fixture_id", "profile", "replay_id",
        "plan_sha256", "scope_store_directories", "device_state_directories",
        "receipt_files", "control_files",
    }:
        raise PersonaGenerationError("history prepare intent is missing or invalid")
    expected = build_history_prepare_intent(
        plan,
        replay_id,
        receipt_files=prepare_intent["receipt_files"],
        control_files=prepare_intent["control_files"],
    )
    if (
        prepare_intent != expected
        or manifest.canonical_json_bytes(prepare_intent)
        != manifest.canonical_json_bytes(expected)
    ):
        raise PersonaGenerationError(
            "history prepare intent differs from canonical expansion"
        )
    # Return the detached canonical reconstruction, never the caller-owned
    # mutable object that was just compared.
    return expected


def _immutable_metadata_bytes(prepared):
    total = len(prepared["plan_file"]) + len(prepared["suite_file"])
    total += sum(
        len(canonical_file_bytes(value))
        for value in prepared["persona_manifests"].values()
    )
    for shard in prepared["shards"]:
        validated = shard["validated"]
        total += len(canonical_file_bytes(shard["manifest"]))
        total += len(manifest.canonical_jsonl_bytes(validated["physical_raw"]))
        total += len(manifest.canonical_jsonl_bytes(validated["logical_items"]))
        total += len(
            manifest.canonical_jsonl_bytes(validated["searchable_expectations"])
        )
    return total


def _filesystem_allocation_unit(path):
    path = Path(path)
    try:
        values = os.statvfs(path)
        unit = int(values.f_frsize or values.f_bsize)
    except (AttributeError, OSError):
        unit = int(getattr(path.lstat(), "st_blksize", 4096) or 4096)
    if not 512 <= unit <= 1024 * 1024:
        raise PersonaGenerationError(
            f"filesystem allocation unit is outside the safe bound: {unit}"
        )
    return unit


def _capacity_plan(prepared, filesystem_allocation_unit_bytes=4096):
    raw_bytes = sum(
        len(entry["rendered"].data) for entry in prepared["source_entries"]
    )
    logical_members = sum(
        len(entry["rendered"].logical_members)
        for entry in prepared["source_entries"]
    )
    ready_files, directories = _expected_layout(prepared, ready=True)
    # Include the root inode itself.  The receipt budget is an upper bound so
    # capacity computation stays non-circular while remaining conservative.
    inodes = 1 + len(ready_files) + len(directories)
    if (
        type(filesystem_allocation_unit_bytes) is not int
        or not 512 <= filesystem_allocation_unit_bytes <= 1024 * 1024
    ):
        raise PersonaGenerationError("invalid filesystem allocation unit")
    allocation_overhead = inodes * filesystem_allocation_unit_bytes
    metadata_bytes = (
        _immutable_metadata_bytes(prepared)
        + CAPACITY_RECEIPT_BUDGET
        + ROOT_BINDING_BUDGET
    )
    inputs = storage.CapacityInputs(
        physical_files=prepared["plan"]["totals"]["physical_sources"],
        logical_members=logical_members,
        current_chunks=prepared["plan"]["totals"]["planned_contract_chunks"],
        history_only_chunks=0,
        raw_bytes=raw_bytes,
        cas_bytes=0,
        index_bytes=metadata_bytes,
        inodes=inodes,
        staging_peak_bytes=raw_bytes + metadata_bytes + allocation_overhead,
        staging_peak_inodes=inodes,
        filesystem_allocation_unit_bytes=filesystem_allocation_unit_bytes,
        allocation_overhead_bytes=allocation_overhead,
        replay_count=spec.REPLAY_COUNT,
        profile=prepared["plan"]["profile"],
    )
    return storage.project_capacity(inputs)


def _capacity_receipt(
    prepared,
    destination,
    replay_id,
    *,
    byte_cap,
    inode_cap,
    reserve_bytes,
    reserve_inodes,
    explicit_free_inodes=None,
):
    availability = storage.probe_available_capacity(
        destination, explicit_free_inodes=explicit_free_inodes
    )
    allocation_unit = _filesystem_allocation_unit(availability.probe_path)
    plan = _capacity_plan(prepared, allocation_unit)
    limits = storage.CapacityLimits(
        byte_cap=byte_cap,
        inode_cap=inode_cap,
        reserve_bytes=reserve_bytes,
        reserve_inodes=reserve_inodes,
    )
    check = storage.check_capacity(plan, availability, limits)
    probe_metadata = availability.probe_path.lstat()
    if not storage.is_plain_directory_metadata(probe_metadata):
        raise PersonaGenerationError("capacity probe is not a plain directory")
    receipt = {
        "schema": CAPACITY_RECEIPT_SCHEMA,
        "schema_version": 1,
        "fixture_id": spec.FIXTURE_ID,
        "profile": prepared["plan"]["profile"],
        "replay_id": replay_id,
        "destination_root": str(Path(destination).absolute()),
        "filesystem_device": probe_metadata.st_dev,
        "filesystem_allocation_unit_bytes": allocation_unit,
        "plan_sha256": prepared["plan_sha256"],
        "suite_manifest_sha256": prepared["suite_manifest_sha256"],
        "capacity_plan_sha256": storage.capacity_plan_sha256(plan),
        "capacity_plan": plan.as_dict(),
        "limits": asdict(limits),
        "availability": {
            "free_bytes": availability.free_bytes,
            "free_inodes": availability.free_inodes,
            "probe_path": str(availability.probe_path),
            "inode_source": availability.inode_source,
        },
        "check": asdict(check),
        "planned_not_attested": True,
    }
    if len(canonical_file_bytes(receipt)) > CAPACITY_RECEIPT_BUDGET:
        raise PersonaGenerationError("capacity receipt exceeded its reserved budget")
    return receipt


def _validate_capacity_receipt(
    prepared,
    receipt,
    replay_id,
    *,
    expected_destination,
    filesystem_path,
    expected_limits=None,
):
    if type(receipt) is not dict or set(receipt) != {
        "schema", "schema_version", "fixture_id", "profile", "replay_id",
        "destination_root", "filesystem_device",
        "filesystem_allocation_unit_bytes", "plan_sha256",
        "suite_manifest_sha256", "capacity_plan_sha256",
        "capacity_plan", "limits", "availability", "check",
        "planned_not_attested",
    }:
        raise PersonaGenerationError("capacity receipt has an invalid field set")
    allocation_unit = receipt.get("filesystem_allocation_unit_bytes")
    expected_plan = _capacity_plan(prepared, allocation_unit)
    if (
        receipt["schema"] != CAPACITY_RECEIPT_SCHEMA
        or receipt["schema_version"] != 1
        or receipt["fixture_id"] != spec.FIXTURE_ID
        or receipt["profile"] != prepared["plan"]["profile"]
        or receipt["replay_id"] != replay_id
        or receipt["destination_root"] != str(Path(expected_destination).absolute())
        or type(receipt["filesystem_device"]) is not int
        or receipt["filesystem_allocation_unit_bytes"] != allocation_unit
        or receipt["plan_sha256"] != prepared["plan_sha256"]
        or receipt["suite_manifest_sha256"]
        != prepared["suite_manifest_sha256"]
        or receipt["capacity_plan"] != expected_plan.as_dict()
        or receipt["capacity_plan_sha256"]
        != storage.capacity_plan_sha256(expected_plan)
        or receipt["planned_not_attested"] is not True
    ):
        raise PersonaGenerationError("capacity receipt binding mismatch")
    try:
        filesystem_metadata = Path(filesystem_path).lstat()
        if (
            not storage.is_plain_directory_metadata(filesystem_metadata)
            or filesystem_metadata.st_dev != receipt["filesystem_device"]
        ):
            raise PersonaGenerationError("capacity filesystem binding mismatch")
        if _filesystem_allocation_unit(filesystem_path) != allocation_unit:
            raise PersonaGenerationError("filesystem allocation unit changed")
        limits = storage.CapacityLimits(**receipt["limits"])
        if expected_limits is not None and receipt["limits"] != expected_limits:
            raise PersonaGenerationError("capacity limits differ from this invocation")
        availability_row = receipt["availability"]
        if type(availability_row) is not dict or set(availability_row) != {
            "free_bytes", "free_inodes", "probe_path", "inode_source"
        }:
            raise PersonaGenerationError("capacity availability has invalid fields")
        if (
            type(availability_row["probe_path"]) is not str
            or not Path(availability_row["probe_path"]).is_absolute()
            or type(availability_row["inode_source"]) is not str
            or not availability_row["inode_source"]
        ):
            raise PersonaGenerationError("capacity availability identity is invalid")
        probe_metadata = Path(availability_row["probe_path"]).lstat()
        if (
            not storage.is_plain_directory_metadata(probe_metadata)
            or probe_metadata.st_dev != receipt["filesystem_device"]
            or _filesystem_allocation_unit(availability_row["probe_path"])
            != allocation_unit
        ):
            raise PersonaGenerationError("capacity probe filesystem differs")
        availability = storage.AvailableCapacity(
            free_bytes=availability_row["free_bytes"],
            free_inodes=availability_row["free_inodes"],
            probe_path=Path(availability_row["probe_path"]),
            inode_source=availability_row["inode_source"],
        )
        check = storage.check_capacity(expected_plan, availability, limits)
    except (OSError, TypeError, storage.PersonaStorageError) as error:
        raise PersonaGenerationError("capacity receipt is internally invalid") from error
    if receipt["check"] != asdict(check):
        raise PersonaGenerationError("capacity receipt check projection differs")
    return receipt


def _root_binding(prepared, capacity_receipt, replay_id, destination):
    persona_rows = [
        {
            "persona_id": persona_id,
            "sha256": _sha256(canonical_file_bytes(value)),
        }
        for persona_id, value in sorted(prepared["persona_manifests"].items())
    ]
    binding = {
        "schema": ROOT_BINDING_SCHEMA,
        "schema_version": 1,
        "fixture_id": spec.FIXTURE_ID,
        "profile": prepared["plan"]["profile"],
        "replay_id": replay_id,
        "destination_root": str(Path(destination).absolute()),
        "filesystem_device": capacity_receipt["filesystem_device"],
        "plan_sha256": prepared["plan_sha256"],
        "suite_manifest_sha256": prepared["suite_manifest_sha256"],
        "capacity_receipt_sha256": _sha256(
            canonical_file_bytes(capacity_receipt)
        ),
        "persona_manifest_root_sha256": _sha256(
            manifest.canonical_json_bytes({
                "domain": "kio.persona.w0.persona-manifest-root/v1",
                "personas": persona_rows,
            })
        ),
    }
    if len(canonical_file_bytes(binding)) > ROOT_BINDING_BUDGET:
        raise PersonaGenerationError("root binding exceeded its reserved budget")
    return binding


def _root_binding_sha256(binding):
    return _sha256(canonical_file_bytes(binding))


def _write_json(path, value):
    storage.atomic_write_file(path, canonical_file_bytes(value))


def _populate_root(root, prepared, capacity_receipt, root_binding):
    _write_json(root / PLAN_FILE_NAME, prepared["plan"])
    _write_json(root / SUITE_FILE_NAME, prepared["suite_manifest"])
    _write_json(root / CAPACITY_FILE_NAME, capacity_receipt)
    _write_json(root / ROOT_BINDING_FILE_NAME, root_binding)
    for person in prepared["plan"]["personas"]:
        device = root / "devices" / person["device_slug"]
        storage.atomic_create_directory(device / "home", parents=True)
        _write_json(
            device / PERSONA_FILE_NAME,
            prepared["persona_manifests"][person["persona_id"]],
        )
        for scope in person["scopes"]:
            leaf = device / "home"
            for component in PurePosixPath(scope["relative_path"]).parts:
                leaf /= component
            storage.atomic_create_directory(leaf, parents=True)
    for entry in prepared["source_entries"]:
        person = entry["person"]
        scope = entry["scope"]
        leaf = root / "devices" / person["device_slug"] / "home"
        for component in PurePosixPath(scope["relative_path"]).parts:
            leaf /= component
        storage.atomic_write_file(
            leaf / entry["source"]["file_name"], entry["rendered"].data
        )
    for shard in prepared["shards"]:
        person = shard["person"]
        scope = shard["scope"]
        destination = (
            root / "ledgers" / person["persona_id"] / scope["scope_key"]
        )
        validated = shard["validated"]
        published = manifest.publish_w0_scope_shard(
            destination,
            validated["physical_raw"],
            validated["logical_items"],
            validated["searchable_expectations"],
            fixture_id=spec.FIXTURE_ID,
            profile=prepared["plan"]["profile"],
            persona_id=person["persona_id"],
            scope_key=scope["scope_key"],
            plan_sha256=prepared["plan_sha256"],
            expected_contract_chunks=scope["expected_contract_chunks"],
            expected_physical_rows=scope["expected_physical_rows"],
            expected_variant_counts=scope["expected_variant_counts"],
        )
        if published != shard["manifest"]:
            raise PersonaGenerationError(
                f"published scope manifest drifted: {scope['scope_key']}"
            )


def _walk_exact_tree(root, expected_files, expected_directories):
    root = Path(root)
    root_metadata = root.lstat()
    if not storage.is_plain_directory_metadata(root_metadata) or root.is_symlink():
        raise PersonaGenerationError("persona root must be a plain directory")
    actual_files = set()
    actual_directories = set()
    file_inodes = set()
    directory_inodes = {(root_metadata.st_dev, root_metadata.st_ino)}
    maximum_entries = len(expected_files) + len(expected_directories)
    visited_entries = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        directory_metadata = directory.lstat()
        if (
            not storage.is_plain_directory_metadata(directory_metadata)
            or directory.is_symlink()
        ):
            raise PersonaGenerationError(f"unsafe directory in persona root: {directory}")
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    visited_entries += 1
                    if visited_entries > maximum_entries:
                        raise PersonaGenerationError(
                            "persona root exceeds the exact entry bound"
                        )
                    path = Path(entry.path)
                    relative = path.relative_to(root).as_posix()
                    if (
                        relative not in expected_files
                        and relative not in expected_directories
                    ):
                        raise PersonaGenerationError(
                            f"unexpected entry in persona root: {relative}"
                        )
                    metadata = path.lstat()
                    if (
                        storage.is_plain_directory_metadata(metadata)
                        and not path.is_symlink()
                    ):
                        if relative not in expected_directories:
                            raise PersonaGenerationError(
                                f"file/directory type mismatch: {relative}"
                            )
                        inode = (metadata.st_dev, metadata.st_ino)
                        if inode in directory_inodes:
                            raise PersonaGenerationError(
                                f"directory inode reused in persona root: {relative}"
                            )
                        directory_inodes.add(inode)
                        actual_directories.add(relative)
                        pending.append(path)
                    elif (
                        storage.is_plain_regular_file_metadata(metadata)
                        and not path.is_symlink()
                    ):
                        if relative not in expected_files:
                            raise PersonaGenerationError(
                                f"file/directory type mismatch: {relative}"
                            )
                        if metadata.st_nlink != 1:
                            raise PersonaGenerationError(
                                f"hard-linked file in persona root: {relative}"
                            )
                        inode = (metadata.st_dev, metadata.st_ino)
                        if inode in file_inodes:
                            raise PersonaGenerationError(
                                f"file inode reused in persona root: {relative}"
                            )
                        file_inodes.add(inode)
                        actual_files.add(relative)
                    else:
                        raise PersonaGenerationError(
                            f"symlink/reparse/special entry in persona root: {relative}"
                        )
        except OSError as error:
            raise PersonaGenerationError(f"cannot scan persona root: {directory}") from error
    if actual_files != expected_files:
        raise PersonaGenerationError(
            "persona root file allowlist mismatch "
            f"(missing={sorted(expected_files - actual_files)[:5]}, "
            f"extra={sorted(actual_files - expected_files)[:5]})"
        )
    if actual_directories != expected_directories:
        raise PersonaGenerationError(
            "persona root directory allowlist mismatch "
            f"(missing={sorted(expected_directories - actual_directories)[:5]}, "
            f"extra={sorted(actual_directories - expected_directories)[:5]})"
        )


def _assert_canonical_file(path, expected, maximum, label):
    raw = _read_plain_file(path, maximum, label)
    if raw != canonical_file_bytes(expected):
        raise PersonaGenerationError(f"{label} differs from its canonical value")


def _verify_rendered_sources(root, prepared):
    for entry in prepared["source_entries"]:
        person = entry["person"]
        scope = entry["scope"]
        source = entry["source"]
        # Reconstruct solely from the canonical plan, never from ledger claims.
        request = _source_request(person["persona_id"], scope["scope_key"], source)
        rendered = renderers.render_source(request)
        physical, logical, searchable = _rows_for_rendered(
            person["persona_id"], scope, source, rendered
        )
        if (
            physical != entry["physical"]
            or tuple(logical) != entry["logical"]
            or searchable != entry["searchable"]
        ):
            raise PersonaGenerationError(
                f"renderer/ledger projection drifted: {source['source_id']}"
            )
        path = root / "devices" / person["device_slug"] / "home"
        for component in PurePosixPath(scope["relative_path"]).parts:
            path /= component
        path /= source["file_name"]
        raw = _read_plain_file(
            path, renderers.MAX_RENDERED_SOURCE_BYTES, "rendered source"
        )
        if raw != rendered.data:
            raise PersonaGenerationError(
                f"rendered source differs from canonical request: {source['source_id']}"
            )


def _verify_expected_w0_entries_allowing_extras(root, prepared):
    """Require every immutable W0 path/type without rejecting phase extras.

    This is deliberately not a permissive recursive walk: every expected path
    is checked directly, while the separate phase-envelope verifier owns the
    allowlist for additional runtime entries.
    """
    root = Path(root)
    root_metadata = root.lstat()
    if not storage.is_plain_directory_metadata(root_metadata) or root.is_symlink():
        raise PersonaGenerationError("persona root must be a plain directory")
    expected_files, expected_directories = _expected_layout(prepared, ready=True)
    directory_inodes = {(root_metadata.st_dev, root_metadata.st_ino)}
    for relative in sorted(
        expected_directories,
        key=lambda value: (len(PurePosixPath(value).parts), value),
    ):
        path = root.joinpath(*PurePosixPath(relative).parts)
        try:
            metadata = path.lstat()
        except OSError as error:
            raise PersonaGenerationError(
                f"missing or unreadable immutable W0 directory: {relative}"
            ) from error
        if not storage.is_plain_directory_metadata(metadata) or path.is_symlink():
            raise PersonaGenerationError(
                f"immutable W0 directory is unsafe: {relative}"
            )
        inode = (metadata.st_dev, metadata.st_ino)
        if inode in directory_inodes:
            raise PersonaGenerationError(
                f"immutable W0 directory inode is reused: {relative}"
            )
        directory_inodes.add(inode)

    file_inodes = set()
    for relative in sorted(expected_files):
        path = root.joinpath(*PurePosixPath(relative).parts)
        try:
            metadata = path.lstat()
        except OSError as error:
            raise PersonaGenerationError(
                f"missing or unreadable immutable W0 file: {relative}"
            ) from error
        if (
            not storage.is_plain_regular_file_metadata(metadata)
            or path.is_symlink()
            or metadata.st_nlink != 1
        ):
            raise PersonaGenerationError(f"immutable W0 file is unsafe: {relative}")
        inode = (metadata.st_dev, metadata.st_ino)
        if inode in file_inodes:
            raise PersonaGenerationError(
                f"immutable W0 file inode is reused: {relative}"
            )
        file_inodes.add(inode)


def _verify_w0_immutable_content_prepared(plan, root, replay_id, prepared):
    """Verify W0 bytes and ledgers while allowing phase-owned extra entries."""
    _require_physical_publication_platform()
    if replay_id not in REPLAY_IDS:
        raise PersonaGenerationError(f"invalid replay id: {replay_id!r}")
    if (
        prepared.get("plan") != plan
        or prepared.get("plan_sha256") != generation_plan_sha256(plan)
    ):
        raise PersonaGenerationError("prepared suite is not bound to the supplied plan")
    root = Path(root).absolute()
    inspected = storage.preflight_destination(
        root,
        expected_profile=plan["profile"],
        expected_replay_id=replay_id,
        expected_plan_sha256=prepared["plan_sha256"],
    )
    if (
        inspected.disposition != "owned"
        or inspected.owner is None
        or inspected.owner.get("state") != "ready"
    ):
        raise PersonaGenerationError("replay root is not ready-owned")
    capacity_receipt = _decode_canonical_json(
        _read_plain_file(
            root / CAPACITY_FILE_NAME,
            MAX_CAPACITY_RECEIPT_BYTES,
            "capacity receipt",
        ),
        "capacity receipt",
    )
    _validate_capacity_receipt(
        prepared,
        capacity_receipt,
        replay_id,
        expected_destination=root,
        filesystem_path=root,
    )
    root_binding = _root_binding(prepared, capacity_receipt, replay_id, root)
    _assert_canonical_file(
        root / ROOT_BINDING_FILE_NAME,
        root_binding,
        ROOT_BINDING_BUDGET,
        "W0 root binding",
    )
    root_binding_sha256 = _root_binding_sha256(root_binding)
    storage.require_ready_owned_root(
        root,
        profile=plan["profile"],
        replay_id=replay_id,
        plan_sha256=prepared["plan_sha256"],
        manifest_sha256=root_binding_sha256,
    )
    # Unlike strict ready-root reuse, this public verifier performs no fsync
    # and no durability re-confirmation: it is a read-only phase prerequisite.
    _verify_expected_w0_entries_allowing_extras(root, prepared)
    if storage.load_staging_owner_marker(root) != storage.make_staging_owner_marker(
        profile=plan["profile"],
        replay_id=replay_id,
        plan_sha256=prepared["plan_sha256"],
        manifest_sha256=root_binding_sha256,
    ):
        raise PersonaGenerationError("staging publication receipt differs")
    _assert_canonical_file(
        root / PLAN_FILE_NAME, plan, MAX_PLAN_BYTES, "published generation plan"
    )
    load_generation_plan(root / PLAN_FILE_NAME)
    _assert_canonical_file(
        root / SUITE_FILE_NAME,
        prepared["suite_manifest"],
        manifest.MAX_SCOPE_MANIFEST_BYTES * 4,
        "W0 suite manifest",
    )
    for person in plan["personas"]:
        _assert_canonical_file(
            root / "devices" / person["device_slug"] / PERSONA_FILE_NAME,
            prepared["persona_manifests"][person["persona_id"]],
            manifest.MAX_SCOPE_MANIFEST_BYTES,
            "persona manifest",
        )
    _verify_rendered_sources(root, prepared)
    observed_manifests = []
    observed_projections = []
    for shard in prepared["shards"]:
        person = shard["person"]
        scope = shard["scope"]
        persona_home = root / "devices" / person["device_slug"] / "home"
        result = manifest.verify_w0_scope_shard(
            root / "ledgers" / person["persona_id"] / scope["scope_key"],
            expected_manifest=shard["manifest"],
            persona_home=persona_home,
        )
        if (
            result["manifest"]["totals"]["sources_by_variant"]
            != scope["expected_variant_counts"]
        ):
            raise PersonaGenerationError(
                f"scope allocation cell mismatch: {scope['scope_key']}"
            )
        observed_manifests.append(result["manifest"])
        observed_projections.append(result["validated"])
    rebuilt_suite = manifest.build_w0_suite_manifest(
        fixture_id=spec.FIXTURE_ID,
        profile=plan["profile"],
        plan_sha256=prepared["plan_sha256"],
        shard_manifests=observed_manifests,
        validated_shards=observed_projections,
    )
    if rebuilt_suite != prepared["suite_manifest"]:
        raise PersonaGenerationError("published suite does not rebuild exactly")
    return {
        "root": str(root),
        "profile": plan["profile"],
        "replay_id": replay_id,
        "plan_sha256": prepared["plan_sha256"],
        "root_binding_sha256": root_binding_sha256,
        "suite_manifest_sha256": prepared["suite_manifest_sha256"],
        "personas": plan["totals"]["personas"],
        "scope_shards": plan["totals"]["scope_shards"],
        "physical_sources": plan["totals"]["physical_sources"],
        "planned_contract_chunks": plan["totals"]["planned_contract_chunks"],
        "actual_kio_chunks_attested": False,
        "immutable_w0_verified": True,
        "strict_full_tree_verified": False,
        "durability_reconfirmed": False,
        "verification_mode": "w0-immutable-content",
    }


def verify_w0_immutable_content(plan, root, replay_id):
    """Read-only verification of immutable W0 bytes after runtime creation.

    Extra paths are intentionally ignored here and must be checked by
    :func:`verify_history_prepare_envelope`.  This API never creates, removes,
    rewrites, fsyncs, or invokes KIO.
    """
    if replay_id not in REPLAY_IDS:
        raise PersonaGenerationError(f"invalid replay id: {replay_id!r}")
    _require_physical_publication_platform()
    validate_generation_plan(plan)
    if plan["profile"] not in WRITABLE_PROFILES:
        raise PersonaGenerationError(
            f"verification is not enabled for physical {plan['profile']} roots"
        )
    prepared = prepare_w0_suite(plan)
    return _verify_w0_immutable_content_prepared(plan, root, replay_id, prepared)


def _verify_replay_root_prepared(
    plan,
    root,
    replay_id,
    prepared,
    *,
    expected_limits=None,
    home=None,
    repo_root=None,
):
    _require_physical_publication_platform()
    if replay_id not in REPLAY_IDS:
        raise PersonaGenerationError(f"invalid replay id: {replay_id!r}")
    if (
        prepared.get("plan") != plan
        or prepared.get("plan_sha256") != generation_plan_sha256(plan)
    ):
        raise PersonaGenerationError("prepared suite is not bound to the supplied plan")
    root = Path(root).absolute()
    inspected = storage.preflight_destination(
        root,
        home=home,
        repo_root=repo_root,
        expected_profile=plan["profile"],
        expected_replay_id=replay_id,
        expected_plan_sha256=prepared["plan_sha256"],
    )
    if inspected.disposition != "owned":
        raise PersonaGenerationError("replay root is not ready-owned")
    capacity_receipt = _decode_canonical_json(
        _read_plain_file(
            root / CAPACITY_FILE_NAME,
            MAX_CAPACITY_RECEIPT_BYTES,
            "capacity receipt",
        ),
        "capacity receipt",
    )
    _validate_capacity_receipt(
        prepared,
        capacity_receipt,
        replay_id,
        expected_destination=root,
        filesystem_path=root,
        expected_limits=expected_limits,
    )
    root_binding = _root_binding(prepared, capacity_receipt, replay_id, root)
    _assert_canonical_file(
        root / ROOT_BINDING_FILE_NAME,
        root_binding,
        ROOT_BINDING_BUDGET,
        "W0 root binding",
    )
    root_binding_sha256 = _root_binding_sha256(root_binding)
    storage.require_ready_owned_root(
        root,
        profile=plan["profile"],
        replay_id=replay_id,
        plan_sha256=prepared["plan_sha256"],
        manifest_sha256=root_binding_sha256,
    )
    storage.confirm_ready_root_durability(root)
    expected_files, expected_directories = _expected_layout(prepared, ready=True)
    _walk_exact_tree(root, expected_files, expected_directories)
    if storage.load_staging_owner_marker(root) != storage.make_staging_owner_marker(
        profile=plan["profile"],
        replay_id=replay_id,
        plan_sha256=prepared["plan_sha256"],
        manifest_sha256=root_binding_sha256,
    ):
        raise PersonaGenerationError("staging publication receipt differs")
    _assert_canonical_file(
        root / PLAN_FILE_NAME, plan, MAX_PLAN_BYTES, "published generation plan"
    )
    load_generation_plan(root / PLAN_FILE_NAME)
    _assert_canonical_file(
        root / SUITE_FILE_NAME,
        prepared["suite_manifest"],
        manifest.MAX_SCOPE_MANIFEST_BYTES * 4,
        "W0 suite manifest",
    )
    for person in plan["personas"]:
        _assert_canonical_file(
            root / "devices" / person["device_slug"] / PERSONA_FILE_NAME,
            prepared["persona_manifests"][person["persona_id"]],
            manifest.MAX_SCOPE_MANIFEST_BYTES,
            "persona manifest",
        )
    _verify_rendered_sources(root, prepared)
    observed_manifests = []
    observed_projections = []
    for shard in prepared["shards"]:
        person = shard["person"]
        scope = shard["scope"]
        persona_home = root / "devices" / person["device_slug"] / "home"
        result = manifest.verify_w0_scope_shard(
            root / "ledgers" / person["persona_id"] / scope["scope_key"],
            expected_manifest=shard["manifest"],
            persona_home=persona_home,
        )
        if (
            result["manifest"]["totals"]["sources_by_variant"]
            != scope["expected_variant_counts"]
        ):
            raise PersonaGenerationError(
                f"scope allocation cell mismatch: {scope['scope_key']}"
            )
        observed_manifests.append(result["manifest"])
        observed_projections.append(result["validated"])
    rebuilt_suite = manifest.build_w0_suite_manifest(
        fixture_id=spec.FIXTURE_ID,
        profile=plan["profile"],
        plan_sha256=prepared["plan_sha256"],
        shard_manifests=observed_manifests,
        validated_shards=observed_projections,
    )
    if rebuilt_suite != prepared["suite_manifest"]:
        raise PersonaGenerationError("published suite does not rebuild exactly")
    return {
        "root": str(root),
        "profile": plan["profile"],
        "replay_id": replay_id,
        "plan_sha256": prepared["plan_sha256"],
        "root_binding_sha256": root_binding_sha256,
        "suite_manifest_sha256": prepared["suite_manifest_sha256"],
        "personas": plan["totals"]["personas"],
        "scope_shards": plan["totals"]["scope_shards"],
        "physical_sources": plan["totals"]["physical_sources"],
        "planned_contract_chunks": plan["totals"]["planned_contract_chunks"],
        "actual_kio_chunks_attested": False,
        "verified": True,
    }


def verify_replay_root(plan, root, replay_id):
    """Strict full-tree, shard, suite, capacity, and rerender verification."""
    if replay_id not in REPLAY_IDS:
        raise PersonaGenerationError(f"invalid replay id: {replay_id!r}")
    _require_physical_publication_platform()
    validate_generation_plan(plan)
    if plan["profile"] not in WRITABLE_PROFILES:
        raise PersonaGenerationError(
            f"verification is not enabled for physical {plan['profile']} roots"
        )
    prepared = prepare_w0_suite(plan)
    return _verify_replay_root_prepared(plan, root, replay_id, prepared)


def _walk_history_prepare_envelope(
    root,
    expected_files,
    expected_directories,
    opaque_directories,
):
    """Walk an exact phase envelope, stopping at explicitly opaque runtimes."""
    root = Path(root)
    root_metadata = root.lstat()
    if not storage.is_plain_directory_metadata(root_metadata) or root.is_symlink():
        raise PersonaGenerationError("persona root must be a plain directory")
    if not opaque_directories <= expected_directories:
        raise PersonaGenerationError("opaque runtime directories are not allowlisted")
    actual_files = set()
    actual_directories = set()
    file_inodes = set()
    directory_inodes = {(root_metadata.st_dev, root_metadata.st_ino)}
    maximum_entries = len(expected_files) + len(expected_directories)
    visited_entries = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        directory_metadata = directory.lstat()
        if (
            not storage.is_plain_directory_metadata(directory_metadata)
            or directory.is_symlink()
        ):
            raise PersonaGenerationError(
                f"unsafe directory in history prepare envelope: {directory}"
            )
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    visited_entries += 1
                    if visited_entries > maximum_entries:
                        raise PersonaGenerationError(
                            "history prepare envelope exceeds its exact entry bound"
                        )
                    path = Path(entry.path)
                    relative = path.relative_to(root).as_posix()
                    if (
                        relative not in expected_files
                        and relative not in expected_directories
                    ):
                        raise PersonaGenerationError(
                            f"unexpected entry in history prepare envelope: {relative}"
                        )
                    metadata = path.lstat()
                    if (
                        storage.is_plain_directory_metadata(metadata)
                        and not path.is_symlink()
                    ):
                        if relative not in expected_directories:
                            raise PersonaGenerationError(
                                f"file/directory type mismatch: {relative}"
                            )
                        inode = (metadata.st_dev, metadata.st_ino)
                        if inode in directory_inodes:
                            raise PersonaGenerationError(
                                f"directory inode reused in prepare envelope: {relative}"
                            )
                        directory_inodes.add(inode)
                        actual_directories.add(relative)
                        # KIO and device runtime formats require a semantic
                        # attestor.  Generic recursion must not legitimize an
                        # arbitrary internal tree merely because it is made of
                        # regular files and directories.
                        if relative not in opaque_directories:
                            pending.append(path)
                    elif (
                        storage.is_plain_regular_file_metadata(metadata)
                        and not path.is_symlink()
                    ):
                        if relative not in expected_files:
                            raise PersonaGenerationError(
                                f"file/directory type mismatch: {relative}"
                            )
                        if metadata.st_nlink != 1:
                            raise PersonaGenerationError(
                                f"hard-linked file in prepare envelope: {relative}"
                            )
                        inode = (metadata.st_dev, metadata.st_ino)
                        if inode in file_inodes:
                            raise PersonaGenerationError(
                                f"file inode reused in prepare envelope: {relative}"
                            )
                        file_inodes.add(inode)
                        actual_files.add(relative)
                    else:
                        raise PersonaGenerationError(
                            "symlink/reparse/special entry in history prepare "
                            f"envelope: {relative}"
                        )
        except OSError as error:
            raise PersonaGenerationError(
                f"cannot scan history prepare envelope: {directory}"
            ) from error
    if actual_files != expected_files:
        raise PersonaGenerationError(
            "history prepare file allowlist mismatch "
            f"(missing={sorted(expected_files - actual_files)[:5]}, "
            f"extra={sorted(actual_files - expected_files)[:5]})"
        )
    if actual_directories != expected_directories:
        raise PersonaGenerationError(
            "history prepare directory allowlist mismatch "
            f"(missing={sorted(expected_directories - actual_directories)[:5]}, "
            f"extra={sorted(actual_directories - expected_directories)[:5]})"
        )


def _verify_declared_prepare_files(root, rows, label):
    for row in rows:
        relative = row["relative_path"]
        path = Path(root).joinpath(*PurePosixPath(relative).parts)
        raw = _read_plain_file(
            path,
            MAX_HISTORY_PREPARE_DECLARED_FILE_BYTES,
            label,
        )
        if len(raw) != row["bytes"] or _sha256(raw) != row["raw_sha256"]:
            raise PersonaGenerationError(
                f"{label} differs from its prepare intent: {relative}"
            )


def _attest_opaque_runtime_directories(root, descriptors, runtime_attestor):
    if runtime_attestor is None:
        return {
            "status": "opaque_unattested",
            "attestation_root_sha256": None,
            "attested_directories": 0,
        }
    if not callable(runtime_attestor):
        raise PersonaGenerationError("runtime attestor must be callable")
    receipts = []
    for descriptor in descriptors:
        relative = descriptor["relative_path"]
        path = Path(root).joinpath(*PurePosixPath(relative).parts)
        before = path.lstat()
        if (
            not storage.is_plain_directory_metadata(before)
            or path.is_symlink()
        ):
            raise PersonaGenerationError(
                f"opaque runtime root is unsafe: {relative}"
            )
        try:
            receipt = runtime_attestor(path, dict(descriptor))
        except Exception as error:
            raise PersonaGenerationError(
                f"runtime attestor failed: {relative}"
            ) from error
        after = path.lstat()
        expected_attestor_schema = (
            RUNTIME_SCOPE_STORE_SEMANTIC_CONTRACT
            if descriptor["kind"] == "scope_store"
            else RUNTIME_DEVICE_STATE_SEMANTIC_CONTRACT
        )
        if (
            type(receipt) is not dict
            or set(receipt) != {
                "schema", "schema_version", "kind", "relative_path",
                "directory_device", "directory_inode", "directory_nlink",
                "attestor_schema", "content_root_sha256",
            }
            or receipt.get("schema") != RUNTIME_DIRECTORY_ATTESTATION_SCHEMA
            or type(receipt.get("schema_version")) is not int
            or receipt.get("schema_version") != 1
            or receipt.get("kind") != descriptor["kind"]
            or receipt.get("relative_path") != relative
            or type(receipt.get("directory_device")) is not int
            or receipt.get("directory_device") != before.st_dev
            or type(receipt.get("directory_inode")) is not int
            or receipt.get("directory_inode") != before.st_ino
            or type(receipt.get("directory_nlink")) is not int
            or receipt.get("directory_nlink") != before.st_nlink
            or receipt.get("attestor_schema") != expected_attestor_schema
            or type(receipt.get("content_root_sha256")) is not str
            or len(receipt.get("content_root_sha256", "")) != 64
            or any(
                character not in "0123456789abcdef"
                for character in receipt.get("content_root_sha256", "")
            )
            or not storage.is_plain_directory_metadata(after)
            or path.is_symlink()
            or (before.st_dev, before.st_ino, before.st_nlink)
            != (after.st_dev, after.st_ino, after.st_nlink)
        ):
            raise PersonaGenerationError(
                "runtime attestation receipt did not bind a stable directory: "
                f"{relative}"
            )
        # The callback owns its dict and may reuse or mutate it on a later
        # invocation.  Freeze the validated primitive fields immediately.
        receipts.append({
            "schema": receipt["schema"],
            "schema_version": receipt["schema_version"],
            "kind": receipt["kind"],
            "relative_path": receipt["relative_path"],
            "directory_device": receipt["directory_device"],
            "directory_inode": receipt["directory_inode"],
            "directory_nlink": receipt["directory_nlink"],
            "attestor_schema": receipt["attestor_schema"],
            "content_root_sha256": receipt["content_root_sha256"],
        })
    root_value = {
        "schema": RUNTIME_ATTESTATION_ROOT_SCHEMA,
        "schema_version": 1,
        "receipts": receipts,
    }
    return {
        "status": "attested_by_callback",
        "attestation_root_sha256": _sha256(
            manifest.canonical_json_bytes(root_value)
        ),
        "attested_directories": len(receipts),
    }


def verify_history_prepare_envelope(
    plan,
    root,
    replay_id,
    *,
    prepare_intent,
    runtime_attestor=None,
):
    """Verify the exact post-W0/pre-mutation filesystem envelope read-only.

    A validated intent is mandatory.  ``.kio`` scope stores and per-device
    ``.kio-eval-device`` trees are opaque boundaries: without a supplied
    read-only semantic attestor their contents are not traversed or claimed
    valid, and the result explicitly reports ``opaque_unattested``.  Unknown,
    nested managed, symlink/reparse/special, and hard-linked entries outside
    those opaque boundaries fail closed.  This function runs no KIO process,
    mutates nothing, and never marks history replay executable or history
    readiness attested.
    """
    if replay_id not in REPLAY_IDS:
        raise PersonaGenerationError(f"invalid replay id: {replay_id!r}")
    _require_physical_publication_platform()
    validate_generation_plan(plan)
    if plan["profile"] not in WRITABLE_PROFILES:
        raise PersonaGenerationError(
            f"verification is not enabled for physical {plan['profile']} roots"
        )
    # Intent validation deliberately precedes every root inspection.
    prepare_intent = validate_history_prepare_intent(
        plan, replay_id, prepare_intent
    )

    # A semantic runtime callback must never see an incomplete, falsely-bound,
    # or tampered root.  Verify all immutable W0 bytes before the first walk;
    # callback-enabled verification repeats it at the end.
    immutable_result = verify_w0_immutable_content(plan, root, replay_id)

    expected_files, expected_directories = _expected_layout(
        {"plan": plan}, ready=True
    )
    scope_stores = set(prepare_intent["scope_store_directories"])
    device_states = set(prepare_intent["device_state_directories"])
    opaque_directories = scope_stores | device_states
    expected_directories.update(opaque_directories)
    inferred = _validate_declared_prepare_location_set(
        plan,
        prepare_intent["receipt_files"],
        prepare_intent["control_files"],
    )
    expected_directories.update(inferred)
    expected_files.update(
        row["relative_path"]
        for row in (
            *prepare_intent["receipt_files"],
            *prepare_intent["control_files"],
        )
    )
    root = Path(immutable_result["root"])
    _walk_history_prepare_envelope(
        root,
        expected_files,
        expected_directories,
        opaque_directories,
    )
    _verify_declared_prepare_files(
        root, prepare_intent["receipt_files"], "history prepare receipt"
    )
    _verify_declared_prepare_files(
        root, prepare_intent["control_files"], "history prepare control"
    )
    descriptors = [
        {"kind": "scope_store", "relative_path": relative}
        for relative in prepare_intent["scope_store_directories"]
    ] + [
        {"kind": "device_state", "relative_path": relative}
        for relative in prepare_intent["device_state_directories"]
    ]
    runtime_attestation = _attest_opaque_runtime_directories(
        root, descriptors, runtime_attestor
    )
    if runtime_attestor is not None:
        # A callback is a read-only trust boundary, not permission to mutate
        # or reclassify the enclosing persona tree.  Re-walk all non-opaque
        # entries and re-hash every declared receipt/control after it returns.
        _walk_history_prepare_envelope(
            root,
            expected_files,
            expected_directories,
            opaque_directories,
        )
        _verify_declared_prepare_files(
            root, prepare_intent["receipt_files"], "history prepare receipt"
        )
        _verify_declared_prepare_files(
            root, prepare_intent["control_files"], "history prepare control"
        )
        # Hash/rerender W0 again so a semantic attestor cannot invalidate
        # source or ledger bytes and still receive a successful result.
        immutable_result = verify_w0_immutable_content(plan, root, replay_id)
    return {
        **immutable_result,
        "verification_mode": "history-prepare-envelope",
        "prepare_intent_sha256": _sha256(
            manifest.canonical_json_bytes(prepare_intent)
        ),
        "envelope_verified": True,
        "scope_store_directories": len(scope_stores),
        "device_state_directories": len(device_states),
        "declared_receipt_files": len(prepare_intent["receipt_files"]),
        "declared_control_files": len(prepare_intent["control_files"]),
        "runtime_contents_status": runtime_attestation["status"],
        "runtime_attestation_root_sha256": runtime_attestation[
            "attestation_root_sha256"
        ],
        "attested_runtime_directories": runtime_attestation[
            "attested_directories"
        ],
        "opaque_runtime_contents_attested": (
            runtime_attestation["status"] == "attested_by_callback"
        ),
        "history_ready_attested": False,
        "strict_full_tree_verified": False,
    }


def _validate_staging_root(
    root,
    prepared,
    capacity_receipt,
    root_binding,
    replay_id,
    destination,
    expected_limits,
):
    expected_files, expected_directories = _expected_layout(prepared, ready=False)
    _walk_exact_tree(root, expected_files, expected_directories)
    _assert_canonical_file(root / PLAN_FILE_NAME, prepared["plan"], MAX_PLAN_BYTES, "plan")
    _assert_canonical_file(
        root / SUITE_FILE_NAME,
        prepared["suite_manifest"],
        manifest.MAX_SCOPE_MANIFEST_BYTES * 4,
        "suite manifest",
    )
    _assert_canonical_file(
        root / CAPACITY_FILE_NAME,
        capacity_receipt,
        MAX_CAPACITY_RECEIPT_BYTES,
        "capacity receipt",
    )
    _validate_capacity_receipt(
        prepared,
        capacity_receipt,
        replay_id,
        expected_destination=destination,
        filesystem_path=root,
        expected_limits=expected_limits,
    )
    if root_binding != _root_binding(
        prepared, capacity_receipt, replay_id, destination
    ):
        raise PersonaGenerationError("staging root binding projection differs")
    _assert_canonical_file(
        root / ROOT_BINDING_FILE_NAME,
        root_binding,
        ROOT_BINDING_BUDGET,
        "root binding",
    )
    for person in prepared["plan"]["personas"]:
        _assert_canonical_file(
            root / "devices" / person["device_slug"] / PERSONA_FILE_NAME,
            prepared["persona_manifests"][person["persona_id"]],
            manifest.MAX_SCOPE_MANIFEST_BYTES,
            "persona manifest",
        )
    _verify_rendered_sources(root, prepared)
    observed_manifests = []
    observed_projections = []
    for shard in prepared["shards"]:
        person = shard["person"]
        scope = shard["scope"]
        result = manifest.verify_w0_scope_shard(
            root / "ledgers" / person["persona_id"] / scope["scope_key"],
            expected_manifest=shard["manifest"],
            persona_home=root / "devices" / person["device_slug"] / "home",
        )
        if result["manifest"]["totals"]["sources_by_variant"] != scope[
            "expected_variant_counts"
        ]:
            raise PersonaGenerationError("scope variant cell differs in staging")
        observed_manifests.append(result["manifest"])
        observed_projections.append(result["validated"])
    rebuilt = manifest.build_w0_suite_manifest(
        fixture_id=spec.FIXTURE_ID,
        profile=prepared["plan"]["profile"],
        plan_sha256=prepared["plan_sha256"],
        shard_manifests=observed_manifests,
        validated_shards=observed_projections,
    )
    if rebuilt != prepared["suite_manifest"]:
        raise PersonaGenerationError("staging suite does not rebuild exactly")


def generate_replay(
    plan,
    destination,
    replay_id,
    *,
    byte_cap=DEFAULT_TINY_BYTE_CAP,
    inode_cap=DEFAULT_TINY_INODE_CAP,
    reserve_bytes=DEFAULT_RESERVE_BYTES,
    reserve_inodes=DEFAULT_RESERVE_INODES,
    explicit_free_inodes=None,
    repo_root=None,
    home=None,
):
    """Publish one independent tiny W0 root, or strictly verify a ready no-op."""
    if replay_id not in REPLAY_IDS:
        raise PersonaGenerationError(f"invalid replay id: {replay_id!r}")
    _require_physical_publication_platform()
    validate_generation_plan(plan)
    if plan["profile"] not in WRITABLE_PROFILES:
        raise PersonaGenerationError(
            f"{plan['profile']} write is blocked pending streaming/RSS/pilot gates"
        )
    prepared = prepare_w0_suite(plan)
    expected_limits = asdict(storage.CapacityLimits(
        byte_cap=byte_cap,
        inode_cap=inode_cap,
        reserve_bytes=reserve_bytes,
        reserve_inodes=reserve_inodes,
    ))
    inspected = storage.preflight_destination(
        destination,
        home=home,
        repo_root=repo_root,
        expected_profile=plan["profile"],
        expected_replay_id=replay_id,
        expected_plan_sha256=prepared["plan_sha256"],
    )
    if inspected.disposition == "owned":
        result = _verify_replay_root_prepared(
            plan,
            inspected.root,
            replay_id,
            prepared,
            expected_limits=expected_limits,
            home=home,
            repo_root=repo_root,
        )
        result["published"] = False
        result["strict_noop"] = True
        return result
    if inspected.disposition != "missing":
        raise PersonaGenerationError(
            "persona final root must be missing or an exactly verified ready root"
        )
    capacity_receipt = _capacity_receipt(
        prepared,
        inspected.root,
        replay_id,
        byte_cap=byte_cap,
        inode_cap=inode_cap,
        reserve_bytes=reserve_bytes,
        reserve_inodes=reserve_inodes,
        explicit_free_inodes=explicit_free_inodes,
    )
    root_binding = _root_binding(
        prepared, capacity_receipt, replay_id, inspected.root
    )
    root_binding_sha256 = _root_binding_sha256(root_binding)
    publication = storage.atomic_publish_owned_root(
        inspected.root,
        profile=plan["profile"],
        replay_id=replay_id,
        plan_sha256=prepared["plan_sha256"],
        manifest_sha256=root_binding_sha256,
        populate=lambda stage: _populate_root(
            stage, prepared, capacity_receipt, root_binding
        ),
        validate=lambda stage: _validate_staging_root(
            stage,
            prepared,
            capacity_receipt,
            root_binding,
            replay_id,
            inspected.root,
            expected_limits,
        ),
        home=home,
        repo_root=repo_root,
    )
    if (
        not publication.published
        or not publication.durability_confirmed
        or not publication.identity_confirmed
    ):
        # The final path may already be visible.  Re-attest it, but do not
        # delete, repair, or claim a successful durable publication.
        if publication.root.exists():
            _verify_replay_root_prepared(
                plan,
                publication.root,
                replay_id,
                prepared,
                expected_limits=expected_limits,
                home=home,
                repo_root=repo_root,
            )
        raise PersonaGenerationError(
            "publication confirmation failed: "
            f"durability={publication.durability_confirmed}, "
            f"identity={publication.identity_confirmed}, "
            f"warning={publication.warning!r}"
        )
    result = _verify_replay_root_prepared(
        plan,
        publication.root,
        replay_id,
        prepared,
        expected_limits=expected_limits,
        home=home,
        repo_root=repo_root,
    )
    result["published"] = True
    result["strict_noop"] = False
    return result


def _parser():
    parser = argparse.ArgumentParser(
        description="Plan, generate, and verify the synthetic persona-PC W0 corpus"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="write an immutable generation plan")
    plan.add_argument("--profile", choices=("tiny", "pilot", "full"), required=True)
    plan.add_argument("--plan-out", type=Path, required=True)

    generate = commands.add_parser("generate", help="publish one independent W0 root")
    generate.add_argument("--plan", type=Path, required=True)
    generate.add_argument("--out", type=Path, required=True)
    generate.add_argument("--replay-id", choices=REPLAY_IDS, required=True)
    generate.add_argument("--byte-cap", type=int, default=DEFAULT_TINY_BYTE_CAP)
    generate.add_argument("--inode-cap", type=int, default=DEFAULT_TINY_INODE_CAP)
    generate.add_argument("--reserve-bytes", type=int, default=DEFAULT_RESERVE_BYTES)
    generate.add_argument("--reserve-inodes", type=int, default=DEFAULT_RESERVE_INODES)
    generate.add_argument("--explicit-free-inodes", type=int)

    verify = commands.add_parser("verify", help="strictly verify one ready W0 root")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--replay-id", choices=REPLAY_IDS, required=True)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "plan":
            plan, written = write_generation_plan(args.plan_out, args.profile)
            result = {
                "command": "plan",
                "path": str(args.plan_out.absolute()),
                "profile": args.profile,
                "plan_sha256": generation_plan_sha256(plan),
                **plan["totals"],
                "written": written,
                "actual_kio_chunks_attested": False,
            }
        elif args.command == "generate":
            result = generate_replay(
                load_generation_plan(args.plan),
                args.out,
                args.replay_id,
                byte_cap=args.byte_cap,
                inode_cap=args.inode_cap,
                reserve_bytes=args.reserve_bytes,
                reserve_inodes=args.reserve_inodes,
                explicit_free_inodes=args.explicit_free_inodes,
            )
            result["command"] = "generate"
        else:
            result = verify_replay_root(
                load_generation_plan(args.plan), args.root, args.replay_id
            )
            result["command"] = "verify"
    except (
        PersonaGenerationError,
        allocation.AllocationError,
        manifest.PersonaManifestError,
        renderers.RendererContractError,
        storage.PersonaStorageError,
        OSError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
