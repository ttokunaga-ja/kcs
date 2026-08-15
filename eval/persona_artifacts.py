"""Strict, non-authorizing readers for Rust-owned persona artifacts.

This module binds exact artifact bytes to a small, safe filesystem topology.
It is deliberately not a second implementation of the Rust plan, schedule, or
renderer contracts and must never be used as Kio semantic evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


FIXTURE_ID = "kio-persona-pc-v2"
PLAN_SCHEMA = "kio.persona.plan/v2"
SCHEDULE_SCHEMA = "kio.persona.schedule/v2"
RENDER_SCHEMA = "kio.persona.render-artifact/v2"
ARTIFACT_BUNDLE_SCHEMA = "kio.persona.artifact-bundle/v2"

MAX_PLAN_BYTES = 4 * 1024 * 1024
MAX_SCHEDULE_BYTES = 64 * 1024 * 1024
MAX_RENDER_BYTES = 160 * 1024 * 1024
MAX_PATH_COMPONENTS = 128

_ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_PATH_COMPONENT = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_PERSONA_ID = re.compile(r"p(?:0[1-9]|1[0-9]|20)\Z")


class PersonaArtifactError(RuntimeError):
    """An artifact or its filesystem binding is unsafe or malformed."""


@dataclass(frozen=True)
class ScopeTopology:
    scope_id: str
    path: str


@dataclass(frozen=True)
class PersonTopology:
    persona_id: str
    role: str
    scopes: tuple[ScopeTopology, ...]


@dataclass(frozen=True)
class ArtifactBundle:
    fixture_id: str
    profile: str
    plan_digest: str
    plan_sha256: str
    schedule_sha256: str
    render_sha256: str
    people: tuple[PersonTopology, ...]


def _stable(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        getattr(metadata, "st_mtime_ns", 0),
        getattr(metadata, "st_ctime_ns", 0),
    )


def _directory_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode)


def _normalized_artifact_path(path: Path, label: str) -> Path:
    supplied = Path(os.fspath(path))
    if (
        not supplied.is_absolute()
        or Path(os.path.normpath(os.fspath(supplied))) != supplied
        or len(supplied.parts) > MAX_PATH_COMPONENTS
    ):
        raise PersonaArtifactError(
            f"{label} path must be absolute, bounded, and lexically normalized"
        )
    # Darwin exposes these two fixed system aliases. Normalizing only these
    # aliases preserves the no-follow policy for every caller-controlled link.
    if sys.platform == "darwin" and supplied.parts[:2] in (
        ("/", "tmp"),
        ("/", "var"),
    ):
        supplied = Path("/private").joinpath(*supplied.parts[1:])
    return supplied


def _read_fd(descriptor: int, maximum: int) -> bytes:
    result = bytearray()
    while len(result) <= maximum:
        block = os.read(descriptor, min(64 * 1024, maximum + 1 - len(result)))
        if not block:
            break
        result.extend(block)
    return bytes(result)


def _plain_bytes(path: Path, maximum: int, label: str) -> bytes:
    path = _normalized_artifact_path(path, label)
    if (
        os.name == "nt"
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
    ):
        raise PersonaArtifactError("descriptor-relative no-follow reads are unavailable")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    bindings: list[tuple[int, str, int, tuple[int, ...]]] = []
    file_descriptor = -1
    try:
        parent = os.open(path.anchor, directory_flags)
        descriptors.append(parent)
        for component in path.parts[1:-1]:
            try:
                named = os.stat(component, dir_fd=parent, follow_symlinks=False)
                child = os.open(component, directory_flags, dir_fd=parent)
            except OSError as error:
                raise PersonaArtifactError(
                    f"cannot bind {label} path without following links"
                ) from error
            opened = os.fstat(child)
            if (
                not stat.S_ISDIR(named.st_mode)
                or not stat.S_ISDIR(opened.st_mode)
                or _directory_identity(named) != _directory_identity(opened)
            ):
                os.close(child)
                raise PersonaArtifactError(f"{label} ancestor changed while opening")
            descriptors.append(child)
            bindings.append((parent, component, child, _directory_identity(opened)))
            parent = child

        try:
            named_before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            file_descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        except OSError as error:
            raise PersonaArtifactError(f"cannot open {label} without following links") from error
        opened = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(named_before.st_mode)
            or named_before.st_nlink != 1
            or named_before.st_size < 0
            or named_before.st_size > maximum
            or _stable(named_before) != _stable(opened)
        ):
            raise PersonaArtifactError(f"{label} is not a bounded single-link file")

        raw = _read_fd(file_descriptor, maximum)
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        repeated = _read_fd(file_descriptor, maximum)
        named_after = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        after = os.fstat(file_descriptor)
        if (
            len(raw) > maximum
            or raw != repeated
            or len(raw) != opened.st_size
            or _stable(after) != _stable(opened)
            or _stable(named_after) != _stable(opened)
        ):
            raise PersonaArtifactError(f"{label} changed while reading")

        for bound_parent, component, child, expected in reversed(bindings):
            current_named = os.stat(
                component, dir_fd=bound_parent, follow_symlinks=False
            )
            if (
                _directory_identity(current_named) != expected
                or _directory_identity(os.fstat(child)) != expected
            ):
                raise PersonaArtifactError(f"{label} ancestor changed while reading")
        return raw
    except PersonaArtifactError:
        raise
    except OSError as error:
        raise PersonaArtifactError(f"cannot read {label} safely") from error
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def read_exact_artifact(
    path: Path, label: str, maximum: int
) -> tuple[bytes, str]:
    raw = _plain_bytes(path, maximum, label)
    return raw, "sha256:" + hashlib.sha256(raw).hexdigest()


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise PersonaArtifactError(f"{label} is not strict JSON") from error
    if not isinstance(value, dict):
        raise PersonaArtifactError(f"{label} must be an object")
    return value


def _safe_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024:
        raise PersonaArtifactError("invalid scope path")
    parts = value.split("/")
    if len(parts) > 20 or any(not _PATH_COMPONENT.fullmatch(part) for part in parts):
        raise PersonaArtifactError("unsafe scope path")
    return value


def _people(plan: dict[str, object]) -> tuple[PersonTopology, ...]:
    personas = plan.get("personas")
    if not isinstance(personas, list) or not 1 <= len(personas) <= 20:
        raise PersonaArtifactError("invalid persona topology")
    people: list[PersonTopology] = []
    seen_people: set[str] = set()
    for person in personas:
        if not isinstance(person, dict):
            raise PersonaArtifactError("invalid person topology")
        persona_id = person.get("id")
        role = person.get("role")
        scopes = person.get("scopes")
        if (
            not isinstance(persona_id, str)
            or not _PERSONA_ID.fullmatch(persona_id)
            or persona_id in seen_people
            or not isinstance(role, str)
            or not _ID.fullmatch(role)
            or not isinstance(scopes, list)
            or len(scopes) > 20
        ):
            raise PersonaArtifactError("invalid person topology")
        seen_people.add(persona_id)
        parsed: list[ScopeTopology] = []
        seen_scope_ids: set[str] = set()
        seen_scope_paths: set[str] = set()
        for scope in scopes:
            if not isinstance(scope, dict):
                raise PersonaArtifactError("invalid scope topology")
            scope_id = scope.get("id")
            scope_path = _safe_path(scope.get("path"))
            if (
                not isinstance(scope_id, str)
                or not _ID.fullmatch(scope_id)
                or scope_id in seen_scope_ids
                or scope_path in seen_scope_paths
            ):
                raise PersonaArtifactError("invalid scope topology")
            seen_scope_ids.add(scope_id)
            seen_scope_paths.add(scope_path)
            parsed.append(ScopeTopology(scope_id, scope_path))
        people.append(PersonTopology(persona_id, role, tuple(parsed)))
    return tuple(people)


def parse_plan_topology_bytes(
    raw: bytes, label: str = "plan artifact"
) -> tuple[str, str, tuple[PersonTopology, ...]]:
    """Parse only the safe filesystem topology carried by a Rust plan."""
    value = _json(raw, label)
    fixture = value.get("fixture_id")
    profile = value.get("profile")
    if (
        value.get("schema") != PLAN_SCHEMA
        or fixture != FIXTURE_ID
        or profile not in {"tiny", "pilot", "full"}
    ):
        raise PersonaArtifactError("plan fixture/profile mismatch")
    return fixture, profile, _people(value)


def load_plan_topology(
    plan: Path,
) -> tuple[str, str, str, tuple[PersonTopology, ...]]:
    """Read a Rust plan only for safe workspace topology; not semantic approval."""
    raw, plan_sha = read_exact_artifact(plan, "plan artifact", MAX_PLAN_BYTES)
    fixture, profile, people = parse_plan_topology_bytes(raw)
    return fixture, profile, plan_sha, people


def artifact_bundle_record(
    *,
    fixture_id: str,
    profile: str,
    plan_digest: str,
    plan_sha256: str,
    schedule_sha256: str,
    render_sha256: str,
) -> dict[str, object]:
    """Return the exact non-authorizing artifact identity envelope."""
    return {
        "schema": ARTIFACT_BUNDLE_SCHEMA,
        "fixture_id": fixture_id,
        "profile": profile,
        "plan_digest": plan_digest,
        "plan_sha256": plan_sha256,
        "schedule_sha256": schedule_sha256,
        "render_sha256": render_sha256,
    }
def load_bundle(plan: Path, schedule: Path, render: Path) -> ArtifactBundle:
    """Bind Rust artifacts; topology output is deliberately non-authorizing."""
    plan_raw, plan_sha = read_exact_artifact(plan, "plan artifact", MAX_PLAN_BYTES)
    schedule_raw, schedule_sha = read_exact_artifact(
        schedule, "schedule artifact", MAX_SCHEDULE_BYTES
    )
    render_raw, render_sha = read_exact_artifact(
        render, "render artifact", MAX_RENDER_BYTES
    )
    fixture, profile, people = parse_plan_topology_bytes(plan_raw)
    schedule_value = _json(schedule_raw, "schedule artifact")
    render_value = _json(render_raw, "render artifact")
    if (
        schedule_value.get("schema") != SCHEDULE_SCHEMA
        or render_value.get("schema") != RENDER_SCHEMA
    ):
        raise PersonaArtifactError("artifact schema mismatch")
    # Rust artifacts carry the plan content digest. Python binds the exact bytes
    # but does not attempt to reproduce Rust's semantic validation.
    plan_digest = "sha256:" + hashlib.sha256(plan_raw).hexdigest()
    if (
        schedule_value.get("plan_digest") != plan_digest
        or render_value.get("plan_digest") != plan_digest
        or render_value.get("fixture_id") != fixture
        or render_value.get("profile") != profile
    ):
        raise PersonaArtifactError("artifact bundle plan binding mismatch")
    return ArtifactBundle(
        fixture,
        profile,
        plan_digest,
        plan_sha,
        schedule_sha,
        render_sha,
        people,
    )
