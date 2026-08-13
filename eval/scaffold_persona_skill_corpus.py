#!/usr/bin/env python3
"""Safely scaffold the skill-authored 20-persona corpus.

The command creates directories and production-control metadata only. All path
resolution after binding the target parent is descriptor-relative and rejects
symlinks, unexpected object types, foreign owners, and permissive directories.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path, PurePosixPath

if __package__ in (None, ""):
    sys.path.insert(0, os.fspath(Path(__file__).resolve().parents[1]))

from eval import persona_fixture_spec as spec


SCHEMA_VERSION = 1
OWNER_FILE = ".kio-persona-skill-corpus-owner.json"
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


def _validate_regular_file(metadata: os.stat_result, label: str) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise ScaffoldError(f"control file is not regular: {label}")
    if metadata.st_nlink != 1:
        raise ScaffoldError(f"control file must have exactly one link: {label}")
    if metadata.st_uid != os.getuid():
        raise ScaffoldError(f"control file is not owned by the current user: {label}")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
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


def _read_text_at(directory: int, name: str, label: str) -> str:
    try:
        descriptor = os.open(name, os.O_RDONLY | _FILE_NOFOLLOW, dir_fd=directory)
    except OSError as error:
        raise ScaffoldError(f"cannot open control file {label}: {error}") from error
    try:
        _validate_regular_file(os.fstat(descriptor), label)
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
    directory: int, name: str, label: str, *, expect_json: bool
) -> bool:
    try:
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return False
    _validate_regular_file(metadata, label)
    if expect_json:
        try:
            json.loads(_read_text_at(directory, name, label))
        except ValueError as error:
            raise ScaffoldError(f"invalid JSON control file: {label}") from error
    return True


def _owner_payload() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kio-persona-skill-corpus",
        "source_spec": "eval/persona_fixture_spec.py",
        "personas": [f"{row['id']}-{row['role']}" for row in spec.PERSONAS],
    }


def _validate_owner(root_descriptor: int, root: Path) -> None:
    label = os.fspath(root / OWNER_FILE)
    try:
        actual = json.loads(_read_text_at(root_descriptor, OWNER_FILE, label))
    except ValueError as error:
        raise ScaffoldError(f"invalid owner marker: {label}") from error
    if actual != _owner_payload():
        raise ScaffoldError(f"owner marker does not match this scaffold version: {label}")


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


def _bind_root(root: Path, *, resume: bool) -> int:
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
        _validate_owner(root_descriptor, root)
    return root_descriptor


def _persona_initial_files(persona: dict[str, object]) -> dict[str, object]:
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
            "schema_version": SCHEMA_VERSION,
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
            "schema_version": SCHEMA_VERSION,
            "persona_id": persona["id"],
            "fictional_entities": [],
            "timeline": [],
            "terminology": {},
            "numeric_anchors": {},
        },
    }


def scaffold(root: Path, *, resume: bool = False) -> Path:
    root = _absolute_lexical(root)
    root_descriptor = _bind_root(root, resume=resume)
    try:
        devices = _ensure_directory_at(root_descriptor, "devices", os.fspath(root))
        production = _ensure_directory_at(root_descriptor, "_production", os.fspath(root))
        try:
            for persona in spec.PERSONAS:
                slug = f"{persona['id']}-{persona['role']}"
                home = _ensure_directory_at(
                    devices, f"{slug}/home", os.fspath(root / "devices" / slug / "home")
                )
                control = _ensure_directory_at(
                    production, slug, os.fspath(root / "_production" / slug)
                )
                try:
                    for relative_path in spec.all_scope_paths(persona):
                        descriptor = _ensure_directory_at(home, relative_path, relative_path)
                        os.close(descriptor)
                    for relative_path in PRODUCTION_DIRS:
                        descriptor = _ensure_directory_at(control, relative_path, relative_path)
                        os.close(descriptor)

                    for name, payload in _persona_initial_files(persona).items():
                        label = os.fspath(root / "_production" / slug / name)
                        if not _validate_existing_control_file(
                            control, name, label, expect_json=True
                        ):
                            _write_new_json_at(control, name, payload, label)
                    for name in ("inventory.jsonl", "provenance.jsonl", "qa.jsonl"):
                        label = os.fspath(root / "_production" / slug / name)
                        if not _validate_existing_control_file(
                            control, name, label, expect_json=False
                        ):
                            _write_new_text_at(control, name, "", label)
                    for name, initial in (
                        (".lease.lock", "\0"),
                        ("lease-recovery.jsonl", ""),
                    ):
                        label = os.fspath(root / "_production" / slug / name)
                        if not _validate_existing_control_file(
                            control, name, label, expect_json=False
                        ):
                            _write_new_text_at(control, name, initial, label)
                    _validate_existing_control_file(
                        control,
                        "lease.json",
                        os.fspath(root / "_production" / slug / "lease.json"),
                        expect_json=True,
                    )
                finally:
                    os.close(home)
                    os.close(control)
        finally:
            os.close(devices)
            os.close(production)
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
