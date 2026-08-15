#!/usr/bin/env python3
"""Safely scaffold the skill-authored 20-persona corpus.

The command creates directories and production-control metadata only. All path
resolution after binding the target parent is descriptor-relative and rejects
symlinks, unexpected object types, foreign owners, and permissive directories.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import sys
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 4
OWNER_FILE = ".kio-persona-skill-corpus-owner.json"
WORKSPACE_FILE = "WORKSPACE.md"
MAX_CONTROL_FILE_BYTES = 4 * 1024 * 1024
PRODUCTION_DIRS = (
    "prompts",
    "temp",
    "renders/docx",
    "renders/pdf",
    "renders/xlsx",
    "renders/pptx",
    "renders/image",
    "evidence/docx",
    "evidence/pdf",
    "evidence/xlsx",
    "evidence/pptx",
    "evidence/image",
)
SCOPE_PRODUCTION_DIRS = (
    "prompts",
    "temp",
    "renders/docx",
    "renders/pdf",
    "renders/xlsx",
    "renders/pptx",
    "renders/image",
    "evidence/docx",
    "evidence/pdf",
    "evidence/xlsx",
    "evidence/pptx",
    "evidence/image",
)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", None)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", None)
_DIRECTORY_FLAGS = os.O_RDONLY | (_O_DIRECTORY or 0) | (_O_NOFOLLOW or 0)
_FILE_NOFOLLOW = _O_NOFOLLOW or 0


class ScaffoldError(RuntimeError):
    """Raised when a target cannot safely host this corpus layout."""


def _require_descriptor_capabilities() -> None:
    """Fail closed when the platform cannot enforce descriptor no-follow walks."""
    if not isinstance(_O_DIRECTORY, int) or _O_DIRECTORY == 0:
        raise ScaffoldError("required descriptor flag O_DIRECTORY is unavailable")
    if not isinstance(_O_NOFOLLOW, int) or _O_NOFOLLOW == 0:
        raise ScaffoldError("required descriptor flag O_NOFOLLOW is unavailable")


def _absolute_lexical(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    # macOS publishes these fixed aliases at the root. Rewrite only those
    # platform-owned aliases; arbitrary user symlinks remain denied.
    if sys.platform == "darwin" and absolute.parts[:2] in (("/", "tmp"), ("/", "var")):
        absolute = Path("/private").joinpath(*absolute.parts[1:])
    return absolute


def _normal_components(relative_path: str | PurePosixPath) -> tuple[str, ...]:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ScaffoldError(f"unsafe relative path: {relative_path}")
    return path.parts


def _validate_owned_directory(descriptor: int, label: str) -> None:
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise ScaffoldError(f"not a directory: {label}")
    if metadata.st_uid != os.getuid():
        raise ScaffoldError(f"directory is not owned by the current user: {label}")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise ScaffoldError(f"directory is group/world writable: {label}")


def _open_absolute_directory(path: Path) -> int:
    _require_descriptor_capabilities()
    if not path.is_absolute():
        raise ScaffoldError(f"path must be absolute: {path}")
    descriptor = os.open(path.anchor, _DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            try:
                next_descriptor = os.open(
                    component, _DIRECTORY_FLAGS, dir_fd=descriptor
                )
            except OSError as error:
                raise ScaffoldError(
                    f"cannot bind no-follow directory {path}: {error}"
                ) from error
            os.close(descriptor)
            descriptor = next_descriptor
        _validate_owned_directory(descriptor, os.fspath(path))
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_directory_at(parent: int, component: str, label: str) -> int:
    try:
        descriptor = os.open(component, _DIRECTORY_FLAGS, dir_fd=parent)
    except OSError as error:
        raise ScaffoldError(f"cannot open no-follow directory {label}: {error}") from error
    try:
        _validate_owned_directory(descriptor, label)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _ensure_directory_at(parent: int, relative_path: str, label: str) -> int:
    descriptor = os.dup(parent)
    try:
        for component in _normal_components(relative_path):
            try:
                os.mkdir(component, 0o700, dir_fd=descriptor)
                os.fsync(descriptor)
            except FileExistsError:
                pass
            next_descriptor = _open_directory_at(
                descriptor, component, f"{label}/{component}"
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _validate_regular_file(
    metadata: os.stat_result, label: str, *, allow_read_only_public: bool = False
) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise ScaffoldError(f"control file is not regular: {label}")
    if metadata.st_nlink != 1:
        raise ScaffoldError(f"control file must have exactly one link: {label}")
    if metadata.st_uid != os.getuid():
        raise ScaffoldError(f"control file is not owned by the current user: {label}")
    forbidden_mode = 0o022 if allow_read_only_public else 0o077
    if stat.S_IMODE(metadata.st_mode) & forbidden_mode:
        raise ScaffoldError(f"control file permissions are too broad: {label}")


def _write_new_text_at(directory: int, name: str, text: str, label: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory)
    except OSError as error:
        raise ScaffoldError(f"cannot create control file {label}: {error}") from error
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(directory)


def _replace_text_at(
    directory: int, name: str, text: str, label: str, *, allow_read_only_public: bool = False
) -> None:
    """Atomically replace an already-validated, single-link control file."""
    try:
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except OSError as error:
        raise ScaffoldError(f"cannot inspect control file {label}: {error}") from error
    _validate_regular_file(
        metadata, label, allow_read_only_public=allow_read_only_public
    )
    temporary_name = f".{name}.replace-{secrets.token_hex(16)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=directory)
        _validate_regular_file(os.fstat(descriptor), f"{label} replacement")
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    except OSError as error:
        raise ScaffoldError(f"cannot atomically update control file {label}: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory)
        except FileNotFoundError:
            pass


def _read_text_at(
    directory: int, name: str, label: str, *, allow_read_only_public: bool = False
) -> str:
    try:
        descriptor = os.open(name, os.O_RDONLY | _FILE_NOFOLLOW, dir_fd=directory)
    except OSError as error:
        raise ScaffoldError(f"cannot open control file {label}: {error}") from error
    try:
        opened = os.fstat(descriptor)
        _validate_regular_file(
            opened, label, allow_read_only_public=allow_read_only_public
        )
        if opened.st_size < 0 or opened.st_size > MAX_CONTROL_FILE_BYTES:
            raise ScaffoldError(f"control file exceeds byte bound: {label}")
        raw = bytearray()
        while len(raw) <= MAX_CONTROL_FILE_BYTES:
            block = os.read(
                descriptor,
                min(64 * 1024, MAX_CONTROL_FILE_BYTES + 1 - len(raw)),
            )
            if not block:
                break
            raw.extend(block)
        after = os.fstat(descriptor)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (
            len(raw) > MAX_CONTROL_FILE_BYTES
            or len(raw) != opened.st_size
            or (after.st_dev, after.st_ino, after.st_size, after.st_nlink)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_nlink)
            or (named.st_dev, named.st_ino, named.st_size, named.st_nlink)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_nlink)
        ):
            raise ScaffoldError(f"control file changed while reading: {label}")
        try:
            return bytes(raw).decode("utf-8")
        except UnicodeDecodeError as error:
            raise ScaffoldError(f"control file is not UTF-8: {label}") from error
    finally:
        os.close(descriptor)


def _write_new_json_at(directory: int, name: str, payload: object, label: str) -> None:
    _write_new_text_at(
        directory,
        name,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        label,
    )


def _validate_existing_control_file(
    directory: int,
    name: str,
    label: str,
    *,
    expect_json: bool,
    allow_read_only_public: bool = False,
) -> bool:
    try:
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return False
    _validate_regular_file(
        metadata, label, allow_read_only_public=allow_read_only_public
    )
    if expect_json:
        try:
            json.loads(
                _read_text_at(
                    directory,
                    name,
                    label,
                    allow_read_only_public=allow_read_only_public,
                )
            )
        except ValueError as error:
            raise ScaffoldError(f"invalid JSON control file: {label}") from error
    return True
LEASE_FILE = "lease.json"
LOCK_FILE = ".lease.lock"
RECOVERY_LOG = "lease-recovery.jsonl"
PLAN_FILE = "persona-plan.json"


def _json_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def scope_control_id(relative_path: str) -> str:
    try:
        parts = _normal_components(relative_path)
    except ScaffoldError:
        raise
    return "scope-" + hashlib.sha256("/".join(parts).encode("utf-8")).hexdigest()


def _plan(root_plan: Path):
    from .persona_artifacts import (
        MAX_PLAN_BYTES,
        PersonaArtifactError,
        load_plan_topology,
        read_exact_artifact,
    )
    try:
        root_plan = Path(root_plan)
        fixture, profile, digest, people = load_plan_topology(root_plan)
        raw, repeated = read_exact_artifact(root_plan, "plan artifact", MAX_PLAN_BYTES)
    except PersonaArtifactError as error:
        raise ScaffoldError(str(error)) from error
    if digest != repeated:
        raise ScaffoldError("plan digest changed while binding")
    return fixture, profile, digest, people, raw


def _owner_payload(fixture: str, profile: str, plan_sha256: str) -> dict[str, object]:
    return {
        "schema": "kio.persona.skill-corpus/v4",
        "fixture_id": fixture,
        "profile": profile,
        "plan_sha256": plan_sha256,
    }


def _read_owner(root_descriptor: int, root: Path) -> dict[str, object]:
    try:
        value = json.loads(_read_text_at(root_descriptor, OWNER_FILE, os.fspath(root / OWNER_FILE), allow_read_only_public=True))
    except ValueError as error:
        raise ScaffoldError("invalid owner marker") from error
    if not isinstance(value, dict):
        raise ScaffoldError("invalid owner marker")
    return value


def _validate_owner(root_descriptor: int, root: Path, expected: dict[str, object]) -> None:
    if _read_owner(root_descriptor, root) != expected:
        raise ScaffoldError("owner marker does not match exact Rust plan artifact")


def _bind_root(root: Path, *, resume: bool, owner: dict[str, object], plan_raw: bytes) -> int:
    if not root.name or root.name in (".", ".."):
        raise ScaffoldError(f"unsafe corpus root: {root}")
    try:
        parent = _open_absolute_directory(root.parent)
    except FileNotFoundError as error:
        raise ScaffoldError(f"target parent must already exist: {root.parent}") from error
    try:
        created = False
        try:
            os.mkdir(root.name, 0o700, dir_fd=parent)
            os.fsync(parent)
            created = True
        except FileExistsError:
            if not resume:
                raise ScaffoldError(f"target already exists; use --resume for an owned root: {root}")
        descriptor = _open_directory_at(parent, root.name, os.fspath(root))
    finally:
        os.close(parent)
    try:
        if created:
            _write_new_text_at(descriptor, OWNER_FILE, _json_text(owner), os.fspath(root / OWNER_FILE))
            _write_new_text_at(descriptor, PLAN_FILE, plan_raw.decode("utf-8"), os.fspath(root / PLAN_FILE))
        else:
            _validate_owner(descriptor, root, owner)
            existing = _read_text_at(descriptor, PLAN_FILE, os.fspath(root / PLAN_FILE))
            if existing.encode("utf-8") != plan_raw:
                raise ScaffoldError("stored plan artifact does not exactly match requested plan")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _ensure_json(directory: int, name: str, payload: object, label: str) -> None:
    expected = _json_text(payload)
    if _validate_existing_control_file(directory, name, label, expect_json=True):
        if _read_text_at(directory, name, label) != expected:
            raise ScaffoldError(f"control file does not match exact v4 scaffold: {label}")
    else:
        _write_new_text_at(directory, name, expected, label)


def _ensure_text(directory: int, name: str, text: str, label: str) -> None:
    if _validate_existing_control_file(directory, name, label, expect_json=False):
        if _read_text_at(directory, name, label) != text:
            raise ScaffoldError(f"control file does not match exact v4 scaffold: {label}")
    else:
        _write_new_text_at(directory, name, text, label)


def _persona_slug(person) -> str:
    return f"{person.persona_id}-{person.role}"


def _persona_workspace(slug: str) -> str:
    return f"# {slug} workspace\n\nThis workspace is bound to a Rust persona plan artifact. Claim the exclusive persona lease before assigning exact plan scopes.\n"


def _scope_workspace(slug: str, scope_path: str) -> str:
    return f"# {slug} scope workspace\n\nAssigned Rust-plan scope: `{scope_path}`.\n"


def _create_control_files(control: int, slug: str, persona_id: str) -> None:
    _ensure_json(control, "status.json", {"schema": "kio.persona.skill-corpus/v4", "persona_id": persona_id, "state": "scaffolded"}, f"{slug}/_production/status.json")
    for name, value in (("inventory.jsonl", ""), ("provenance.jsonl", ""), ("qa.jsonl", ""), (LOCK_FILE, "\0"), (RECOVERY_LOG, "")):
        _ensure_text(control, name, value, f"{slug}/_production/{name}")
    _validate_existing_control_file(control, LEASE_FILE, f"{slug}/_production/{LEASE_FILE}", expect_json=True)


def scaffold(root: Path, *, plan: Path, resume: bool = False) -> Path:
    _require_descriptor_capabilities()
    root = _absolute_lexical(root)
    fixture, profile, digest, people, raw = _plan(Path(plan))
    owner = _owner_payload(fixture, profile, digest)
    root_descriptor = _bind_root(root, resume=resume, owner=owner, plan_raw=raw)
    try:
        for person in people:
            slug = _persona_slug(person)
            persona = _ensure_directory_at(root_descriptor, slug, os.fspath(root / slug))
            try:
                _ensure_text(persona, WORKSPACE_FILE, _persona_workspace(slug), os.fspath(root / slug / WORKSPACE_FILE))
                home = _ensure_directory_at(persona, "home", f"{slug}/home")
                control = _ensure_directory_at(persona, "_production", f"{slug}/_production")
                try:
                    _create_control_files(control, slug, person.persona_id)
                    scopes = _ensure_directory_at(control, "scopes", f"{slug}/_production/scopes")
                    try:
                        for scope in person.scopes:
                            home_scope = _ensure_directory_at(home, scope.path, f"{slug}/home/{scope.path}")
                            os.close(home_scope)
                            scope_id = scope_control_id(scope.path)
                            scope_control = _ensure_directory_at(scopes, scope_id, f"{slug}/_production/scopes/{scope_id}")
                            try:
                                _ensure_text(scope_control, WORKSPACE_FILE, _scope_workspace(slug, scope.path), f"{slug}/_production/scopes/{scope_id}/{WORKSPACE_FILE}")
                                _ensure_json(scope_control, "assignment.json", {"schema": "kio.persona.skill-corpus/v4", "persona_id": person.persona_id, "scope_id": scope.scope_id, "scope_path": scope.path, "scope_control_id": scope_id, "state": "unassigned"}, f"{slug}/_production/scopes/{scope_id}/assignment.json")
                                for name, value in ((LOCK_FILE, "\0"), (RECOVERY_LOG, ""), ("inventory.jsonl", ""), ("provenance.jsonl", ""), ("qa.jsonl", "")):
                                    _ensure_text(scope_control, name, value, f"{slug}/_production/scopes/{scope_id}/{name}")
                                _validate_existing_control_file(scope_control, LEASE_FILE, f"{slug}/_production/scopes/{scope_id}/{LEASE_FILE}", expect_json=True)
                            finally:
                                os.close(scope_control)
                    finally:
                        os.close(scopes)
                finally:
                    os.close(home); os.close(control)
            finally:
                os.close(persona)
    finally:
        os.close(root_descriptor)
    return root


def _open_existing_root(root: Path) -> int:
    """Open a v4 owned root without following any component or control file."""
    _require_descriptor_capabilities()
    root = _absolute_lexical(root)
    try:
        parent = _open_absolute_directory(root.parent)
    except FileNotFoundError as error:
        raise ScaffoldError(f"corpus root does not exist: {root}") from error
    try:
        descriptor = _open_directory_at(parent, root.name, os.fspath(root))
    finally:
        os.close(parent)
    try:
        # The plan is read descriptor-relatively so a replacement cannot redirect
        # membership lookup outside the workspace binding.
        raw = _read_text_at(descriptor, PLAN_FILE, os.fspath(root / PLAN_FILE)).encode("utf-8")
        from .persona_artifacts import PersonaArtifactError, parse_plan_topology_bytes
        try:
            fixture, profile, people = parse_plan_topology_bytes(raw, "stored plan")
        except PersonaArtifactError as error:
            raise ScaffoldError(str(error)) from error
        owner = _owner_payload(fixture, profile, _digest(raw))
        _validate_owner(descriptor, root, owner)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def load_workspace_topology_at(root_descriptor: int, root: Path):
    """Read authoritative topology from an already-bound workspace descriptor.

    Callers that subsequently mutate the workspace must retain this descriptor;
    resolving ``root`` again after this check could bind a replacement directory.
    """
    root = _absolute_lexical(root)
    raw = _read_text_at(
        root_descriptor, PLAN_FILE, os.fspath(root / PLAN_FILE)
    ).encode("utf-8")
    from .persona_artifacts import PersonaArtifactError, parse_plan_topology_bytes

    try:
        fixture, profile, people = parse_plan_topology_bytes(raw, "stored plan")
    except PersonaArtifactError as error:
        raise ScaffoldError(str(error)) from error
    _validate_owner(
        root_descriptor, root, _owner_payload(fixture, profile, _digest(raw))
    )
    return people


def load_workspace_topology(root: Path):
    """Return stored Rust-plan topology after validating the owner binding."""
    descriptor = _open_existing_root(root)
    try:
        return load_workspace_topology_at(descriptor, root)
    finally:
        os.close(descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a Rust-plan-bound persona corpus workspace.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        root = scaffold(args.root, plan=args.plan, resume=args.resume)
    except (OSError, ScaffoldError) as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    print(f"[ok] persona skill corpus scaffold: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
