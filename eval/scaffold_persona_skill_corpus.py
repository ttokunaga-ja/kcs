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

if __package__ in (None, ""):
    sys.path.insert(0, os.fspath(Path(__file__).resolve().parents[1]))

from eval import persona_fixture_spec as spec


SCHEMA_VERSION = 3
OWNER_FILE = ".kio-persona-skill-corpus-owner.json"
WORKSPACE_FILE = "WORKSPACE.md"
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
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class ScaffoldError(RuntimeError):
    """Raised when a target cannot safely host this corpus layout."""


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
        _validate_regular_file(
            os.fstat(descriptor),
            label,
            allow_read_only_public=allow_read_only_public,
        )
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
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


def _owner_payload(version: int = SCHEMA_VERSION) -> dict[str, object]:
    return {
        "schema_version": version,
        "kind": "kio-persona-skill-corpus",
        "source_spec": "eval/persona_fixture_spec.py",
        "personas": [f"{row['id']}-{row['role']}" for row in spec.PERSONAS],
    }


def _read_owner(root_descriptor: int, root: Path) -> dict[str, object]:
    label = os.fspath(root / OWNER_FILE)
    try:
        actual = json.loads(
            _read_text_at(
                root_descriptor,
                OWNER_FILE,
                label,
                allow_read_only_public=True,
            )
        )
    except ValueError as error:
        raise ScaffoldError(f"invalid owner marker: {label}") from error
    return actual


def _validate_owner(root_descriptor: int, root: Path) -> int:
    actual = _read_owner(root_descriptor, root)
    if actual == _owner_payload():
        return SCHEMA_VERSION
    if actual == _owner_payload(2):
        return 2
    raise ScaffoldError(f"owner marker does not match this scaffold version: {root / OWNER_FILE}")


def _open_existing_root(root: Path) -> int:
    root = _absolute_lexical(root)
    try:
        parent_descriptor = _open_absolute_directory(root.parent)
    except FileNotFoundError as error:
        raise ScaffoldError(f"corpus root does not exist: {root}") from error
    try:
        root_descriptor = _open_directory_at(
            parent_descriptor, root.name, os.fspath(root)
        )
    except BaseException:
        os.close(parent_descriptor)
        raise
    os.close(parent_descriptor)
    try:
        _validate_owner(root_descriptor, root)
        return root_descriptor
    except BaseException:
        os.close(root_descriptor)
        raise


def _bind_root(root: Path, *, resume: bool) -> tuple[int, int]:
    if not root.name or root.name in (".", ".."):
        raise ScaffoldError(f"unsafe corpus root: {root}")
    try:
        parent_descriptor = _open_absolute_directory(root.parent)
    except FileNotFoundError as error:
        raise ScaffoldError(f"target parent must already exist: {root.parent}") from error
    try:
        created = False
        try:
            os.mkdir(root.name, 0o700, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
            created = True
        except FileExistsError:
            if not resume:
                raise ScaffoldError(
                    f"target already exists; use --resume for an owned root: {root}"
                )
        root_descriptor = _open_directory_at(parent_descriptor, root.name, os.fspath(root))
    finally:
        os.close(parent_descriptor)
    if created:
        _write_new_json_at(
            root_descriptor, OWNER_FILE, _owner_payload(), os.fspath(root / OWNER_FILE)
        )
    else:
        existing_version = _validate_owner(root_descriptor, root)
    return root_descriptor, (SCHEMA_VERSION if created else existing_version)


def _persona_initial_files(persona: dict[str, object], *, version: int = SCHEMA_VERSION) -> dict[str, object]:
    return {
        "status.json": {
            "persona_id": persona["id"],
            "role": persona["role"],
            "owner_session": None,
            "state": "scaffolded",
            "current_batch": None,
            "completed_artifacts": 0,
            "last_verified_inventory_line": 0,
            "next_action": "claim an exclusive persona lease",
            "blocking_issue": None,
            "updated_at": None,
        },
        "manifest.json": {
            "schema_version": version,
            "persona_id": persona["id"],
            "role": persona["role"],
            "source_spec": "eval/persona_fixture_spec.py",
            "full_raw_files": persona["full_raw_files"],
            "format_percentages": persona["format_percentages"],
            "format_variant_counts_200": spec.format_variant_counts(persona, "tiny"),
            "primary_paths": list(persona["primary_paths"]),
            "secondary_paths": list(spec.SECONDARY_PATHS),
            "inventory": "inventory.jsonl",
            "provenance": "provenance.jsonl",
            "qa": "qa.jsonl",
            "artifact_join_key": "artifact_id",
        },
        "narrative.json": {
            "schema_version": version,
            "persona_id": persona["id"],
            "fictional_entities": [],
            "timeline": [],
            "terminology": {},
            "numeric_anchors": {},
        },
    }


def _workspace_text(persona: dict[str, object]) -> str:
    slug = f"{persona['id']}-{persona['role']}"
    return (
        f"# {slug} workspace\n\n"
        f"The parent chat session exclusively owns the `{slug}/` persona folder.\n"
        "The parent holds each scope lease and assigns one authoritative `home/` leaf "
        "folder to each subagent. A subagent creates only the fixed files listed for "
        "that folder and updates only its permitted scope-local production records.\n\n"
        "Read the production rules before working:\n\n"
        "- `../../tasks/persona-skill-corpus/COMMON_RULES.md`\n"
        "- `../../tasks/persona-skill-corpus/BATCH_PROTOCOL.md`\n"
        f"- `../../tasks/persona-skill-corpus/personas/{slug}.md`\n"
    )


def _validate_workspace_file(directory: int, persona: dict[str, object], label: str, *, previous_version: int | None) -> None:
    if not _validate_existing_control_file(
        directory,
        WORKSPACE_FILE,
        label,
        expect_json=False,
        allow_read_only_public=True,
    ):
        _write_new_text_at(directory, WORKSPACE_FILE, _workspace_text(persona), label)
        return
    actual = _read_text_at(
        directory,
        WORKSPACE_FILE,
        label,
        allow_read_only_public=True,
    )
    if actual == _workspace_text(persona):
        return
    if actual in (_workspace_text_v2(persona), _workspace_text_v3_initial(persona)):
        _replace_text_at(
            directory,
            WORKSPACE_FILE,
            _workspace_text(persona),
            label,
            allow_read_only_public=True,
        )
        return
    else:
        raise ScaffoldError(f"workspace file does not match this scaffold version: {label}")


def _workspace_text_v2(persona: dict[str, object]) -> str:
    slug = f"{persona['id']}-{persona['role']}"
    return (
        f"# {slug} workspace\n\n"
        f"This session owns only the `{slug}/` persona folder.\n\n"
        "Read the production rules before working:\n\n"
        "- `../../tasks/persona-skill-corpus/COMMON_RULES.md`\n"
        "- `../../tasks/persona-skill-corpus/BATCH_PROTOCOL.md`\n"
        f"- `../../tasks/persona-skill-corpus/personas/{slug}.md`\n"
    )


def _workspace_text_v3_initial(persona: dict[str, object]) -> str:
    """Return the exact first v3 text so resume can converge tracked scaffolds."""
    slug = f"{persona['id']}-{persona['role']}"
    return (
        f"# {slug} workspace\n\n"
        f"The parent chat session exclusively owns the `{slug}/` persona folder.\n"
        "Each subagent claims one assigned authoritative `home/` scope and may write "
        "only that folder plus its matching `_production/scopes/` control folder.\n\n"
        "Read the production rules before working:\n\n"
        "- `../../tasks/persona-skill-corpus/COMMON_RULES.md`\n"
        "- `../../tasks/persona-skill-corpus/BATCH_PROTOCOL.md`\n"
        f"- `../../tasks/persona-skill-corpus/personas/{slug}.md`\n"
    )


def scope_control_id(relative_path: str) -> str:
    """Return the stable, safe on-disk ID for one authoritative scope path."""
    try:
        spec.validate_relative_scope(relative_path)
    except ValueError as error:
        raise ScaffoldError(f"invalid scope path: {relative_path}") from error
    return "scope-" + hashlib.sha256(relative_path.encode("ascii")).hexdigest()


def _scope_initial_files(persona: dict[str, object], relative_path: str) -> dict[str, object]:
    return {
        "status.json": {"schema_version": 1, "persona_id": persona["id"], "scope_path": relative_path, "state": "scaffolded", "completed_artifacts": 0},
        "manifest.json": {"schema_version": 1, "persona_id": persona["id"], "scope_path": relative_path, "scope_id": scope_control_id(relative_path), "artifact_join_key": "artifact_id"},
        "assignment.json": {
            "schema_version": 1,
            "persona_id": persona["id"],
            "scope_path": relative_path,
            "scope_id": scope_control_id(relative_path),
            "assigned_parent_session": None,
            "assigned_worker_session": None,
            "state": "unassigned",
            "files": [],
        },
    }


def _upgrade_v2_persona_payload(
    persona: dict[str, object], name: str, actual: object, current: dict[str, object]
) -> dict[str, object] | None:
    """Upgrade v2 shared JSON without discarding parent-authored metadata."""
    if name == "status.json":
        return None  # v2 status intentionally had no schema_version field.
    if not isinstance(actual, dict):
        raise ScaffoldError(f"v2 {name} is not an object for {persona['id']}")
    if actual.get("persona_id") != persona["id"]:
        raise ScaffoldError(f"v2 {name} has the wrong persona identity for {persona['id']}")
    if name == "manifest.json" and actual.get("role") != persona["role"]:
        raise ScaffoldError(f"v2 manifest has the wrong role identity for {persona['id']}")
    version = actual.get("schema_version")
    if version == SCHEMA_VERSION:
        return None
    if version != 2:
        raise ScaffoldError(f"unsupported shared control schema in {name} for {persona['id']}")
    upgraded = dict(actual)
    for key, value in current.items():
        upgraded.setdefault(key, value)
    upgraded["schema_version"] = SCHEMA_VERSION
    return upgraded


def _scope_workspace_text(persona: dict[str, object], relative_path: str) -> str:
    slug = f"{persona['id']}-{persona['role']}"
    return (
        f"# {slug} scope worker workspace\n\n"
        f"Assigned home scope: `../../../home/{relative_path}/`\n\n"
        "The parent chat owns persona-level shared metadata and this scope's immutable "
        "`WORKSPACE.md`, `manifest.json`, `assignment.json`, and lease controls. Read "
        "`assignment.json` before work. This worker may create only its listed final "
        "files in the assigned home scope and may update only scope-local status, "
        "inventory, provenance, QA, prompts, temp, renders, and evidence.\n"
    )


def _scope_workspace_text_initial(persona: dict[str, object], relative_path: str) -> str:
    slug = f"{persona['id']}-{persona['role']}"
    return (
        f"# {slug} scope worker workspace\n\n"
        f"Assigned home scope: `../../../home/{relative_path}/`\n\n"
        "The parent chat owns persona-level shared metadata. This worker may write only "
        "the assigned home scope and this `_production/scopes/` directory.\n"
    )


def _validate_scope_workspace_file(scope_control: int, persona: dict[str, object], relative_path: str, label: str) -> None:
    expected = _scope_workspace_text(persona, relative_path)
    if not _validate_existing_control_file(scope_control, WORKSPACE_FILE, label, expect_json=False, allow_read_only_public=True):
        _write_new_text_at(scope_control, WORKSPACE_FILE, expected, label)
        return
    actual = _read_text_at(
        scope_control, WORKSPACE_FILE, label, allow_read_only_public=True
    )
    if actual == expected:
        return
    if actual == _scope_workspace_text_initial(persona, relative_path):
        _replace_text_at(
            scope_control,
            WORKSPACE_FILE,
            expected,
            label,
            allow_read_only_public=True,
        )
        return
    raise ScaffoldError(f"scope workspace file does not match authoritative scope: {label}")


def scaffold(root: Path, *, resume: bool = False) -> Path:
    root = _absolute_lexical(root)
    root_descriptor, previous_version = _bind_root(root, resume=resume)
    try:
        for persona in spec.PERSONAS:
            slug = f"{persona['id']}-{persona['role']}"
            persona_root = _ensure_directory_at(root_descriptor, slug, os.fspath(root / slug))
            try:
                _validate_workspace_file(
                    persona_root, persona, os.fspath(root / slug / WORKSPACE_FILE), previous_version=previous_version
                )
                home = _ensure_directory_at(
                    persona_root, "home", os.fspath(root / slug / "home")
                )
                control = _ensure_directory_at(
                    persona_root, "_production", os.fspath(root / slug / "_production")
                )
                try:
                    for relative_path in spec.all_scope_paths(persona):
                        descriptor = _ensure_directory_at(home, relative_path, relative_path)
                        os.close(descriptor)
                    for relative_path in PRODUCTION_DIRS:
                        descriptor = _ensure_directory_at(control, relative_path, relative_path)
                        os.close(descriptor)

                    scopes = _ensure_directory_at(control, "scopes", f"{slug}/_production/scopes")
                    try:
                        for relative_path in spec.all_scope_paths(persona):
                            scope_id = scope_control_id(relative_path)
                            scope_control = _ensure_directory_at(scopes, scope_id, f"{slug}/_production/scopes/{scope_id}")
                            try:
                                _validate_scope_workspace_file(
                                    scope_control,
                                    persona,
                                    relative_path,
                                    f"{slug}/_production/scopes/{scope_id}/{WORKSPACE_FILE}",
                                )
                                for scope_dir in SCOPE_PRODUCTION_DIRS:
                                    descriptor = _ensure_directory_at(scope_control, scope_dir, scope_dir)
                                    os.close(descriptor)
                                for name, payload in _scope_initial_files(persona, relative_path).items():
                                    label = f"{slug}/_production/scopes/{scope_id}/{name}"
                                    exists = _validate_existing_control_file(
                                        scope_control, name, label, expect_json=True
                                    )
                                    if not exists:
                                        _write_new_json_at(scope_control, name, payload, label)
                                    elif name == "assignment.json":
                                        actual = json.loads(
                                            _read_text_at(scope_control, name, label)
                                        )
                                        legacy = {
                                            key: value
                                            for key, value in payload.items()
                                            if key not in ("state", "files")
                                        }
                                        if actual == legacy:
                                            _replace_text_at(
                                                scope_control,
                                                name,
                                                json.dumps(
                                                    payload,
                                                    ensure_ascii=False,
                                                    indent=2,
                                                    sort_keys=True,
                                                )
                                                + "\n",
                                                label,
                                            )
                                for name, initial in (("inventory.jsonl", ""), ("provenance.jsonl", ""), ("qa.jsonl", ""), (".lease.lock", "\0"), ("lease-recovery.jsonl", "")):
                                    label = f"{slug}/_production/scopes/{scope_id}/{name}"
                                    if not _validate_existing_control_file(scope_control, name, label, expect_json=False):
                                        _write_new_text_at(scope_control, name, initial, label)
                                _validate_existing_control_file(scope_control, "lease.json", f"{slug}/_production/scopes/{scope_id}/lease.json", expect_json=True)
                            finally:
                                os.close(scope_control)
                    finally:
                        os.close(scopes)

                    for name, payload in _persona_initial_files(persona).items():
                        label = os.fspath(root / slug / "_production" / name)
                        exists = _validate_existing_control_file(
                            control, name, label, expect_json=True
                        )
                        if not exists:
                            _write_new_json_at(control, name, payload, label)
                        elif previous_version == 2:
                            actual = json.loads(_read_text_at(control, name, label))
                            upgraded = _upgrade_v2_persona_payload(persona, name, actual, payload)
                            if upgraded is not None:
                                _replace_text_at(control, name, json.dumps(upgraded, ensure_ascii=False, indent=2, sort_keys=True) + "\n", label)
                    for name in ("inventory.jsonl", "provenance.jsonl", "qa.jsonl"):
                        label = os.fspath(root / slug / "_production" / name)
                        if not _validate_existing_control_file(
                            control, name, label, expect_json=False
                        ):
                            _write_new_text_at(control, name, "", label)
                    for name, initial in (
                        (".lease.lock", "\0"),
                        ("lease-recovery.jsonl", ""),
                    ):
                        label = os.fspath(root / slug / "_production" / name)
                        if not _validate_existing_control_file(
                            control, name, label, expect_json=False
                        ):
                            _write_new_text_at(control, name, initial, label)
                    _validate_existing_control_file(
                        control,
                        "lease.json",
                        os.fspath(root / slug / "_production" / "lease.json"),
                        expect_json=True,
                    )
                finally:
                    os.close(home)
                    os.close(control)
            finally:
                os.close(persona_root)
        if previous_version == 2:
            _replace_text_at(
                root_descriptor,
                OWNER_FILE,
                json.dumps(_owner_payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                os.fspath(root / OWNER_FILE),
                allow_read_only_public=True,
            )
    finally:
        os.close(root_descriptor)
    return root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create the empty layout for the skill-authored 20-persona corpus."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="fill missing directories in an exact, safe, owned scaffold",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        root = scaffold(args.root, resume=args.resume)
    except (OSError, ScaffoldError) as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    print(f"[ok] persona skill corpus scaffold: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
